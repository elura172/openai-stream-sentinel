# OpenAI Stream Sentinel (`openai-stream-sentinel`)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MIT OpenCourseWare Grounded](https://img.shields.io/badge/MIT_OCW-6.033_|_6.172_|_6.824-red.svg)](https://ocw.mit.edu)

> **Enterprise API Streaming Observability & Automated Root Cause Analysis (Auto-RCA) Canary.**  
> *Engineered specifically to diagnose low-volume, high-difficulty distributed systems anomalies in mission-critical OpenAI API workloads.*

---

## Architecture Overview

At enterprise scale, API breakdowns are rarely simple syntax errors. They are **distributed systems boundary bugs**—proxy buffer bloat, prompt cache invalidations, rate-limit thundering herds, TCP socket resets, and agentic tool execution timeouts.

`openai-stream-sentinel` is a command-line prototype that records client-side stream timing and creates heuristic diagnostic reports. It does not observe or isolate individual network hops:

```
Enterprise Client Stack                     Intermediate Network / WAF      OpenAI Inference Cluster
┌───────────────────────┐                  ┌─────────────────────────┐     ┌────────────────────────┐
│ Enterprise App / Agent│                  │ Zscaler / Palo Alto / WAF│     │ vLLM / Schedulers      │
│ Async Client Pool     │ ──[HTTP/2 SSE]─► │ Cloudflare CDN / Ingress │ ──►│ Prefix Prompt Cache    │
│ Event Loop Cadence    │                  │ TCP Window / Buffer     │     │ GPU Attention Kernels  │
└───────────────────────┘                  └─────────────────────────┘     └────────────────────────┘
           ▲                                            ▲                              ▲
           │                                            │                              │
           └────────────────── openai-stream-sentinel ─────────────────────────────────┘
                               • Monotonic-clock TTFT & Inter-chunk interval tracking
                               • Heuristic cache signal from prompt length and TTFT
                               • Dual-Format Auto-RCA Generation (Customer + Engineering)
```

---

## Theoretical Grounding: MIT OpenCourseWare

This prototype applies ideas from distributed systems and performance engineering coursework to a diagnostic probe. Its offline scenarios are synthetic; a live probe measures only the client-visible stream and cannot establish which network or service component caused an anomaly:

1. **[MIT 6.033: Computer System Engineering](https://ocw.mit.edu/courses/6-033-computer-system-engineering-spring-2018/)**
   - *The End-to-End Argument & Buffer Bloat:* Diagnoses intermediate network buffering where enterprise firewalls convert fluid HTTP/2 chunked SSE streams into bursty, high-latency TCP frames.
   - *Fault Tolerance & Backpressure:* The RCA recommends jittered backoff for rate limits. The current client does not implement retries or rate limiting.
2. **[MIT 6.172: Performance Engineering of Software Systems](https://ocw.mit.edu/courses/6-172-performance-engineering-of-software-systems-fall-2018/)**
   - *Tail Latency Distributions (P95/P99):* Reports percentiles of observed inter-chunk intervals. These measurements cannot distinguish event-loop delay from network or server delay.
   - *Spatial & Temporal Cache Locality:* Uses prompt length and TTFT as a heuristic for possible cache effects. It does not currently consume authoritative cached-token usage data.
3. **[MIT 6.824: Distributed Systems](https://ocw.mit.edu/courses/6-824-distributed-systems-spring-2020/)**
   - *RPC Semantics & Deadlines:* The tool-timeout case is a synthetic profile; the live probe does not execute tools or measure downstream RPC deadlines.
4. **[MIT 6.858: Computer Systems Security](https://ocw.mit.edu/courses/6-858-computer-systems-security-fall-2014/)**
   - Security is a relevant design concern, but the current probe does not execute tools or validate tool payload schemas.

---

## Enterprise Failure Matrix

`openai-stream-sentinel` includes a live probe and six synthetic offline scenarios. Offline timing is simulated and incurs no API usage; the measured timings vary slightly with local scheduling:

| Scenario Flag | Failure Domain | Simulated Enterprise Root Cause | Mitigating Architecture |
|---|---|---|---|
| `healthy` | `HEALTHY` | Sub-250ms TTFT, smooth 22ms inter-token cadence, nominal prompt cache lookup. | Baseline SLI verification |
| `buffer-bloat` | `PROXY_BUFFER_BLOAT` | Palo Alto / Zscaler WAF buffers chunks for 1.8s, then flushes 35 tokens instantly. | `X-Accel-Buffering: no`, TCP window tuning |
| `cache-miss` | `PROMPT_CACHE_EVICTION` | Dynamic timestamp prepended at byte 0 of 4.5k prompt, causing cold prefill (TTFT > 2.1s). | Static prefix template restructuring |
| `rate-limit` | `RATE_LIMIT_BURST` | 15 concurrent agent workers exhaust TPM quota; naive retries cause 429 thundering herd. | Decorrelated Jitter Backoff + Client Leaky-Bucket |
| `tcp-rst` | `TCP_RST_TRUNCATION` | Enterprise ingress reverse proxy drops connection mid-stream due to 60s idle timeout. | HTTP/2 keep-alive, TCP probes, token resumption |
| `tool-timeout` | `TOOL_TIMEOUT_SCHEMA_MISMATCH` | Multi-step agent tool execution hangs beyond 10s client deadline and emits non-conforming JSON. | Session idempotency keys & Pydantic schema guards |

---

## Dual-Format Auto-RCA Output

For an observed or simulated degradation, the engine generates two report sections. Root-cause labels and remediation text are heuristic guidance and require validation against system-side evidence before being treated as findings:

1. **Customer advisory draft:** Suggested workarounds for review before external distribution.
2. **Engineering diagnostic draft:** Collected client telemetry, a reproduction suggestion, and potential follow-up actions.

---

## Quickstart

### Prerequisites
- Python 3.12+
- `uv` (recommended) or standard `pip`

```bash
# Clone the repository
git clone https://github.com/elura172/openai-stream-sentinel.git
cd openai-stream-sentinel

# Install dependencies and sync virtual environment
uv sync
```

### 1. Run Offline Failure Matrix (Zero API Cost)
Run all 5 simulated breakdown scenarios to see the Rich terminal dashboard and diagnostics:
```bash
uv run sentinel run --scenario all
```

Simulate an enterprise proxy buffer bloat incident and export the dual-format Markdown RCA:
```bash
uv run sentinel run --scenario buffer-bloat --out rca-incident.md
```

Simulate a prompt cache eviction on a 4,500 token prompt:
```bash
uv run sentinel run --scenario cache-miss
```

### 2. Run Live Probe Against OpenAI API
*(Requires `OPENAI_API_KEY` in environment)*
```bash
export OPENAI_API_KEY="sk-..."
uv run sentinel probe --model gpt-4o --prompt "Analyze distributed system failure modes"
```

Each probe makes one request with SDK retries disabled. `--timeout 30` sets the
total request-and-stream deadline in seconds, including time spent receiving
content. `OPENAI_BASE_URL` can point the SDK at an alternative compatible endpoint.

A live stream must deliver a `finish_reason` for choice 0 to count as completed.
The SDK consumes the SSE `[DONE]` marker internally; the probe checks the model's
finish event. A stream ending before that event is a failure even if HTTP closes
cleanly. Missing optional usage data leaves token counts unavailable. A finish
reason records protocol completion, not an assessment of answer quality.

`probe` exits **0** for a healthy report and **1** for a detected anomaly or request
failure. Reports requested with `--out` are written before the diagnostic exit
status is returned. Offline `run` and `suite` commands exit 0 when their synthetic
scenarios execute successfully, including intentionally injected failures.

### 3. Run Automated Test Suite
```bash
uv run pytest
```

The tests include a temporary loopback HTTP server exercising the real OpenAI SDK
and CLI. They require local socket binding, use a dummy key, and make no requests
to OpenAI. Cases include SSE content and usage, missing usage, premature EOF,
broken HTTP chunk framing, idle and total deadlines, and HTTP 429/503.

### Metric migration from the initial 0.1.0 implementation

Callers consuming `StreamingMetrics` should update these fields:

| Previous field | Current field and meaning |
|---|---|
| `tokens_per_second` | `chunks_per_second`: delivery chunks per second; `None` for fewer than two chunks or windows under 10 ms |
| `total_tokens` | `chunk_count` for delivery events; `completion_tokens` for provider-reported token usage |
| `jitter_*_ms` | `inter_chunk_interval_*_ms`: interval mean, sample standard deviation, maximum, and nearest-rank P95/P99 |
| `ttft_ms` | Nullable; `None` when no content arrived |
| `tcp_handshake_ms` | Nullable; the SDK probe cannot measure TCP handshake timing |
| `prompt_cache_hit` | Nullable timing heuristic; `None` means insufficient signal |

Additional fields include interval sample count, `finish_reason`, `error_occurred`,
`error_details`, and `http_status_code`. A generic failed request is classified as
`STREAM_ERROR` when the available evidence does not support a narrower domain.

---

## Project Structure

```
openai-stream-sentinel/
├── pyproject.toml              # Project metadata & CLI script bindings
├── README.md                   # Systems design & MIT OCW grounding documentation
├── src/
│   └── openai_stream_sentinel/
│       ├── __init__.py
│       ├── cli.py              # Rich terminal dashboard & CLI runner
│       ├── models.py           # Pydantic schemas for telemetry, incidents & RCAs
│       ├── telemetry.py        # Monotonic-clock timings and inter-chunk interval statistics
│       ├── simulator.py        # 5 deterministic enterprise failure profiles
│       ├── canary.py           # Probe orchestration (Live & Simulated)
│       └── rca_engine.py       # Dual-format Auto-RCA generation
└── tests/
    ├── test_http_probe.py      # Real SDK and CLI against a local HTTP/SSE server
    ├── test_telemetry.py       # Math and percentile verification
    ├── test_simulator.py       # Simulation profile verification
    └── test_rca_engine.py      # RCA formatting and advisory tests
```

---

## License

MIT © [Paul Trafford](https://github.com/elura172).
