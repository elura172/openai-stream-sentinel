"""Unit tests for TelemetryTracker and statistical analysis."""

import pytest
import time
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
    assert metrics.total_tokens == 3
    assert metrics.ttft_ms > 0
    assert metrics.tokens_per_second > 0
    assert metrics.inferred_domain == FailureDomain.HEALTHY


def test_telemetry_tracker_error_recording():
    tracker = TelemetryTracker(prompt_tokens=100)
    tracker.start_connection()
    tracker.record_error("HTTP 429: rate_limit_exceeded")
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.RATE_LIMIT_BURST


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
