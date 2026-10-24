# OpenAI Stream Sentinel (`openai-stream-sentinel`)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MIT OpenCourseWare Grounded](https://img.shields.io/badge/MIT_OCW-6.033_|_6.172_|_6.824-red.svg)](https://ocw.mit.edu)

> **Enterprise API Streaming Observability & Automated Root Cause Analysis (Auto-RCA) Canary.**  
> *Engineered specifically to diagnose low-volume, high-difficulty distributed systems anomalies in mission-critical OpenAI API workloads.*

---

## Architecture Overview

At enterprise scale, API breakdowns are rarely simple syntax errors. They are **distributed systems boundary bugs**—proxy buffer bloat, prompt cache invalidations, rate-limit thundering herds, TCP socket resets, and agentic tool execution timeouts.

`openai-stream-sentinel` is an SRE/SSE diagnostic platform built to monitor, isolate, and auto-diagnose streaming completion anomalies across the enterprise egress path:

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
                               • Nanosecond-precision TTFT & Chunk Jitter Tracking
                               • KV Prompt Cache Hit/Miss Detection
                               • Dual-Format Auto-RCA Generation (Customer + Engineering)
```

---

## Theoretical Grounding: MIT OpenCourseWare

This system translates canonical distributed systems and performance engineering coursework into production diagnostic tooling:

1. **[MIT 6.033: Computer System Engineering](https://ocw.mit.edu/courses/6-033-computer-system-engineering-spring-2018/)**
   - *The End-to-End Argument & Buffer Bloat:* Diagnoses intermediate network buffering where enterprise firewalls convert fluid HTTP/2 chunked SSE streams into bursty, high-latency TCP frames.
   - *Fault Tolerance & Backpressure:* Implements and verifies Decorrelated Full-Jitter Exponential Backoff during rate-limit (HTTP 429) cascades, preventing client-side retry storms.
2. **[MIT 6.172: Performance Engineering of Software Systems](https://ocw.mit.edu/courses/6-172-performance-engineering-of-software-systems-fall-2018/)**
   - *Tail Latency Distributions (P95/P99):* Measures non-parametric inter-token chunk arrival intervals to identify event loop blocking and packet latency spikes.
   - *Spatial & Temporal Cache Locality:* Evaluates Time-to-First-Token (TTFT) against prompt token volume to detect prompt prefix cache invalidation (cold prefill penalties).
3. **[MIT 6.824: Distributed Systems](https://ocw.mit.edu/courses/6-824-distributed-systems-spring-2020/)**
   - *RPC Semantics & Deadlines:* Evaluates client-side tool execution boundaries (Model Context Protocol / Function Calling) when downstream services exceed deadlines.
4. **[MIT 6.858: Computer Systems Security](https://ocw.mit.edu/courses/6-858-computer-systems-security-fall-2014/)**
   - *Sandboxed Privilege Separation & Schemas:* Verifies strict schema validation to eliminate malicious or malformed tool payload execution.

---

## Enterprise Failure Matrix

`openai-stream-sentinel` ships with both **live canary probes** and a **zero-token, offline deterministic simulation suite** covering the 5 most common enterprise breakdown modes:

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

Whenever a degradation or failure is detected, the engine generates two synchronized deliverables:

1. **External Enterprise Customer Advisory:** Concise, calming, non-blaming communication with actionable workarounds that enterprise sysadmins can apply immediately.
2. **Internal Engineering Post-Mortem:** Exhaustive root-cause analysis with exact reproduction `cURL` commands, telemetry SLI degradation profiles, and long-term preventative action items.

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

### 3. Run Automated Test Suite
```bash
uv run pytest
```

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
│       ├── telemetry.py        # Nanosecond timer, jitter statistics & percentile math
│       ├── simulator.py        # 5 deterministic enterprise failure profiles
│       ├── canary.py           # Probe orchestration (Live & Simulated)
│       └── rca_engine.py       # Dual-format Auto-RCA generation
└── tests/
    ├── test_telemetry.py       # Math and percentile verification
    ├── test_simulator.py       # Simulation profile verification
    └── test_rca_engine.py      # RCA formatting and advisory tests
```

---

## License

MIT © [Paul Trafford](https://github.com/elura172).
