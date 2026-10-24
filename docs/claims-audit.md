# Claims audit — 0.2.0

The audit covers the current README, CLI, models, report generator, simulation
labels, package metadata, and release description. Historical Git commits and
archived baseline evidence retain the original text to preserve provenance.

| Earlier claim or behavior | Evidence boundary | Change |
|---|---|---|
| Enterprise platform / mission-critical deployment | A local CLI and tests do not establish deployment or customer outcomes | Describe the implemented diagnostic tool |
| MIT grounding as a headline credential | Course links do not prove course completion, endorsement, or implementation correctness | Remove promotional course branding and replace report fields with actual diagnostic rules |
| Knowledge of OpenAI's inference stack and intermediate WAFs | The SDK sees one client stream | Replace the architecture diagram with the observable request path |
| Exact proxy, cache, worker-count, or timeout cause | Delays and errors do not locate a network hop or identify request concurrency | Remove invented telemetry defaults and use observations plus alternative explanations |
| Backoff, schemas, tool execution, and resumable streaming implemented | These were suggestions or injected strings, not implementations | Document absent capabilities; replace unsupported operational prescriptions with investigation steps |
| Support-team validated customer advice | No support team reviewed generated output | Label drafts as independent and unvalidated |
| “Exact reproduction” curl commands | Some omitted required messages, single-quoted the API-key variable, used the wrong model, or induced load | Generate one valid generic connectivity check with correct shell quoting, or an explicit synthetic scenario command |
| Token rate from chunk count | SDK chunks can contain multiple tokens | Separate chunks from provider token usage |
| Jitter / nanosecond precision / universal SLOs | The collector measures monotonic-clock intervals with platform-dependent resolution | Name intervals accurately and label thresholds as local references |
| HTTP EOF means model completion | A controlled local server reproduces partial output followed by clean EOF | Require a model finish event and return failure before a caller treats output as complete |
| SDK has no retries | The SDK supplied retries by default | Explicitly set `max_retries=0`; HTTP tests count requests |
| No-content requests have TTFT | No first content event exists | Return `None`, display unavailable |
| Error substring implies a specific cause | Text can mention unrelated tools or status numbers | Prefer structured HTTP status and narrow text fallback patterns |

The release still uses historical failure-domain names for compatibility. They
are heuristic labels. Cache status remains a timing heuristic, with no verified
cache-eviction claim. The Chat Completions probe does not cover Responses API
streaming, trace an entire distributed system, or validate content correctness.

Tests and the worked incident establish behavior in a controlled environment.
They do not demonstrate on-call tenure, ownership of customer outages, or latency
improvements on a production workload. CI results are linked from the repository;
a local passing run is never described as a hosted CI result.
