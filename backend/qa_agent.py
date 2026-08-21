"""Q&A over reconciliation results.

Phase 4 scope only: a small set of pattern-matched questions, each answered
by a direct query against the audit DB (audit.py) — real data, no LLM.
Phase 5 replaces this with a free-form Ollama agent that has tool access to
the same audit.py query functions; the /qa endpoint contract doesn't change.
"""

import json
import re
from decimal import Decimal, InvalidOperation

import audit

SUPPORTED_HELP = (
    "I can currently answer: match rate, exception count, match count, "
    "and unmatched bank entries over a given amount (e.g. 'unmatched bank "
    "entries over 1000'). Free-form questions arrive in Phase 5."
)


def answer(question, conn, run_id=None):
    """Returns {"answer": str, "sourced_from": [record_ids]}."""
    run_id = run_id or audit.latest_run_id(conn)
    if not run_id:
        return {"answer": "No reconciliation run found. Run /reconcile first.", "sourced_from": []}

    q = question.lower()

    if "match rate" in q:
        run = audit.get_run(conn, run_id)
        stats = json.loads(run["stats_json"])
        return {
            "answer": f"Match rate for run {run_id}: {stats['match_rate'] * 100:.1f}% "
                      f"({stats['matched']}/{stats['total_settlements']} settlements matched — "
                      f"{stats['rule_matched']} by rule, {stats['llm_matched']} by LLM).",
            "sourced_from": [run_id],
        }

    if "how many exception" in q or "exception count" in q:
        exceptions = audit.list_exceptions(conn, run_id)
        return {
            "answer": f"{len(exceptions)} exceptions in run {run_id}.",
            "sourced_from": [e["settlement_ref"] or e["bank_ref"] for e in exceptions],
        }

    if "how many match" in q or "match count" in q:
        matches = audit.list_matches(conn, run_id)
        return {
            "answer": f"{len(matches)} matched records in run {run_id}.",
            "sourced_from": [m["settlement_ref"] for m in matches],
        }

    threshold_match = re.search(r"unmatched bank entries? over\s*(?:rs\.?|₹|inr)?\s*([\d,]+(?:\.\d+)?)", q)
    if threshold_match:
        try:
            threshold = Decimal(threshold_match.group(1).replace(",", ""))
        except InvalidOperation:
            return {"answer": f"Couldn't parse an amount from that question. {SUPPORTED_HELP}", "sourced_from": []}

        exceptions = audit.list_exceptions(conn, run_id)
        bank_only = [e for e in exceptions if e["bank_ref"] and not e["settlement_ref"]]
        hits = []
        for e in bank_only:
            row = conn.execute(
                "SELECT * FROM bank_entries WHERE run_id = ? AND txn_id = ?",
                (run_id, e["bank_ref"]),
            ).fetchone()
            if row and Decimal(row["amount"]) > threshold:
                hits.append(dict(row))

        if not hits:
            return {"answer": f"No unmatched bank entries over Rs {threshold} in run {run_id}.", "sourced_from": []}
        lines = [f"  {h['txn_id']}: Rs {h['amount']} on {h['date']} ({h['narration']})" for h in hits]
        return {
            "answer": f"{len(hits)} unmatched bank entries over Rs {threshold} in run {run_id}:\n" + "\n".join(lines),
            "sourced_from": [h["txn_id"] for h in hits],
        }

    return {"answer": f"I don't understand that question yet. {SUPPORTED_HELP}", "sourced_from": []}
