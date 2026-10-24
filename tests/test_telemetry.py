"""Unit tests for TelemetryTracker and statistical analysis."""

import pytest
import time
from types import SimpleNamespace
from openai_stream_sentinel import canary
from openai_stream_sentinel.telemetry import TelemetryTracker
from openai_stream_sentinel.models import FailureDomain


def test_telemetry_tracker_healthy_stream():
    tracker = TelemetryTracker(prompt_tokens=500)
    tracker.start_connection()
    time.sleep(0.01)
    tracker.record_handshake()
    time.sleep(0.02)
    tracker.record_chunk("Hello")
    time.sleep(0.01)
    tracker.record_chunk(" World")
    time.sleep(0.01)
    tracker.record_chunk("!")
    tracker.finish()

    metrics = tracker.compute_metrics()
    assert metrics.chunk_count == 3
    assert metrics.ttft_ms > 0
    assert metrics.chunks_per_second > 0
    assert metrics.inferred_domain == FailureDomain.HEALTHY


def test_telemetry_tracker_error_recording():
    tracker = TelemetryTracker(prompt_tokens=100)
    tracker.start_connection()
    tracker.record_error("HTTP 429: rate_limit_exceeded")
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.RATE_LIMIT_BURST


def test_unclassified_error_is_not_reported_as_healthy():
    tracker = TelemetryTracker()
    tracker.start_connection()
    tracker.record_error("upstream request failed", status_code=503)

    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.STREAM_ERROR
    assert metrics.error_occurred is True
    assert metrics.error_details == "upstream request failed"
    assert metrics.http_status_code == 503


def test_rate_limit_classification_uses_status_code():
    tracker = TelemetryTracker()
    tracker.start_connection()
    tracker.record_error("request rejected", status_code=429)

    assert tracker.compute_metrics().inferred_domain == FailureDomain.RATE_LIMIT_BURST


@pytest.mark.asyncio
async def test_live_probe_preserves_unclassified_http_failure(monkeypatch):
    class UpstreamFailure(Exception):
        status_code = 503

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def create(self, **kwargs):
            raise UpstreamFailure("upstream unavailable")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(canary, "HAS_OPENAI", True)
    monkeypatch.setattr(canary, "AsyncOpenAI", lambda **kwargs: FakeClient())

    report = await canary.CanaryRunner.run_live_probe(model="test-model", prompt="hello")

    assert report.incident.failure_domain == FailureDomain.STREAM_ERROR
    assert report.incident.metrics.http_status_code == 503
    assert report.incident.metrics.error_details == "UpstreamFailure: upstream unavailable"
    assert report.incident.metrics.tcp_handshake_ms is None


def test_tcp_handshake_is_unknown_until_explicitly_recorded():
    tracker = TelemetryTracker()
    tracker.start_connection()
    tracker.record_chunk("first content")
    tracker.finish()

    assert tracker.compute_metrics().tcp_handshake_ms is None


def test_telemetry_tracker_prompt_cache_hit_detection():
    tracker = TelemetryTracker(prompt_tokens=2048)
    tracker.start_connection()
    tracker.record_handshake()
    # Emulate very fast TTFT on large prompt (< 400ms)
    time.sleep(0.05)
    tracker.record_chunk("Cached")
    tracker.finish()

    metrics = tracker.compute_metrics()
    assert metrics.prompt_cache_hit is True


def test_completion_token_count_is_unknown_without_provider_usage():
    tracker = TelemetryTracker()
    tracker.start_connection()
    tracker.record_chunk("a chunk that may contain several tokens")
    tracker.finish()

    metrics = tracker.compute_metrics()
    assert metrics.completion_tokens is None
    assert metrics.chunks_per_second is None


def test_prompt_cache_status_is_unknown_without_a_strong_signal():
    tracker = TelemetryTracker(prompt_tokens=500)
    tracker.start_connection()
    tracker.record_chunk("hello")
    tracker.finish()

    assert tracker.compute_metrics().prompt_cache_hit is None


def test_provider_usage_is_reported_separately_from_chunks():
    tracker = TelemetryTracker()
    tracker.start_connection()
    tracker.record_chunk("multiple words in one chunk")
    tracker.record_usage(completion_tokens=4, prompt_tokens=17)
    tracker.finish()

    metrics = tracker.compute_metrics()
    assert metrics.chunk_count == 1
    assert metrics.completion_tokens == 4
    assert metrics.prompt_tokens == 17


@pytest.mark.parametrize("message,status", [
    ("first request failed", None),
    ("tool configuration was mentioned in a generic error", None),
    ("upstream failed while discussing HTTP 429", 503),
])
def test_incidental_error_text_does_not_invent_a_failure_domain(message, status):
    tracker = TelemetryTracker()
    tracker.start_connection()
    tracker.record_error(message, status_code=status)
    assert tracker.compute_metrics().inferred_domain == FailureDomain.STREAM_ERROR
