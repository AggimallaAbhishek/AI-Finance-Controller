# ADR-001: Hybrid rules + LLM reconciliation

**Status:** Accepted

## Context

Reconciling settlement records against bank statement entries needs to be
fast and deterministic for the clear cases, but bank narration is free text
and dates/amounts can drift — some records need judgment, not just a rule.

## Decision

Match in two tiers:
1. **Rules first** — exact match, then fuzzy tiers (date-tolerance,
   amount-tolerance) resolve every confident case deterministically.
2. **Ollama for the ambiguous middle** — records the rules can't confidently
   call go to an LLM with both full records (including bank narration) for
   a match/no-match verdict. The verdict and its reasoning are logged into
   the audit trail, and LLM-assisted matches are flagged distinctly from
   rule matches (`confidence: llm-reasoned`).

Records neither tier resolves fall to the exception list.

## Alternatives considered

- **Full-LLM matching** — rejected: non-determinism and hallucinated
  "matches" would break the honesty bar the reconciliation is scored on.
- **Rules-only** — rejected: wastes the LLM's ability to reason over
  free-text narration, and would push more real matches into exceptions.

## Consequences

- Every match is traceable to either a specific rule or a logged LLM
  reasoning trace — see the audit log (Phase 3).
- The Q&A agent (Phase 5) reads this same output as its source of truth and
  never invents numbers.
