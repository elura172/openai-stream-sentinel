# Senior Support Engineer: project evidence

Reviewed 2026-10-24 against OpenAI's [Toronto posting](https://openai.com/careers/senior-support-engineer-toronto-ontario-remote/).
The employer page lists Ontario remote, with an expected transition to an office.
[Application link](https://jobs.ashbyhq.com/openai/6aa78bd0-98d6-4671-a98f-d1010c627eb5/application).

This map assesses this repository only; it does not assess the applicant's full employment history.

| Role emphasis | Evidence here | Scope |
|---|---|---|
| Difficult API troubleshooting | [Worked EOF investigation](investigations/incomplete-stream.md), real SDK and HTTP regression cases | Demonstrated in a local lab |
| Python automation | [Bounded probe](../src/openai_stream_sentinel/canary.py), report export, subprocess exit checks | Demonstrated |
| Operational monitoring | Timing, completion, usage, error and request-ID collection | Partial; no scheduled monitoring or alert routing |
| Incident documentation and communication | Technical investigation and customer update in the worked case | Demonstrated as an exercise |
| Release readiness | Locked dependencies, Python CI matrix, installed-package smoke checks | Demonstrated when linked CI passes |
| 8+ years of production operations | No employment history in this repo | Unverified here |
| High-severity incident leadership and cross-team coordination | No real customer incident or coordination record | Unverified here |
| Cloud, container, database and infrastructure operations | This project is a local CLI and loopback server | Not established here |
| Relevant degree and coverage availability | Not software capabilities | Unverified here |

Suggested project wording:

> Built a Python streaming diagnostic tool and a local HTTP failure harness using
> the OpenAI SDK. Reproduced a false-success bug on incomplete streams, added
> completion checks and deadlines, and produced customer and engineering
> investigation artifacts with automated regression coverage.

Do not replace the unverified rows with claims inferred from this project's
name, dependencies, synthetic scenarios, or generated reports.
