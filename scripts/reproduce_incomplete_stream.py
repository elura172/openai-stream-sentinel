"""Reproduce clean HTTP EOF without a model finish event, using loopback only.

Run with the target checkout on PYTHONPATH to compare historical versions.
"""
import argparse
import asyncio
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.server.request_count += 1
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("x-request-id", "local-incomplete-stream-001")
            self.end_headers()
            payload = {"id": "local", "object": "chat.completion.chunk", "created": 1,
                       "model": "test-model", "choices": [{"index": 0,
                       "delta": {"content": "Partial answer"}, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()
            # HTTP/1.0 closes cleanly here: no transport error, finish_reason, or [DONE].

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.request_count = 0
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    os.environ["OPENAI_API_KEY"] = "local-test-key"
    os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{server.server_port}/v1"
    os.environ["NO_PROXY"] = "127.0.0.1"
    try:
        from openai_stream_sentinel.canary import CanaryRunner
        import openai_stream_sentinel

        async def probe():
            return await asyncio.wait_for(CanaryRunner.run_live_probe(model="test-model", prompt="Ping"), timeout=5)

        report = asyncio.run(probe())
        cmd = [sys.executable, "-m", "openai_stream_sentinel.cli", "probe", "--model", "test-model",
               "--prompt", "Ping", "--out", str(args.out / "cli-report.md")]
        cli = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
        (args.out / "cli-output.txt").write_text(cli.stdout + cli.stderr)
        (args.out / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
        source = Path(openai_stream_sentinel.__file__).parent
        digest = hashlib.sha256()
        for path in sorted(source.glob("*.py")):
            digest.update(path.name.encode() + b"\0" + path.read_bytes())
        head = subprocess.run(["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()
        result = {
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "git_head": head,
            "source_sha256": digest.hexdigest(),
            "sentinel_version": openai_stream_sentinel.__version__,
            "python": platform.python_version(),
            "openai_sdk": importlib.metadata.version("openai"),
            "http_status_served": 200,
            "content_chunks_per_request": 1,
            "finish_event_sent": False,
            "done_marker_sent": False,
            "requests_received": server.request_count,
            "expected_requests": 2,
            "api_report_error": report.incident.metrics.model_dump().get("error_occurred"),
            "api_report_domain": report.incident.failure_domain.value,
            "cli_exit": cli.returncode,
            "cli_report_written": (args.out / "cli-report.md").exists(),
        }
        (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
