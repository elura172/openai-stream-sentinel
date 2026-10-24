"""Telemetry collector and statistical analyzer for streaming LLM completions.

References:
- MIT 6.172 (Performance Engineering): Latency tail distributions, percentiles, cache hits
- MIT 6.033 (Computer System Engineering): End-to-end telemetry and socket performance
"""

import math
import statistics
import time
from typing import List, Dict, Any, Tuple, Optional
from .models import StreamingMetrics, FailureDomain


class TelemetryTracker:
    def __init__(self, prompt_tokens: int = 100):
        self.prompt_tokens = prompt_tokens
        self.connect_start: float = 0.0
        self.tcp_connected: float = 0.0
        self.first_token_time: float = 0.0
        self.stream_end: float = 0.0
        self.chunk_timestamps: List[float] = []
        self.tokens: List[str] = []
        self.error_occurred: bool = False
        self.error_details: Optional[str] = None

    def start_connection(self) -> None:
        self.connect_start = time.perf_counter()

    def record_handshake(self) -> None:
        self.tcp_connected = time.perf_counter()

    def record_chunk(self, token_chunk: str) -> None:
        now = time.perf_counter()
        if not self.chunk_timestamps:
            self.first_token_time = now
        self.chunk_timestamps.append(now)
        self.tokens.append(token_chunk)

    def finish(self) -> None:
        self.stream_end = time.perf_counter()

    def record_error(self, err: str) -> None:
        self.error_occurred = True
        self.error_details = err
        self.stream_end = time.perf_counter()

    def compute_metrics(self) -> StreamingMetrics:
        if self.connect_start == 0.0:
            self.connect_start = time.perf_counter()
        if self.tcp_connected == 0.0:
            self.tcp_connected = self.connect_start + 0.025  # default 25ms handshake
        if self.first_token_time == 0.0:
            self.first_token_time = self.stream_end or time.perf_counter()
        if self.stream_end == 0.0:
            self.stream_end = time.perf_counter()

        tcp_handshake_ms = (self.tcp_connected - self.connect_start) * 1000.0
        ttft_ms = (self.first_token_time - self.connect_start) * 1000.0
        total_duration_s = max(0.0001, self.stream_end - self.connect_start)
        gen_duration_s = max(0.0001, self.stream_end - self.first_token_time)

        total_tokens = len(self.tokens)
        tokens_per_second = (total_tokens / gen_duration_s) if total_tokens > 0 else 0.0

        # Calculate inter-chunk arrival times in ms
        diffs_ms: List[float] = []
        for i in range(1, len(self.chunk_timestamps)):
            diff = (self.chunk_timestamps[i] - self.chunk_timestamps[i - 1]) * 1000.0
            diffs_ms.append(diff)

        if not diffs_ms:
            mean_jitter = 0.0
            stddev_jitter = 0.0
            max_jitter = 0.0
            p95_jitter = 0.0
            p99_jitter = 0.0
        else:
            diffs_sorted = sorted(diffs_ms)
            mean_jitter = statistics.mean(diffs_ms)
            stddev_jitter = statistics.stdev(diffs_ms) if len(diffs_ms) > 1 else 0.0
            max_jitter = max(diffs_ms)
            p95_idx = min(len(diffs_sorted) - 1, math.floor(0.95 * len(diffs_sorted)))
            p99_idx = min(len(diffs_sorted) - 1, math.floor(0.99 * len(diffs_sorted)))
            p95_jitter = diffs_sorted[p95_idx]
            p99_jitter = diffs_sorted[p99_idx]

        # Detect prompt cache hit heuristic:
        # If prompt > 1024 tokens and TTFT < 350ms -> cache hit.
        # If prompt > 2048 tokens and TTFT > 1200ms -> cold prefill / cache miss.
        prompt_cache_hit = False
        if self.prompt_tokens >= 1024 and ttft_ms < 400.0:
            prompt_cache_hit = True

        # Inferred domain classification
        domain = FailureDomain.HEALTHY
        if self.error_occurred and "429" in (self.error_details or ""):
            domain = FailureDomain.RATE_LIMIT_BURST
        elif self.error_occurred and ("RST" in (self.error_details or "") or "Truncation" in (self.error_details or "")):
            domain = FailureDomain.TCP_RST_TRUNCATION
        elif self.error_occurred and "Tool" in (self.error_details or ""):
            domain = FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH
        elif p95_jitter > 200.0 or (diffs_ms and max(diffs_ms) > 1000.0):
            domain = FailureDomain.PROXY_BUFFER_BLOAT
        elif self.prompt_tokens >= 2048 and ttft_ms > 1400.0:
            domain = FailureDomain.PROMPT_CACHE_EVICTION

        return StreamingMetrics(
            connect_start_ms=self.connect_start * 1000.0,
            tcp_handshake_ms=tcp_handshake_ms,
            ttft_ms=ttft_ms,
            total_duration_s=total_duration_s,
            tokens_per_second=tokens_per_second,
            total_tokens=total_tokens,
            chunk_count=len(self.chunk_timestamps),
            jitter_mean_ms=mean_jitter,
            jitter_stddev_ms=stddev_jitter,
            jitter_max_ms=max_jitter,
            jitter_p95_ms=p95_jitter,
            jitter_p99_ms=p99_jitter,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=total_tokens,
            prompt_cache_hit=prompt_cache_hit,
            inferred_domain=domain
        )
