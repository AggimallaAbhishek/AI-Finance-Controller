# Changelog

## v1.0 — 2026-08-22

Initial build, per `project_plan.md` (Phases 0–8). Hackathon-submission
complete.

- Synthetic settlement/bank data generator with a dev-only ground-truth
  answer key for validation
- Hybrid reconciliation engine: deterministic rule tiers (exact, fuzzy-date,
  fuzzy-amount) plus an Ollama-reasoned tier for the ambiguous middle
- SQLite audit trail, queryable by record ID, tracing every decision to its
  source rows
- FastAPI backend: reconciliation, matches/exceptions/audit endpoints,
  free-form Q&A via Ollama tool-calling
- React dashboard: match-rate summary, browsable exception list, chat panel
- Validated 90% match rate / 66/66 ground-truth-correct on both the dev
  batch and an independent held-out batch (`docs/PHASE7-INTEGRATION-TEST.md`)
- Full architecture review and systematic-debugging passes; findings fixed
  and logged (`docs/BUILD-CHALLENGES.md`)

See `project_plan_v2.md` for planned features and improvements beyond v1.0.
