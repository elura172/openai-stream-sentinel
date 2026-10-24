"""Build diagnostic drafts from observations without inventing a root cause."""

import datetime
import json
import shlex
import uuid

from .models import FailureDomain, SeverityLevel, StreamingMetrics, IncidentRecord, RCAReport


# Domain names are retained for compatibility; they describe patterns, not proven causes.
GUIDANCE = {
    FailureDomain.HEALTHY: (
        "No probe error or configured diagnostic pattern was detected. This does not establish an application SLO or service-wide health.",
        "No error and no matching timing heuristic",
        ["Compare repeated probes with the application's own latency and completion objectives."],
    ),
    FailureDomain.PROXY_BUFFER_BLOAT: (
        "A long inter-chunk interval was observed. Buffering, server delay, network delay, and local scheduling remain possible explanations.",
        "P95 interval > 200 ms or maximum interval > 1000 ms",
        ["Compare the same bounded request over the normal route and an approved direct route.",
         "Correlate client timings with proxy and service logs before changing buffering or timeout settings."],
    ),
    FailureDomain.PROMPT_CACHE_EVICTION: (
        "High time to first content was observed with a long prompt. Cache behavior is unconfirmed; timing alone cannot identify eviction.",
        "Prompt size >= 2048 tokens and TTFT > 1400 ms (heuristic)",
        ["Compare equivalent prompts and inspect provider-reported cached-token usage separately.",
         "Check server and network timing before attributing the delay to prompt caching."],
    ),
    FailureDomain.RATE_LIMIT_BURST: (
        "A rate-limit signal was reported. The quota category, request concurrency, and effect of retries are not established by this probe.",
        "HTTP 429 or an explicit rate-limit error signal",
        ["Inspect the response error and quota information before choosing a retry policy.",
         "For transient rate limits, use bounded backoff consistent with the response guidance; do not retry exhausted billing quota blindly."],
    ),
    FailureDomain.TCP_RST_TRUNCATION: (
        "A connection-reset or truncation signal was reported. The originating network hop and timeout cause are unknown.",
        "Explicit reset or truncation error signal",
        ["Preserve partial output as incomplete and correlate the failure with transport logs.",
         "Review retry safety before sending another request; this probe does not implement stream resumption."],
    ),
    FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH: (
        "A tool-related error signal was reported. This probe does not execute tools or validate their return schemas.",
        "Explicit tool timeout or schema error signal",
        ["Inspect the tool runner's deadline, dispatch record, and actual return payload.",
         "Verify idempotency before repeating a tool with side effects."],
    ),
    FailureDomain.STREAM_ERROR: (
        "The streaming request failed. The available client telemetry does not identify a more specific failure domain.",
        "Recorded request, stream, deadline, or missing-finish error",
        ["Correlate the request ID, HTTP status, error, and completion state with service logs.",
         "Treat partial content as incomplete; retry only when safe for the calling application."],
    ),
}

SCENARIOS = {
    FailureDomain.HEALTHY: "healthy",
    FailureDomain.PROXY_BUFFER_BLOAT: "buffer-bloat",
    FailureDomain.PROMPT_CACHE_EVICTION: "cache-miss",
    FailureDomain.RATE_LIMIT_BURST: "rate-limit",
    FailureDomain.TCP_RST_TRUNCATION: "tcp-rst",
    FailureDomain.TOOL_TIMEOUT_SCHEMA_MISMATCH: "tool-timeout",
}


class RCAEngine:
    @staticmethod
    def diagnose(metrics: StreamingMetrics, meta: dict) -> IncidentRecord:
        domain = metrics.inferred_domain
        summary, basis, steps = GUIDANCE[domain]
        model = meta.get("model", "gpt-4o")
        simulation = "scenario" in meta
        mode = "SIMULATION" if simulation else meta.get("mode", "UNSPECIFIED")
        indicators = {
            "http_status": metrics.http_status_code,
            "error": metrics.error_details,
            "request_id": metrics.request_id,
            "finish_reason": metrics.finish_reason,
            "chunks_received": metrics.chunk_count,
            "ttft_ms": metrics.ttft_ms,
            "max_inter_chunk_interval_ms": metrics.inter_chunk_interval_max_ms,
            "interval_sample_count": metrics.inter_chunk_interval_sample_count,
        }
        if simulation:
            indicators["synthetic_scenario"] = meta["scenario"]
            reproduction = f"sentinel run --scenario {SCENARIOS[domain]}"
        else:
            # This is deliberately a generic connectivity check, not a replay of private prompts.
            payload = shlex.quote(json.dumps({"model": model, "stream": True,
                                             "messages": [{"role": "user", "content": "Ping"}]}))
            reproduction = (
                'curl --no-buffer --max-time 30 "${OPENAI_BASE_URL:-https://api.openai.com/v1}/chat/completions" \\\n'
                '  -H "Authorization: Bearer $OPENAI_API_KEY" \\\n'
                "  -H 'Content-Type: application/json' \\\n"
                f"  --data {payload}"
            )
        severity = (SeverityLevel.INFORMATIONAL if domain == FailureDomain.HEALTHY else
                    SeverityLevel.SEV2 if metrics.error_occurred else SeverityLevel.SEV3)
        return IncidentRecord(
            incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            target_model=model, failure_domain=domain, severity=severity,
            probe_mode=mode, diagnostic_basis=basis, root_cause_summary=summary,
            metrics=metrics, telemetry_indicators=indicators,
            reproduction_command=reproduction, remediation_steps=steps,
        )

    @staticmethod
    def generate_report(incident: IncidentRecord) -> RCAReport:
        metrics = incident.metrics
        steps = "\n".join(f"- {step}" for step in incident.remediation_steps)
        ttft = "unavailable (no content received)" if metrics.ttft_ms is None else f"{metrics.ttft_ms:.2f} ms"
        rate = "unavailable (insufficient duration)" if metrics.chunks_per_second is None else f"{metrics.chunks_per_second:.2f} chunks/s"
        # Encoding evidence as indented JSON keeps error text out of Markdown structure.
        evidence = "\n".join("    " + line for line in json.dumps(incident.telemetry_indicators, indent=2).splitlines())
        advisory = (
            f"### Customer advisory draft — {incident.incident_id}\n\n"
            f"**Source:** {incident.probe_mode}  \n"
            f"**Status:** {'No configured anomaly detected' if not metrics.error_occurred and incident.failure_domain == FailureDomain.HEALTHY else 'Investigation required'}  \n\n"
            f"{incident.root_cause_summary}\n\n"
            f"#### Suggested next steps\n{steps}\n\n"
            "*This automatically generated draft has not been independently validated. "
            "It is not a communication from OpenAI support.*"
        )
        engineering = (
            f"# Internal Diagnostic Draft: {incident.incident_id}\n\n"
            f"**Target model:** `{incident.target_model}`  \n"
            f"**Source:** `{incident.probe_mode}`  \n"
            f"**Diagnostic pattern:** `{incident.failure_domain.value}`  \n"
            f"**Triage hint:** `{incident.severity.value}` (service impact not measured)  \n"
            f"**Timestamp:** `{incident.timestamp}`  \n\n"
            f"## Assessment\n{incident.root_cause_summary}\n\n"
            f"**Rule:** {incident.diagnostic_basis}\n\n"
            f"## Observations\n"
            f"- **TTFT (Time to First Token):** `{ttft}`  \n"
            f"- **Chunk delivery rate:** `{rate}`  \n"
            f"- **P95 inter-chunk interval:** `{metrics.inter_chunk_interval_p95_ms:.2f} ms` (n={metrics.inter_chunk_interval_sample_count})  \n"
            f"- **Completion tokens (provider-reported):** `{metrics.completion_tokens if metrics.completion_tokens is not None else 'unavailable'}`  \n"
            f"- **HTTP error status:** `{metrics.http_status_code if metrics.http_status_code is not None else 'unavailable'}`  \n\n"
            f"{evidence}\n\n"
            "## Reproduction aid\n"
            "Synthetic scenarios repeat an injected pattern. Live commands are generic connectivity checks; "
            "they do not reproduce the original prompt, route, or root cause automatically.\n\n"
            f"```bash\n{incident.reproduction_command}\n```\n\n"
            f"## Follow-up\n{steps}\n"
        )
        return RCAReport(incident=incident, customer_advisory=advisory, engineering_postmortem=engineering)
