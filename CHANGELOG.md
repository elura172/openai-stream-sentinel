# Changelog

## 0.2.0

- Detect clean EOF before model completion; bound the entire stream, including trickled content.
- Disable SDK retries so one probe measures one attempt.
- Return nonzero probe exit codes after exporting failure reports.
- Preserve request IDs, errors, HTTP status, finish reason and provider usage.
- Separate chunks from tokens; report unavailable measurements explicitly.
- Replace invented root-cause details and promotional report text with observed evidence and scoped hypotheses.
- Add real HTTP/SDK/CLI integration tests, a worked incident, a reproducible local harness and CI package checks.
- Publish breaking report-schema changes documented in the README migration table.

The original 0.1.0 implementation was a synthetic diagnostic prototype. Its
production, automated root-cause and course-grounding claims were not evidence
of those capabilities; see the claims audit and archived baseline reproduction.
