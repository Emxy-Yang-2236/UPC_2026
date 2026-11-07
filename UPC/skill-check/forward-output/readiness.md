# Practice readiness note

**Decision: the requested synthetic practice answer and editable English manuscript are complete and ready for review. This is not a contest submission-readiness claim.**

Date: 2026-11-07. Manuscript version: practice 1, `paper/manuscript.md`.

The 8 and 12 W/K designs reach 30 °C in 268.76 and 179.18 s. Each removes 60.0 kJ. The dimensionless threshold relation is Gt*/C = ln6. Conductance changes of −10% and +10% give time changes of +11.11% and −9.09%; the faster design retains its ordering throughout the specified ranges. Every result is conditional on the stipulated law, not on experimental evidence.

| Readiness dimension | Actual status and evidence |
| --- | --- |
| Problem coverage | Complete: all eight recorded requirements have supported answers; see manuscript and `requirements.csv` |
| Physical consistency | Author self-check passed: exact solution, dimensions, first crossing, monotonicity, energy balance and limiting cases; `model.md` |
| Numerical implementation | One separate RK4 implementation actually ran for all six scenarios; finest maximum time error 9.85138e-7 s and heat error 1.60071e-10 J; `data/derived/summary.json` |
| Reproduction | A second calculation run reproduced the four derived outputs byte-for-byte; `data/derived/run-output.txt` and `reproduction-check.json` |
| Manuscript source | Complete English Markdown with a 120-word abstract, equations, results table, discussion, conclusion, source and AI use statement; all table rows match saved results at display precision |
| Mathematical formatting | Initial inline delimiters were inconsistent; repaired to `$...$` and `$$...$$`; source checks pass and prose parentheses remain intact |
| Visual/export review | No PDF or other export was requested or created; Markdown source was checked, not a rendered page layout |
| Review independence | Author self-check only; a coordinator spot-check identified the delimiter defect, but no independent full physics/manuscript review is claimed |
| Empirical evidence | None supplied or collected; numerical agreement is not experimental validation |
| Structural audit | `audit.json`: ready=true and integrity_ok=true; no errors or status findings; structural audit is not scientific or submission certification |
| Contest rules and format | Not applicable to this invented practice request; current official rules were not verified and no team number or A/B choice was fabricated |
| AI disclosure | AI assistance is explicitly stated; complete host interaction/tool transcript coverage remains unavailable; `ai-records/coverage.md` |
| Sending or uploading | None performed |

No unresolved blocker remains for answering this practice problem. Real-instrument prediction would require evidence about the single-temperature and constant-parameter assumptions. A real contest entry would separately require the actual current rules, team/problem assignment, requested export and layout checks, and a genuine complete AI interaction export. These were not requested or claimed here.

Final manuscript SHA-256: `7d35d507cbc5eed1f6a6e3d7918a0c5f8e4dfb530b2fd34549236b18053077c0`.

The first combined manuscript-check attempt failed because its checker compared a rounded conductance (13.2) to an unrounded binary float (13.200000000000001) by exact equality. The solver had completed successfully and the hash reproduction check had passed before that assertion. Comparing at the specified display precision corrected the checker; no physical result changed. This execution detail is preserved in `reproduction-check.json`, rather than being interpreted as a failed physical model.
