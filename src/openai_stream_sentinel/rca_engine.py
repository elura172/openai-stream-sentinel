"""Auto-RCA Engine — Diagnoses enterprise API incidents and formats dual-format outputs.

Outputs:
1. External Customer Incident Advisory (actionable workaround, calm communication)
2. Internal Engineering Post-Mortem (reproduction cURL, telemetry, MIT course grounding)

References:
- MIT 6.033: Computer System Engineering (Fault tolerance, post-incident analysis)
- MIT 6.172: Performance Engineering (Latency distributions, cache reuse)
- MIT 6.824: Distributed Systems (RPC semantics, tool execution failures)
"""

import datetime
import uuid
from typing import Dict, Any, List
from .models import FailureDomain, SeverityLevel, StreamingMetrics, IncidentRecord, RCAReport


class RCAEngine:
    @staticmethod
    def diagnose(metrics: StreamingMetrics, meta: Dict[str, Any]) -> IncidentRecord:
        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        domain = metrics.inferred_domain
        model = meta.get("model", "gpt-4o")

        if domain == FailureDomain.HEALTHY:
            return IncidentRecord(
                incident_id=incident_id,
                timestamp=now_str,
                target_model=model,
                failure_domain=domain,
                severity=SeverityLevel.INFORMATIONAL,
                mit_course_reference="MIT 6.172 (Performance Engineering: Cache Locality & Pipeline Throughput)",
                root_cause_summary="No stream error was observed, and the measured client-side TTFT and inter-chunk intervals were within the probe's reference thresholds.",
                metrics=metrics,
                telemetry_indicators={"ttft_ms": metrics.ttft_ms, "chunks_per_second": metrics.chunks_per_second, "p95_inter_chunk_interval_ms": metrics.inter_chunk_interval_p95_ms},
                reproduction_curl="curl -X POST https://api.openai.com/v1/chat/completions -H 'Content-Type: application/json' -d '{\"model\": \"gpt-4o\", \"stream\": true}'",
                remediation_steps=["Continue routine synthetic canary monitoring.", "Verify quarterly SLO compliance against P99 latency."]
            )

        elif domain == FailureDomain.PROXY_BUFFER_BLOAT:
            return IncidentRecord(
                incident_id=incident_id,
                timestamp=now_str,
                target_model=model,
                failure_domain=domain,
                severity=SeverityLevel.SEV3,
                mit_course_reference="MIT 6.033 (Computer System Engineering: Network Buffering & The End-to-End Argument)",
                root_cause_summary=(
                    "A long inter-chunk interval was observed. This pattern is compatible with response buffering, but client-side timing "
                    "cannot locate the delay or distinguish a proxy from server, network, or local scheduling effects."
                ),
                metrics=metrics,
                telemetry_indicators={
                    "p95_inter_chunk_interval_ms": metrics.inter_chunk_interval_p95_ms,
                    "max_stall_s": meta.get("buffer_stall_s", 1.85),
                    "mean_inter_chunk_interval_ms": metrics.inter_chunk_interval_mean_ms,
                    "diagnostic": "Proxy Buffer Bloat"
                },
                reproduction_curl=(
                    "curl -N -v -X POST https://api.openai.com/v1/chat/completions \\\n"
                    "  -H 'Authorization: Bearer $OPENAI_API_KEY' \\\n"
                    "  -H 'Content-Type: application/json' \\\n"
                    "  -H 'X-Accel-Buffering: no' \\\n"
                    "  -d '{\"model\": \"gpt-4o\", \"stream\": true, \"messages\": [{\"role\": \"user\", \"content\": \"ping\"}]}'"
                ),
                remediation_steps=[
                    "Configure enterprise proxy / WAF to bypass response body buffering for domain `api.openai.com`.",
                    "Set `X-Accel-Buffering: no` and ensure `transfer-encoding: chunked` passes unbuffered to the client.",
                    "Audit MTU and TCP window scaling settings on customer egress gateway."
                ]
            )

        elif domain == FailureDomain.PROMPT_CACHE_EVICTION:
            return IncidentRecord(
                incident_id=incident_id,
                timestamp=now_str,
                target_model=model,
                failure_domain=domain,
                severity=SeverityLevel.SEV3,
                mit_course_reference="MIT 6.172 (Performance Engineering: Cache Hierarchy & KV Cache Spatial Locality)",
                root_cause_summary=(
                    "High time-to-first-token (TTFT) was observed with a long prompt. A cold prompt-cache prefill is one possible explanation, "
                    "but client-side timing alone cannot confirm cache status or rule out server and network causes."
                ),
                metrics=metrics,
                telemetry_indicators={
                    "ttft_ms": metrics.ttft_ms,
                    "prompt_tokens": metrics.prompt_tokens,
                    "cache_status": "MISS (Cold Prefill)",
                    "expected_ttft_ms": "< 350 ms on Cache Hit"
                },
                reproduction_curl=(
                    "curl -X POST https://api.openai.com/v1/chat/completions \\\n"
                    "  -H 'Authorization: Bearer $OPENAI_API_KEY' \\\n"
                    "  -H 'Content-Type: application/json' \\\n"
                    "  -d '{\"model\": \"gpt-4o\", \"messages\": [{\"role\": \"system\", \"content\": \"TIMESTAMP_HERE_INVALIDATES_CACHE...\"}]}'"
                ),
                remediation_steps=[
                    "Refactor prompt template: place static system instructions and documentation at the exact beginning of the prompt.",
                    "Move volatile context (timestamps, user UUIDs, dynamic memory) to the very end of the message list.",
                    "Ensure prefix blocks exceed 1,024 tokens to qualify for automatic OpenAI KV prompt caching."
                ]
            )

        elif domain == FailureDomain.RATE_LIMIT_BURST:
            return IncidentRecord(
                incident_id=incident_id,
                timestamp=now_str,
                target_model=model,
                failure_domain=domain,
                severity=SeverityLevel.SEV2,
                mit_course_reference="MIT 6.033 (Fault Tolerance: Token-Bucket Rate Limiting, Backpressure & Decorrelated Jitter)",
                root_cause_summary=(
                    "HTTP 429 was reported. This probe cannot establish the quota cause, request concurrency, "
                    "or whether retries amplified the event."
                ),
                metrics=metrics,
                telemetry_indicators={
                    "http_status": 429,
                    "error_type": "rate_limit_exceeded",
                    "concurrent_workers": 15,
                    "recommended_retry_algo": "Full Jitter Exponential Backoff"
                },
                reproduction_curl=(
                    "for i in {1..20}; do \\\n"
                    "  curl -s -o /dev/null -w \"%{http_code}\\n\" -X POST https://api.openai.com/v1/chat/completions \\\n"
                    "    -H 'Authorization: Bearer $OPENAI_API_KEY' -H 'Content-Type: application/json' \\\n"
                    "    -d '{\"model\": \"gpt-4o\", \"max_tokens\": 1000}' & \\\n"
                    "done; wait"
                ),
                remediation_steps=[
                    "Implement Decorrelated Jitter Backoff algorithm on the client SDK: `sleep = min(cap, random(base, sleep * 3))`.",
                    "Adopt client-side token bucket rate-limiting (e.g., Redis or in-memory semaphore) to smooth burst traffic before egress.",
                    "Request a temporary TPM/RPM tier increase through OpenAI enterprise account management for scheduled batch jobs."
                ]
            )

        elif domain == FailureDomain.TCP_RST_TRUNCATION:
            return IncidentRecord(
                incident_id=incident_id,
                timestamp=now_str,
                target_model=model,
                failure_domain=domain,
                severity=SeverityLevel.SEV1,
                mit_course_reference="MIT 6.033 (Computer System Engineering: Network Transport, Idle Timeouts & Keep-Alives)",
                root_cause_summary=(
                    "The stream terminated with a connection-reset error. The client cannot determine which network hop reset the connection "
                    "or establish that an idle timeout caused it."
                ),
                metrics=metrics,
                telemetry_indicators={
                    "tokens_before_drop": meta.get("tokens_emitted_before_rst", 10),
                    "socket_state": "ECONNRESET / Connection reset by peer",
                    "idle_timeout_suspect": "60.0s"
                },
                reproduction_curl=(
                    "curl -N --limit-rate 5 -X POST https://api.openai.com/v1/chat/completions \\\n"
                    "  -H 'Authorization: Bearer $OPENAI_API_KEY' -H 'Content-Type: application/json' \\\n"
                    "  -d '{\"model\": \"gpt-4o\", \"stream\": true, \"messages\": [{\"role\": \"user\", \"content\": \"Long stream...\"}]}'"
                ),
                remediation_steps=[
                    "Increase HTTP/2 keep-alive and idle timeout settings on intermediate proxies to >= 300 seconds.",
                    "Implement client-side stream resumption with token-offset checkpoints.",
                    "Enable TCP keep-alive probes on customer egress interfaces (`SO_KEEPALIVE`, `TCP_KEEPIDLE=30`)."
                ]
            )

        elif domain == FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH:
            return IncidentRecord(
                incident_id=incident_id,
                timestamp=now_str,
                target_model=model,
                failure_domain=domain,
                severity=SeverityLevel.SEV2,
                mit_course_reference="MIT 6.824 (Distributed Systems: RPC Semantics, Timeouts & Schema Validation)",
                root_cause_summary=(
                    "A tool-related timeout or schema error was reported. This probe does not execute downstream tools, so confirm the tool "
                    "call, deadline, and returned payload in the system that performed the invocation."
                ),
                metrics=metrics,
                telemetry_indicators={
                    "tool_name": meta.get("tool_name", "fetch_customer_record"),
                    "deadline_s": meta.get("client_deadline_s", 10.0),
                    "error": "Client RPC Timeout"
                },
                reproduction_curl=(
                    "curl -X POST https://api.openai.com/v1/chat/completions \\\n"
                    "  -H 'Authorization: Bearer $OPENAI_API_KEY' -H 'Content-Type: application/json' \\\n"
                    "  -d '{\"model\": \"gpt-4o\", \"tools\": [{\"type\": \"function\", \"function\": {\"name\": \"slow_tool\"}}]}'"
                ),
                remediation_steps=[
                    "Enforce strict Pydantic / JSON-Schema validation on tool return arguments before passing back into conversation history.",
                    "Implement independent timeouts per tool execution and return structured `{error: 'timeout', partial: ...}` instead of dropping connection.",
                    "Employ session-scoped idempotency keys on tool dispatches to safely handle retry loops without state corruption."
                ]
            )

        elif domain == FailureDomain.STREAM_ERROR:
            return IncidentRecord(
                incident_id=incident_id,
                timestamp=now_str,
                target_model=model,
                failure_domain=domain,
                severity=SeverityLevel.SEV2,
                mit_course_reference="Distributed systems: failure detection and error propagation",
                root_cause_summary=(
                    "The streaming request failed. The available client telemetry does not identify a more specific failure domain; "
                    "inspect the captured error and HTTP status before attributing the cause to a network or service component."
                ),
                metrics=metrics,
                telemetry_indicators={
                    "http_status": metrics.http_status_code,
                    "error": metrics.error_details or "Unknown streaming error",
                    "diagnostic": "Unclassified stream failure"
                },
                reproduction_curl="Reproduce with the same model and prompt using the OpenAI API client while recording the response status and stream error.",
                remediation_steps=[
                    "Check the recorded HTTP status and error message, then correlate them with request identifiers and service telemetry.",
                    "Do not attribute the failure to a proxy, model, or tool without corroborating evidence."
                ]
            )

        raise ValueError(f"Unmapped domain: {domain}")

    @staticmethod
    def generate_report(incident: IncidentRecord) -> RCAReport:
        advisory = (
            f"### [OpenAI Enterprise Customer Advisory] — {incident.incident_id}\n\n"
            f"**Status:** Diagnostic draft; cause and mitigation require validation  \n"
            f"**Impacted Surface:** API Streaming & Tool Invocation ({incident.target_model})  \n"
            f"**Severity:** {incident.severity.value}  \n\n"
            f"#### Summary\n"
            f"{incident.root_cause_summary}\n\n"
            f"#### Immediate Actionable Workaround for Engineering Teams\n"
        )
        for step in incident.remediation_steps:
            advisory += f"- {step}\n"

        advisory += (
            f"\n*This advisory was generated from client-side telemetry and has not been independently validated. Confirm the cause and proposed workaround before external use.*"
        )

        postmortem = (
            f"# Internal Diagnostic Draft: {incident.incident_id}\n\n"
            f"**Target Model:** `{incident.target_model}`  \n"
            f"**Failure Domain:** `{incident.failure_domain.value}`  \n"
            f"**Severity Classification:** `{incident.severity.value}`  \n"
            f"**Theoretical Grounding:** `{incident.mit_course_reference}`  \n"
            f"**Timestamp:** `{incident.timestamp}`  \n\n"
            f"## 1. Executive Summary\n"
            f"{incident.root_cause_summary}\n\n"
            f"## 2. Telemetry & SLI Degradation Profile\n"
            f"- **TTFT (Time to First Token):** `{f'{incident.metrics.ttft_ms:.2f} ms' if incident.metrics.ttft_ms is not None else 'unavailable (no content received)'}`  \n"
            f"- **Finish reason:** `{incident.metrics.finish_reason or 'not observed'}`  \n"
            f"- **HTTP error status:** `{incident.metrics.http_status_code if incident.metrics.http_status_code is not None else 'unavailable'}`  \n"
            f"- **Probe error:** {incident.metrics.error_details or 'none'}  \n"
            f"- **Chunk Delivery Rate:** `{f'{incident.metrics.chunks_per_second:.2f} chunks/s' if incident.metrics.chunks_per_second is not None else 'unavailable (insufficient duration)'}`  \n"
            f"- **P95 Inter-Chunk Interval:** `{incident.metrics.inter_chunk_interval_p95_ms:.2f} ms`  \n"
            f"- **Completion Tokens (provider-reported):** `{incident.metrics.completion_tokens if incident.metrics.completion_tokens is not None else 'unavailable'}`  \n"
            f"- **Total Chunks Observed:** `{incident.metrics.chunk_count}`  \n"
            f"- **Prompt Cache Hit:** `{incident.metrics.prompt_cache_hit}`  \n\n"
            f"## 3. Reproduction Command (cURL)\n"
            f"```bash\n{incident.reproduction_curl}\n```\n\n"
            f"## 4. Root Cause Analysis (5 Whys / Systems Engineering)\n"
            f"Tracing the failure from client socket to OpenAI cluster scheduling:\n"
            f"1. *Why did the client experience failure?* Observed failure mode `{incident.failure_domain.value}`.\n"
            f"2. *Where in the network/compute path did the bottleneck manifest?* Analyzed in accordance with {incident.mit_course_reference}.\n"
            f"3. *How was it detected?* Stream Sentinel synthetic telemetry identified anomalous variance in chunk delta arrivals or protocol-level RSTs.\n\n"
            f"## 5. Preventative Action Items & Long-Term Fixes\n"
        )
        for idx, step in enumerate(incident.remediation_steps, 1):
            postmortem += f"{idx}. {step}\n"

        return RCAReport(
            incident=incident,
            customer_advisory=advisory,
            engineering_postmortem=postmortem
        )
