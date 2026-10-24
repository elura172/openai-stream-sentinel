"""Collect client-side timing, provider usage, and diagnostic pattern signals."""

import math
import re
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
        self.http_status_code: Optional[int] = None
        self.completion_tokens: Optional[int] = None
        self.finish_reason: Optional[str] = None
        self.request_id: Optional[str] = None

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

    def record_usage(self, completion_tokens: Optional[int], prompt_tokens: Optional[int] = None) -> None:
        """Record provider-reported completion token usage when available."""
        if completion_tokens is not None:
            self.completion_tokens = completion_tokens
        if prompt_tokens is not None:
            self.prompt_tokens = prompt_tokens

    def finish(self) -> None:
        self.stream_end = time.perf_counter()

    def record_error(self, err: str, status_code: Optional[int] = None) -> None:
        self.error_occurred = True
        self.error_details = err
        self.http_status_code = status_code
        self.stream_end = time.perf_counter()

    def compute_metrics(self) -> StreamingMetrics:
        if self.connect_start == 0.0:
            self.connect_start = time.perf_counter()
        if self.stream_end == 0.0:
            self.stream_end = time.perf_counter()

        tcp_handshake_ms = (
            (self.tcp_connected - self.connect_start) * 1000.0
            if self.tcp_connected > 0.0 else None
        )
        ttft_ms = (self.first_token_time - self.connect_start) * 1000.0 if self.chunk_timestamps else None
        total_duration_s = max(0.0001, self.stream_end - self.connect_start)
        gen_duration_s = max(0.0, self.stream_end - self.first_token_time) if self.chunk_timestamps else 0.0

        chunk_count = len(self.chunk_timestamps)
        # Avoid presenting a tiny burst window as sustained throughput.
        chunks_per_second = chunk_count / gen_duration_s if chunk_count > 1 and gen_duration_s >= 0.01 else None

        # Calculate inter-chunk arrival times in ms
        diffs_ms: List[float] = []
        for i in range(1, len(self.chunk_timestamps)):
            diff = (self.chunk_timestamps[i] - self.chunk_timestamps[i - 1]) * 1000.0
            diffs_ms.append(diff)

        if not diffs_ms:
            mean_interval = 0.0
            stddev_interval = 0.0
            interval_max = 0.0
            interval_p95 = 0.0
            interval_p99 = 0.0
        else:
            diffs_sorted = sorted(diffs_ms)
            mean_interval = statistics.mean(diffs_ms)
            stddev_interval = statistics.stdev(diffs_ms) if len(diffs_ms) > 1 else 0.0
            interval_max = max(diffs_ms)
            p95_idx = min(len(diffs_sorted) - 1, math.ceil(0.95 * len(diffs_sorted)) - 1)
            p99_idx = min(len(diffs_sorted) - 1, math.ceil(0.99 * len(diffs_sorted)) - 1)
            interval_p95 = diffs_sorted[p95_idx]
            interval_p99 = diffs_sorted[p99_idx]

        # Detect prompt cache hit heuristic:
        # If prompt > 1024 tokens and TTFT < 350ms -> cache hit.
        # If prompt > 2048 tokens and TTFT > 1400ms -> possible cold prefill / cache miss.
        prompt_cache_hit: Optional[bool] = None
        if ttft_ms is not None and self.prompt_tokens >= 1024 and ttft_ms < 400.0:
            prompt_cache_hit = True
        elif ttft_ms is not None and self.prompt_tokens >= 2048 and ttft_ms > 1400.0:
            prompt_cache_hit = False

        # Inferred domain classification
        domain = FailureDomain.HEALTHY
        error_text = (self.error_details or "").casefold()
        if self.error_occurred and self.http_status_code == 429:
            domain = FailureDomain.RATE_LIMIT_BURST
        elif self.error_occurred and self.http_status_code is not None:
            domain = FailureDomain.STREAM_ERROR
        elif self.error_occurred and (re.search(r"\b429\b", error_text) or "rate_limit" in error_text):
            domain = FailureDomain.RATE_LIMIT_BURST
        elif self.error_occurred and any(term in error_text for term in ("rst_stream", "econnreset", "truncation", "connection reset", "connection aborted")):
            domain = FailureDomain.TCP_RST_TRUNCATION
        elif self.error_occurred and any(term in error_text for term in ("toolexecutiontimeout", "tool timeout", "tool schema")):
            domain = FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH
        elif self.error_occurred:
            domain = FailureDomain.STREAM_ERROR
        elif interval_p95 > 200.0 or (diffs_ms and interval_max > 1000.0):
            domain = FailureDomain.PROXY_BUFFER_BLOAT
        elif ttft_ms is not None and self.prompt_tokens >= 2048 and ttft_ms > 1400.0:
            domain = FailureDomain.PROMPT_CACHE_EVICTION

        return StreamingMetrics(
            connect_start_ms=self.connect_start * 1000.0,
            tcp_handshake_ms=tcp_handshake_ms,
            ttft_ms=ttft_ms,
            finish_reason=self.finish_reason,
            total_duration_s=total_duration_s,
            chunks_per_second=chunks_per_second,
            chunk_count=chunk_count,
            completion_tokens=self.completion_tokens,
            inter_chunk_interval_mean_ms=mean_interval,
            inter_chunk_interval_stddev_ms=stddev_interval,
            inter_chunk_interval_max_ms=interval_max,
            inter_chunk_interval_p95_ms=interval_p95,
            inter_chunk_interval_p99_ms=interval_p99,
            inter_chunk_interval_sample_count=len(diffs_ms),
            prompt_tokens=self.prompt_tokens,
            prompt_cache_hit=prompt_cache_hit,
            inferred_domain=domain,
            error_occurred=self.error_occurred,
            error_details=self.error_details,
            http_status_code=self.http_status_code,
            request_id=self.request_id,
        )
