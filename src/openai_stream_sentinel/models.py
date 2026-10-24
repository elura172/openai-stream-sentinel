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


class SeverityLevel(str, Enum):
    SEV1 = "SEV-1 (Critical / Outage)"
    SEV2 = "SEV-2 (Major / Degraded)"
    SEV3 = "SEV-3 (Moderate / Latency Spike)"
    INFORMATIONAL = "INFORMATIONAL (Normal Operation)"


class StreamingMetrics(BaseModel):
    connect_start_ms: float
    tcp_handshake_ms: float
    ttft_ms: float = Field(description="Time to First Token in milliseconds")
    total_duration_s: float
    tokens_per_second: float
    total_tokens: int
    chunk_count: int
    jitter_mean_ms: float
    jitter_stddev_ms: float
    jitter_max_ms: float = 0.0
    jitter_p95_ms: float
    jitter_p99_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    prompt_cache_hit: bool = False
    inferred_domain: FailureDomain = FailureDomain.HEALTHY


class IncidentRecord(BaseModel):
    incident_id: str
    timestamp: str
    target_model: str
    failure_domain: FailureDomain
    severity: SeverityLevel
    mit_course_reference: str
    root_cause_summary: str
    metrics: StreamingMetrics
    telemetry_indicators: Dict[str, Any]
    reproduction_curl: str
    remediation_steps: List[str]


class RCAReport(BaseModel):
    incident: IncidentRecord
    customer_advisory: str
    engineering_postmortem: str
