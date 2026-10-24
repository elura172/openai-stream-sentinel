"""Exercise real SDK SSE parsing and CLI behavior over loopback HTTP."""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from openai_stream_sentinel.canary import CanaryRunner
from openai_stream_sentinel.models import FailureDomain


def event(*, content=None, finish_reason=None, usage=None):
    choices = [] if usage else [{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}]
    payload = {"id": "local-test", "object": "chat.completion.chunk", "created": 1,
               "model": "test-model", "choices": choices, "usage": usage}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


@pytest.fixture
def endpoint(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.server.auth_ok.append(self.headers.get("Authorization") == "Bearer local-test-key")
            self.server.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            scenario = self.server.scenario
            if scenario in ("429", "503"):
                self.send_response(int(scenario))
                self.send_header("Content-Type", "application/json")
                self.send_header("x-request-id", "local-request-001")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "local failure", "type": "test_error"}}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("x-request-id", "local-request-001")
            if scenario == "disconnect":
                self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            data = event(content="Hello 🌙")
            if scenario == "disconnect":
                self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()
                return  # Deliberately omit the terminating HTTP chunk.
            # Split an SSE event, including UTF-8 bytes, across socket writes.
            for byte in data:
                self.wfile.write(bytes([byte]))
            self.wfile.flush()
            if scenario == "trickle":
                try:
                    for _ in range(20):
                        time.sleep(0.03)
                        self.wfile.write(event(content=" more"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            if scenario == "timeout":
                time.sleep(0.6)
                return
            if scenario == "eof":
                return  # Valid HTTP EOF, but no model finish event.
            self.wfile.write(event(finish_reason="stop"))
            if scenario != "no-usage":
                self.wfile.write(event(usage={"prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21}))
            self.wfile.write(b"data: [DONE]\n\n")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.scenario = "success"
    server.requests = []
    server.auth_ok = []
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_clean_http_eof_without_finish_is_failure(endpoint):
    endpoint.scenario = "eof"
    report = asyncio.run(CanaryRunner.run_live_probe(model="test-model"))
    assert report.incident.metrics.error_occurred
    assert report.incident.failure_domain != FailureDomain.HEALTHY


@pytest.mark.parametrize("scenario,domain", [
    ("success", FailureDomain.HEALTHY),
    ("no-usage", FailureDomain.HEALTHY),
    ("disconnect", FailureDomain.STREAM_ERROR),
    ("timeout", FailureDomain.STREAM_ERROR),
    ("trickle", FailureDomain.STREAM_ERROR),
    ("429", FailureDomain.RATE_LIMIT_BURST),
    ("503", FailureDomain.STREAM_ERROR),
])
def test_real_sdk_stream_outcomes(endpoint, scenario, domain):
    endpoint.scenario = scenario
    report = asyncio.run(CanaryRunner.run_live_probe(model="test-model", timeout=0.2))
    metrics = report.incident.metrics
    assert report.incident.failure_domain == domain
    assert metrics.request_id == "local-request-001"
    assert len(endpoint.requests) == 1  # Retries must not obscure a probe failure.
    assert endpoint.requests[0]["stream_options"] == {"include_usage": True}
    if scenario in ("success", "no-usage"):
        assert metrics.finish_reason == "stop"
        assert metrics.chunk_count == 1
        assert metrics.completion_tokens == (4 if scenario == "success" else None)
        if scenario == "success":
            assert metrics.prompt_tokens == 17
        assert not metrics.error_occurred
    else:
        assert metrics.error_occurred
        assert metrics.error_details in report.engineering_postmortem
        assert metrics.finish_reason is None
        if scenario == "trickle":
            assert metrics.chunk_count > 1
            assert "Probe deadline exceeded" in metrics.error_details
        else:
            assert metrics.chunk_count == (0 if scenario in ("429", "503") else 1)
    if scenario in ("429", "503"):
        assert metrics.http_status_code == int(scenario)
        assert metrics.ttft_ms is None


@pytest.mark.parametrize("scenario", ["success", "eof", "disconnect", "timeout", "429", "503"])
def test_cli_exit_and_export(endpoint, tmp_path, scenario):
    endpoint.scenario = scenario
    output = tmp_path / "incident.md"
    result = subprocess.run(
        [sys.executable, "-m", "openai_stream_sentinel.cli", "probe", "--timeout", "0.2", "--out", str(output)],
        env=os.environ.copy(), capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == (0 if scenario == "success" else 1), result.stdout + result.stderr
    report = output.read_text()
    assert "Internal Diagnostic Draft" in report
    assert len(endpoint.requests) == 1
    if scenario in ("429", "503"):
        assert f"HTTP error status:** `{scenario}`" in report
        assert "unavailable (no content received)" in report
    if scenario == "eof":
        assert "before a model finish_reason" in report


def test_generated_connectivity_command_is_one_valid_request(endpoint):
    from openai_stream_sentinel.rca_engine import RCAEngine
    from openai_stream_sentinel.telemetry import TelemetryTracker

    tracker = TelemetryTracker()
    tracker.start_connection()
    tracker.record_error("request failed", status_code=503)
    model = "test-model'$(echo should-stay-literal)"
    incident = RCAEngine.diagnose(tracker.compute_metrics(), {"model": model, "mode": "LIVE_PROBE"})
    result = subprocess.run(["bash", "-c", incident.reproduction_command],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert len(endpoint.requests) == 1
    assert endpoint.auth_ok == [True]
    assert endpoint.requests[0]["model"] == model
    assert endpoint.requests[0]["messages"] == [{"role": "user", "content": "Ping"}]
