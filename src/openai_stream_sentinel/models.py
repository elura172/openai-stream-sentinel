"""Data models for stream telemetry, incident diagnosis, and root cause analysis."""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class FailureDomain(str, Enum):
    HEALTHY = "HEALTHY"
    PROXY_BUFFER_BLOAT = "PROXY_BUFFER_BLOAT"
    PROMPT_CACHE_EVICTION = "PROMPT_CACHE_EVICTION"
    RATE_LIMIT_BURST = "RATE_LIMIT_BURST"
    TCP_RST_TRUNCATION = "TCP_RST_TRUNCATION"
    TOOL_TIMEOUT_SCHEMA_MISMATCH = "TOOL_TIMEOUT_SCHEMA_MISMATCH"
    STREAM_ERROR = "STREAM_ERROR"


class SeverityLevel(str, Enum):
    SEV1 = "SEV-1 (Critical / Outage)"
    SEV2 = "SEV-2 (Major / Degraded)"
    SEV3 = "SEV-3 (Moderate / Latency Spike)"
    INFORMATIONAL = "INFORMATIONAL (Normal Operation)"


class StreamingMetrics(BaseModel):
    connect_start_ms: float
    tcp_handshake_ms: Optional[float] = None
    ttft_ms: Optional[float] = Field(default=None, description="Time to first content chunk; unavailable when no content arrived")
    finish_reason: Optional[str] = None
    total_duration_s: float
    chunks_per_second: Optional[float] = None
    chunk_count: int
    completion_tokens: Optional[int] = None
    inter_chunk_interval_mean_ms: float
    inter_chunk_interval_stddev_ms: float
    inter_chunk_interval_max_ms: float = 0.0
    inter_chunk_interval_p95_ms: float
    inter_chunk_interval_p99_ms: float
    inter_chunk_interval_sample_count: int = 0
    prompt_tokens: int = 0
    prompt_cache_hit: Optional[bool] = None
    inferred_domain: FailureDomain = FailureDomain.HEALTHY
    error_occurred: bool = False
    error_details: Optional[str] = None
    http_status_code: Optional[int] = None
    request_id: Optional[str] = None


class IncidentRecord(BaseModel):
    incident_id: str
    timestamp: str
    target_model: str
    failure_domain: FailureDomain
    severity: SeverityLevel
    probe_mode: str
    diagnostic_basis: str
    root_cause_summary: str
    metrics: StreamingMetrics
    telemetry_indicators: Dict[str, Any]
    reproduction_command: str
    remediation_steps: List[str]


class RCAReport(BaseModel):
    incident: IncidentRecord
    customer_advisory: str
    engineering_postmortem: str
