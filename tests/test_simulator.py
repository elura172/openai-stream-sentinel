"""Unit tests for the 5 enterprise failure simulators."""

import pytest
from openai_stream_sentinel.models import FailureDomain
from openai_stream_sentinel.simulator import simulate_stream


@pytest.mark.asyncio
async def test_simulate_healthy():
    tracker, meta = await simulate_stream(FailureDomain.HEALTHY)
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.HEALTHY
    assert metrics.chunk_count > 10


@pytest.mark.asyncio
async def test_simulate_proxy_buffer_bloat():
    tracker, meta = await simulate_stream(FailureDomain.PROXY_BUFFER_BLOAT)
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.PROXY_BUFFER_BLOAT
    assert metrics.inter_chunk_interval_max_ms > 1000.0
    assert metrics.inter_chunk_interval_stddev_ms > 100.0


@pytest.mark.asyncio
async def test_simulate_prompt_cache_eviction():
    tracker, meta = await simulate_stream(FailureDomain.PROMPT_CACHE_EVICTION)
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.PROMPT_CACHE_EVICTION
    assert metrics.ttft_ms > 1000.0


@pytest.mark.asyncio
async def test_simulate_rate_limit_burst():
    tracker, meta = await simulate_stream(FailureDomain.RATE_LIMIT_BURST)
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.RATE_LIMIT_BURST


@pytest.mark.asyncio
async def test_simulate_tcp_rst_truncation():
    tracker, meta = await simulate_stream(FailureDomain.TCP_RST_TRUNCATION)
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.TCP_RST_TRUNCATION


@pytest.mark.asyncio
async def test_simulate_tool_timeout():
    tracker, meta = await simulate_stream(FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH)
    metrics = tracker.compute_metrics()
    assert metrics.inferred_domain == FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH
