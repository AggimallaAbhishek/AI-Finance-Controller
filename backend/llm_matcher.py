"""Ollama-backed match/no-match verdicts for the reconciliation "ambiguous
middle" — records the rule tiers can't confidently resolve.

Note: Ollama's structured-output `format=` schema constraint is NOT honored
for cloud-routed models (verified during Phase 2 build — see
docs/BUILD-CHALLENGES.md). Instead we instruct JSON-only output in the
prompt and parse defensively.
"""

import json
import os
import re

import ollama

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b-cloud")

PROMPT_TEMPLATE = """You are reconciling a Razorpay settlement record against candidate bank statement entries. Bank exports sometimes mangle reference_id (case changes, truncation, transposed digits) and post a few days after the settlement date, so use amount, date proximity, reference_id similarity, and narration together — not any single field alone.

SETTLEMENT: settlement_id={settlement_id}, reference_id={reference_id}, amount={amount}, date={date}, status={status}

CANDIDATE BANK ENTRIES:
{candidates_block}

Decide whether exactly one candidate is the true bank-side counterpart of this settlement, or none is. Do not guess if the evidence is weak — say no match.

Respond with ONLY a single JSON object, no markdown, no code fence, no commentary before or after it, matching exactly this shape:
{{"match_found": true or false, "matched_bank_txn_id": "<txn_id from the candidates above, or null>", "reasoning": "<one or two sentence explanation citing the specific evidence>"}}"""


def _format_candidates(candidates):
    lines = []
    for i, c in enumerate(candidates, 1):
        lines.append(
            f'{i}. txn_id={c["txn_id"]}, reference_id={c["reference_id"]}, '
            f'amount={c["amount"]}, date={c["date"]}, narration="{c["narration"]}"'
        )
    return "\n".join(lines)


def get_llm_verdict(settlement, candidates, model=None):
    """Ask Ollama to pick a matching candidate (or none) for a settlement
    record. Returns {"match_found": bool, "matched_bank_txn_id": str|None,
    "reasoning": str}. Never raises — any failure (network, parse, or an
    out-of-range answer) comes back as a safe "no match" with the failure
    reason, so a bad LLM call degrades to an honest exception, not a
    fabricated match.
    """
    model = model or DEFAULT_MODEL
    prompt = PROMPT_TEMPLATE.format(
        settlement_id=settlement["settlement_id"],
        reference_id=settlement["reference_id"],
        amount=settlement["amount"],
        date=settlement["date"],
        status=settlement["status"],
        candidates_block=_format_candidates(candidates),
    )

    try:
        resp = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0},
        )
        raw = resp["message"]["content"]
    except Exception as e:
        return {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM call failed: {e}",
        }

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM response was not parseable JSON: {raw[:200]!r}",
        }

    try:
        verdict = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM response had malformed JSON: {raw[:200]!r}",
        }

    candidate_ids = {c["txn_id"] for c in candidates}
    txn_id = verdict.get("matched_bank_txn_id")
    reasoning = verdict.get("reasoning", "")

    if verdict.get("match_found") and txn_id in candidate_ids:
        return {"match_found": True, "matched_bank_txn_id": txn_id, "reasoning": reasoning}

    if verdict.get("match_found") and txn_id not in candidate_ids:
        return {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM named a bank_txn_id not in the candidate set ({txn_id!r}); discarded as invalid.",
        }

    return {"match_found": False, "matched_bank_txn_id": None, "reasoning": reasoning}
