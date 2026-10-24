"""Unit tests for the RCAEngine."""

import pytest
from openai_stream_sentinel.models import FailureDomain, SeverityLevel
from openai_stream_sentinel.telemetry import TelemetryTracker
from openai_stream_sentinel.rca_engine import RCAEngine


def test_rca_engine_buffer_bloat_report():
    tracker = TelemetryTracker(prompt_tokens=500)
    tracker.start_connection()
    tracker.record_chunk("A")
    # inject large gap then burst
    tracker.chunk_timestamps.append(tracker.first_token_time + 1.5)
    tracker.tokens.append("B")
    tracker.chunk_timestamps.append(tracker.first_token_time + 1.501)
    tracker.tokens.append("C")
    tracker.finish()

    metrics = tracker.compute_metrics()
    incident = RCAEngine.diagnose(metrics, {"buffer_stall_s": 1.5})
    assert incident.failure_domain == FailureDomain.PROXY_BUFFER_BLOAT
    assert "MIT 6.033" in incident.mit_course_reference

    report = RCAEngine.generate_report(incident)
    assert "[OpenAI Enterprise Customer Advisory]" in report.customer_advisory
    assert "Internal Incident RCA & Post-Mortem" in report.engineering_postmortem
    assert "curl" in report.engineering_postmortem
