# Worked investigation: partial stream reported as healthy

**Type:** controlled support-engineering exercise, not a customer outage.  
**Recorded:** 2026-10-24, approximately 10:18 UTC.  
**Affected component:** this project's original Chat Completions probe and CLI.  
**Impact demonstrated:** a truncated answer could be reported as healthy and return exit 0 to a calling script. No production impact was measured.

## Symptom and reproduction

A loopback HTTP server returns status 200, one valid SSE content event, and then
closes the HTTP connection cleanly. It sends neither a model `finish_reason` nor
a `[DONE]` marker. The original client reports success despite receiving only
partial content.

The [standalone harness](../../scripts/reproduce_incomplete_stream.py) exercises
the actual OpenAI SDK twice: once through the Python runner and once through the
CLI subprocess. Both requests use a dummy key and the same local endpoint. The
harness records request count, source fingerprint, Python/SDK versions, structured
report, Markdown export, stdout, and subprocess exit code.

The baseline and corrected runs both used **Python 3.13.5 and OpenAI SDK 3.37.0**.
This controls for SDK differences while comparing project source revisions.

| Observation | Original `b65e4c4` | Corrected `94df803` |
|---|---|---|
| HTTP status served | 200 | 200 |
| Content events per request | 1 | 1 |
| Model finish event / `[DONE]` | Neither sent | Neither sent |
| Requests observed | 2 (runner + CLI) | 2 (runner + CLI) |
| Diagnostic domain | `HEALTHY` | `STREAM_ERROR` |
| CLI exit code | 0 | 1 |
| Markdown report exported | Yes | Yes |
| Correlation ID retained | Not collected | `local-incomplete-stream-001` |

Raw evidence: [baseline result](../evidence/baseline/result.json),
[corrected result](../evidence/current/result.json),
[baseline report](../evidence/baseline/report.json),
[corrected report](../evidence/current/report.json), and
[corrected CLI report](../evidence/current/cli-report.md).
The original reports are archived verbatim and contain assertions removed from
current templates. They are evidence of the defect, not current project claims.
Each `result.json` records the tested source commit and SHA-256 fingerprint of
the package's Python sources. Later documentation commits do not change that
source fingerprint. Timings and incident IDs are snapshots, not benchmarks.

## Competing explanations

| Explanation | Check | Conclusion |
|---|---|---|
| Authentication or provider rejection | The fixture returns 200 and valid content; the SDK parses it | Does not explain this reproduction |
| Invalid JSON or SSE framing | The content event is valid and one chunk is recorded | Does not explain the false success |
| Missing usage alone indicates failure | A separate real-HTTP test completes with a finish event but no usage | Usage is optional and is not the completion criterion |
| A transport exception should have occurred | HTTP/1.0 close-delimited EOF is a valid transport end | An exception is not guaranteed for incomplete application content |
| A proxy reset or provider outage caused the close | The local fixture intentionally closes; no external service participates | No such production attribution is supported |
| Application code equated iterator exhaustion with completion | Original runner finishes unconditionally after iteration | Direct cause of this project's false-success result |

## Root cause in the probe

The original runner called `tracker.finish()` whenever SDK iteration ended.
It never checked whether the model had emitted a finish reason. The SDK can end
iteration normally at HTTP EOF; that is an observation about the transport,
not confirmation that the model response completed.

The CLI also returned zero after rendering an error report. A separate local
HTTP 503 regression reproduced that problem. Consequently, improving only the
report classification would still leave scripts unable to distinguish failures
by process status.

## Correction and validation

The runner now requires a finish reason for choice 0, records a missing-finish
error after premature EOF, closes the stream/client, and captures a response
request ID when present. The CLI exports the report before returning exit 1 for
a detected failure. HTTP errors and no-content results retain meaningful status
and error fields; TTFT stays unavailable when no content arrives.

The request has a total deadline and SDK retries are disabled. Those changes
preserve the first attempt's behavior and prevent a continuously trickling stream
from outliving the requested deadline. They do not implement automatic recovery.

Regression coverage in [test_http_probe.py](../../tests/test_http_probe.py)
exercises normal completion, missing usage, clean premature EOF, broken chunked
transfer, idle timeout, continuously arriving content past the total deadline,
and HTTP 429/503. CLI cases verify the report and exit code together. The
[CI workflow](../../.github/workflows/ci.yml) runs the suite on three Python
versions and uploads fresh reproduction results; consult its actual run status
rather than treating this document as proof of a green hosted run.

## Customer-facing update draft

> We reproduced a case where the diagnostic probe marked a partial streamed
> answer as successful after the connection closed. In the controlled test, the
> server had not sent a model completion event. The updated probe now marks this
> response incomplete, saves the diagnostic report, and returns a failure status
> to automation. We have not established why a connection in your environment
> might close early. Please preserve the request ID, timestamp, and relevant
> transport logs so we can correlate the event. Until the cause is known, treat
> partial answers as incomplete and check whether retrying is safe for your
> application before resubmitting.

This is a writing exercise, not a message sent to a real customer.

## Engineering handoff

- Local request ID: `local-incomplete-stream-001`.
- Trigger: one content event followed by clean HTTP EOF with no finish event.
- Reproduction ownership: the local fixture controls the close; the defect is
  in this project's completion check, not evidence of an SDK or OpenAI outage.
- Fix ownership: runner completion detection and CLI diagnostic exit behavior.
- Acceptance: partial content is retained as an observation; failure is exported;
  CLI exits 1; valid finish events still succeed without requiring usage.
- Follow-up outside this exercise: correlate a real incident with service/proxy
  logs; measure impact on the affected application; verify safe retry semantics.

## Reproduce the corrected result

```bash
uv sync --locked
uv run --no-sync python scripts/reproduce_incomplete_stream.py --out /tmp/sentinel-current
cat /tmp/sentinel-current/result.json
```

To compare the original source using the same installed dependency environment:

```bash
sentinel_root="$PWD"
git worktree add --detach /tmp/sentinel-original b65e4c4
(
  cd /tmp/sentinel-original
  PYTHONPATH="$PWD/src" "$sentinel_root/.venv/bin/python" \
    "$sentinel_root/scripts/reproduce_incomplete_stream.py" \
    --out /tmp/sentinel-original-evidence
)
```

The original is expected to report `HEALTHY` and exit 0 for the CLI. The corrected
source is expected to report `STREAM_ERROR` and exit 1. The reproduction script
itself exits successfully when it captures the experiment; the CLI's result is
recorded separately in `result.json`.
