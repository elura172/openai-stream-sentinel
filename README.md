# OpenAI Stream Sentinel

[![CI](https://github.com/elura172/openai-stream-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/elura172/openai-stream-sentinel/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Python command-line diagnostic tool for streaming Chat Completions requests.
It captures client-visible timing, completion state, usage, errors, and request
IDs, then produces customer and engineering drafts for review.

Independent portfolio project; no affiliation with OpenAI or MIT is implied.
The report generator uses rules and templates, not an LLM. No production
customer deployment or customer-impact reduction is claimed.

**Start with the [worked incomplete-stream investigation](docs/investigations/incomplete-stream.md).**
It demonstrates a real bug in this project's original probe: a clean HTTP close
was mistaken for successful model completion. The evidence is a controlled local
HTTP reproduction through the actual OpenAI SDK, not an OpenAI service incident.

## What is implemented

- One bounded SDK request, with automatic retries disabled.
- Detection of missing model finish events, request failures, transport errors,
  idle timeouts, and a total deadline that also bounds continuously arriving content.
- Provider-reported completion-token usage when available; delivery chunks counted separately.
- Request IDs and HTTP error status for correlation, without inventing unseen network events.
- Markdown report export before returning a nonzero diagnostic exit code.
- Loopback HTTP tests exercising the real SDK parser and the CLI as a subprocess.
- Six optional synthetic timing/error profiles for exploring report behavior.

```text
Your CLI -> OpenAI SDK -> configured Chat Completions endpoint
     |          |
     +-- timings, content events, finish reason, usage, request ID, errors
                |
         rule-based assessment -> customer draft + engineering evidence
```

The client cannot observe server internals, individual network hops, TCP handshake
timing through the SDK, downstream tool execution, or actual prompt-cache hits
from timing alone. Latency thresholds are local heuristics, not OpenAI SLOs.
There is no scheduler, alert-routing service, dashboard, retry policy, tool runner,
or resumable stream implementation. See the [claims audit](docs/claims-audit.md).

## Reproduce without an API key

```bash
git clone https://github.com/elura172/openai-stream-sentinel.git
cd openai-stream-sentinel
git checkout v0.2.0
uv sync --locked
uv run --no-sync pytest -q
uv run --no-sync python scripts/reproduce_incomplete_stream.py --out /tmp/sentinel-incident
```

The last command starts a temporary server bound only to `127.0.0.1`, supplies a
dummy key, and exercises both the Python runner and CLI. It writes `result.json`,
`report.json`, `cli-report.md`, and `cli-output.txt`. Expected result: two local
requests, `STREAM_ERROR`, and CLI exit 1. No OpenAI API call is made.

Tests require permission to bind local sockets. CI exercises Python 3.12, 3.13,
and 3.14 on Linux and uploads JUnit results and fresh reproduction artifacts.
The package job builds and smoke-tests both wheel and source distribution.

## Run against an API endpoint

Set `OPENAI_API_KEY` in your environment, then run:

```bash
uv run --no-sync sentinel probe --model gpt-4o --prompt "Ping" --timeout 30 --out incident.md
```

A live API request can incur provider usage charges. `OPENAI_BASE_URL` selects a
compatible alternative endpoint; only send credentials to a trusted endpoint.
The total deadline starts immediately before the request. A live stream must
produce a `finish_reason` for choice 0. The SDK consumes `[DONE]` internally;
this tool checks the model finish event, not raw `[DONE]` framing. A finish event
establishes protocol completion, not answer quality. Usage can be missing even
when completion is valid.

Exit codes: `probe` returns **0** when no configured anomaly is detected, **1** for
a diagnostic failure/anomaly or execution error, and argparse returns **2** for
invalid command syntax. Reports requested with `--out` are exported before a
diagnostic failure returns. Raw provider errors may contain sensitive context;
review a report before sharing it.

## Synthetic profiles

```bash
uv run --no-sync sentinel run --scenario all
uv run --no-sync sentinel run --scenario buffer-bloat --out synthetic-report.md
```

| Flag | Injected behavior |
|---|---|
| `healthy` | Regular content delivery |
| `buffer-bloat` | A long pause followed by short delivery intervals |
| `cache-miss` | Delayed first content with an assigned large prompt size |
| `rate-limit` | A synthetic rate-limit error |
| `tcp-rst` | A synthetic connection-reset error after partial content |
| `tool-timeout` | A synthetic tool-timeout error string; no tool is executed |

`run` and `suite` exit 0 when the requested demonstrations execute, including
intentionally injected errors. They are demonstrations, not substitutes for
`pytest`. Timing varies with the operating system's scheduler. Historical domain
names such as `PROXY_BUFFER_BLOAT` and `PROMPT_CACHE_EVICTION` remain diagnostic
pattern labels, not proof of a proxy or cache cause.

## Upgrade from the initial 0.1.0 schema

Version 0.2.0 changes the report schema to match what is actually measured:

| Previous field | Replacement / current meaning |
|---|---|
| `tokens_per_second` | `chunks_per_second`; nullable for fewer than two chunks or windows under 10 ms |
| `total_tokens` | `chunk_count` for delivery events; `completion_tokens` for provider usage |
| `jitter_*_ms` | `inter_chunk_interval_*_ms`; mean, sample standard deviation, max, nearest-rank P95/P99 |
| `ttft_ms` | Nullable when no content arrived |
| `tcp_handshake_ms` | Nullable; unavailable in the SDK probe |
| `prompt_cache_hit` | Nullable, unverified timing heuristic |
| `mit_course_reference` | `diagnostic_basis`; the actual rule used |
| `reproduction_curl` | `reproduction_command`; synthetic invocation or generic connectivity check |

Additional fields include interval sample count, `probe_mode`, `finish_reason`,
`request_id`, `error_occurred`, `error_details`, and `http_status_code`.
`prompt_tokens` is a rough character-based estimate until provider usage arrives.
`connect_start_ms` is an arbitrary monotonic-clock reading, not a wall-clock timestamp.
Severity values are triage hints; the probe does not measure service-wide impact.

## Release verification

The GitHub release includes a wheel, source distribution, locked runtime
requirements, and SHA-256 checksums. The source tag contains the full `uv.lock`.
See [release verification](docs/release.md) for build, installation, and checksum
commands. Reproducibility here means pinned inputs and repeatable checks;
incident IDs, wall-clock timestamps, and local timing measurements vary per run.

## Application evidence

The [role-to-evidence map](docs/application-evidence.md) links this work to the
OpenAI Senior Support Engineer posting and marks experience requirements this
project cannot establish. The project demonstrates troubleshooting and support
communication through inspectable artifacts, without presenting lab work as
production incident ownership.

## License

[MIT](LICENSE), copyright 2026 elura172.
