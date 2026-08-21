# Glossary

- **Settlement record** — a Razorpay-side payout entry (`settlement.csv`).
- **Bank statement entry** — a bank-posted transaction (`bank_statement.csv`),
  may include free-text narration and a date that drifts from settlement date.
- **Match** — a settlement record and bank entry linked with a confidence
  tier: `exact`, `fuzzy-date`, `fuzzy-amount`, or `llm-reasoned`.
- **Exception** — a record neither rules nor the LLM could confidently
  resolve; left for human review, never force-matched.
- **Match rate** — matched records / total records in the batch, always
  reported on a batch the rules weren't tuned against.
- **Audit log** — per-decision record of match/exception outcome, the
  source record IDs, and the reason (rule name or LLM reasoning text).
- **Q&A agent** — Ollama-backed chat layer that answers questions about
  reconciliation results by reading the audit log/matches/exceptions; never
  answers from data outside that source of truth.
