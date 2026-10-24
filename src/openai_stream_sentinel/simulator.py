"""Deterministic failure simulators modeling the top 5 enterprise API breakdown modes.

References:
- MIT 6.033: Computer System Engineering (Fault tolerance, retries, RPC timeouts)
- MIT 6.172: Performance Engineering (Buffering, tail latency, cache misses)
- MIT 6.824: Distributed Systems (RPC semantics, tool execution failures)
"""

import asyncio
import time
from typing import AsyncGenerator, Dict, Any, Tuple
from .models import FailureDomain
from .telemetry import TelemetryTracker


async def simulate_stream(scenario: FailureDomain) -> Tuple[TelemetryTracker, Dict[str, Any]]:
    """Simulates a streaming completion with synthetic network and inference characteristics."""
    meta: Dict[str, Any] = {"scenario": scenario.value}

    if scenario == FailureDomain.HEALTHY:
        tracker = TelemetryTracker(prompt_tokens=512)
        tracker.start_connection()
        await asyncio.sleep(0.035)  # 35ms TCP + TLS
        tracker.record_handshake()
        await asyncio.sleep(0.180)  # 180ms TTFT (warm inference)
        
        # 40 smooth chunks
        sample_tokens = ["OpenAI", " API", " streaming", " connection", " established", " with", " nominal", " latency.",
                         " All", " distributed", " nodes", " responding", " with", " sub-50ms", " token", " cadence.",
                         " Prompt", " cache", " lookup", " verified.", " Enterprise", " proxy", " pass-through", " clear.",
                         " Zero", " packet", " loss", " observed", " across", " gateway", " boundary.", " Ready",
                         " for", " production", " workload", " dispatch", " and", " telemetry", " collection", "."]
        for token in sample_tokens:
            tracker.record_chunk(token)
            await asyncio.sleep(0.022)  # ~45 tokens/sec
        tracker.finish()
        meta["model"] = "gpt-4o"
        meta["prompt_cache"] = "HIT"
        return tracker, meta

    elif scenario == FailureDomain.PROXY_BUFFER_BLOAT:
        tracker = TelemetryTracker(prompt_tokens=512)
        tracker.start_connection()
        await asyncio.sleep(0.040)
        tracker.record_handshake()
        await asyncio.sleep(0.220)
        
        # Initial chunk arrives
        tracker.record_chunk("Starting")
        tracker.record_chunk(" request")
        
        # Enterprise firewall/proxy buffers stream instead of immediate flush!
        meta["simulated_fault"] = "Palo Alto / Zscaler intermediate proxy buffer delay (1.85s)"
        await asyncio.sleep(1.85)  # Huge stall
        
        # Giant burst flushed all at once
        burst_tokens = [" [Proxy", " Flushed", " Buffer]:", " Here", " is", " the", " full", " enterprise",
                        " response", " delivered", " in", " a", " single", " TCP", " burst", " rather",
                        " than", " a", " smooth", " stream.", " High", " variance", " in", " token",
                        " inter-arrival", " time", " destroys", " interactive", " conversational", " cadence."]
        for token in burst_tokens:
            tracker.record_chunk(token)
            await asyncio.sleep(0.001)  # Delivered in <1ms bursts
        tracker.finish()
        meta["model"] = "gpt-4o"
        meta["buffer_stall_s"] = 1.85
        return tracker, meta

    elif scenario == FailureDomain.PROMPT_CACHE_EVICTION:
        # 4,500 token system prompt with a dynamic timestamp prepended at byte 0
        tracker = TelemetryTracker(prompt_tokens=4500)
        tracker.start_connection()
        await asyncio.sleep(0.040)
        tracker.record_handshake()
        
        # Cold prefill delay: KV cache cannot be reused because prefix is non-deterministic
        meta["simulated_fault"] = "Prefix cache miss: Dynamic timestamp injected at index 0 of 4,500 token prompt"
        await asyncio.sleep(2.150)  # 2.15s TTFT!
        
        sample_tokens = ["Processing", " un-cached", " 4.5k", " token", " context.", " Notice", " extreme",
                         " TTFT", " penalty", " caused", " by", " non-deterministic", " prefix", " variation."]
        for token in sample_tokens:
            tracker.record_chunk(token)
            await asyncio.sleep(0.025)
        tracker.finish()
        meta["model"] = "gpt-4o"
        meta["prompt_cache"] = "MISS (Cold Prefill)"
        return tracker, meta

    elif scenario == FailureDomain.RATE_LIMIT_BURST:
        tracker = TelemetryTracker(prompt_tokens=150)
        tracker.start_connection()
        await asyncio.sleep(0.025)
        tracker.record_handshake()
        await asyncio.sleep(0.080)
        
        # Fails with 429
        meta["http_status"] = 429
        meta["error_code"] = "rate_limit_exceeded"
        meta["simulated_fault"] = "Token bucket exhausted: 15 concurrent agent workers burst into shared TPM quota"
        meta["backoff_algo"] = "Decorrelated Exponential Jitter (Full Jitter)"
        tracker.record_error("HTTP 429: rate_limit_exceeded (TPM quota saturated)")
        return tracker, meta

    elif scenario == FailureDomain.TCP_RST_TRUNCATION:
        tracker = TelemetryTracker(prompt_tokens=256)
        tracker.start_connection()
        await asyncio.sleep(0.030)
        tracker.record_handshake()
        await asyncio.sleep(0.190)
        
        # Starts streaming normally...
        tokens = ["This", " stream", " is", " generating", " normally", " across", " the", " enterprise", " egress", " gateway..."]
        for t in tokens:
            tracker.record_chunk(t)
            await asyncio.sleep(0.025)
            
        # Socket reset mid-stream after token 10!
        meta["simulated_fault"] = "TCP RST received / HTTP/2 RST_STREAM: Ingress timeout (idle timeout exceeded on reverse proxy)"
        meta["tokens_emitted_before_rst"] = 10
        tracker.record_error("TCP Connection Reset by Peer (RST_STREAM / Socket Truncation)")
        return tracker, meta

    elif scenario == FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH:
        tracker = TelemetryTracker(prompt_tokens=800)
        tracker.start_connection()
        await asyncio.sleep(0.035)
        tracker.record_handshake()
        await asyncio.sleep(0.240)
        
        tracker.record_chunk('{"tool_call": "fetch_customer_record"')
        tracker.record_chunk(', "arguments": {"customer_id": "CUST-9921"')
        
        meta["simulated_fault"] = "Downstream MCP tool execution timed out after 10.0s; returned malformed non-JSON schema"
        meta["tool_name"] = "fetch_customer_record"
        meta["client_deadline_s"] = 10.0
        tracker.record_error("ToolExecutionTimeout: Downstream tool 'fetch_customer_record' failed client deadline (10s)")
        return tracker, meta

    raise ValueError(f"Unknown scenario: {scenario}")
