"""Ollama-backed match/no-match verdicts for the reconciliation "ambiguous
middle" — records the rule tiers can't confidently resolve.

Note: Ollama's structured-output `format=` schema constraint is NOT honored
for cloud-routed models (verified during Phase 2 build — see
docs/BUILD-CHALLENGES.md). Instead we instruct JSON-only output in the
prompt and parse defensively.
"""

import json
import logging
import os
import time

import ollama

logger = logging.getLogger("llm_matcher")

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:120b-cloud")
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
# A 429 means the endpoint is rejecting the call outright because too many
# requests are already in flight — it returns almost instantly (confirmed
# empirically: ~0.3-0.4s, versus multiple seconds for a real inference), so
# it's a near-guaranteed success on retry once other in-flight calls clear,
# not a random transient blip. It gets more attempts and a longer backoff
# than a generic failure so concurrent LLM-tier callers (reconcile.py's
# thread pool) don't silently downgrade a rate-limited call into a false
# "no match" exception.
MAX_ATTEMPTS_RATE_LIMITED = 6
BACKOFF_BASE_SECONDS_RATE_LIMITED = 1.0

PROMPT_TEMPLATE = """You are reconciling a Razorpay settlement record against candidate bank statement entries. Bank exports sometimes mangle reference_id (case changes, truncation, transposed digits) and post a few days after the settlement date, so use amount, date proximity, reference_id similarity, and narration together — not any single field alone.

SETTLEMENT: settlement_id={settlement_id}, reference_id={reference_id}, amount={amount}, date={date}, status={status}

CANDIDATE BANK ENTRIES:
{candidates_block}

Decide whether exactly one candidate is the true bank-side counterpart of this settlement, or none is. Do not guess if the evidence is weak — say no match.

Respond with ONLY a single JSON object, no markdown, no code fence, no commentary before or after it, matching exactly this shape:
{{"match_found": true or false, "matched_bank_txn_id": "<txn_id from the candidates above, or null>", "reasoning": "<one or two sentence explanation citing the specific evidence>"}}"""

BATCH_PROMPT_TEMPLATE = """You are reconciling multiple Razorpay settlement records against candidate bank statement entries. Bank exports sometimes mangle reference_id (case changes, truncation, transposed digits) and post a few days after the settlement date, so use amount, date proximity, reference_id similarity, and narration together — not any single field alone.

Decide INDEPENDENTLY for EACH settlement below whether exactly one of ITS OWN listed candidates is its true bank-side counterpart, or none is. Do not guess if the evidence is weak — say no match. Never match a settlement to a candidate listed under a different settlement.

{settlements_block}

Respond with ONLY a single JSON array, no markdown, no code fence, no commentary before or after it, with exactly one object per settlement above, in the same order, each matching exactly this shape:
[{{"settlement_id": "<settlement_id>", "match_found": true or false, "matched_bank_txn_id": "<txn_id from that settlement's own candidates above, or null>", "reasoning": "<one or two sentence explanation citing the specific evidence>"}}, ...]"""


def _format_candidates(candidates):
    lines = []
    for i, c in enumerate(candidates, 1):
        lines.append(
            f'{i}. txn_id={c["txn_id"]}, reference_id={c["reference_id"]}, '
            f'amount={c["amount"]}, date={c["date"]}, narration="{c["narration"]}"'
        )
    return "\n".join(lines)


def _parse_verdict(raw, candidates):
    """Parse the LLM's raw text response into a verdict dict. Pure function,
    no network — the seam that carries all the defensive parsing logic
    (see docs/BUILD-CHALLENGES.md for the bug classes this guards against:
    greedy-regex JSON extraction, stringly-typed booleans, out-of-range IDs).
    Never raises — any parse failure or invalid answer becomes a safe
    "no match" with the reason, never a fabricated match.
    """
    start = raw.find("{")
    if start == -1:
        return {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM response was not parseable JSON: {raw[:200]!r}",
        }

    try:
        # raw_decode parses exactly one JSON value starting at `start` and
        # ignores anything after it — unlike a greedy regex, it isn't thrown
        # off by trailing commentary or stray braces after the real object.
        verdict, _ = json.JSONDecoder().raw_decode(raw, start)
    except json.JSONDecodeError:
        return {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM response had malformed JSON: {raw[:200]!r}",
        }

    candidate_ids = {c["txn_id"] for c in candidates}
    txn_id = verdict.get("matched_bank_txn_id")
    reasoning = verdict.get("reasoning", "")
    match_found = verdict.get("match_found") is True

    if match_found and txn_id in candidate_ids:
        return {"match_found": True, "matched_bank_txn_id": txn_id, "reasoning": reasoning}

    if match_found and txn_id not in candidate_ids:
        return {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM named a bank_txn_id not in the candidate set ({txn_id!r}); discarded as invalid.",
        }

    return {"match_found": False, "matched_bank_txn_id": None, "reasoning": reasoning}


def _format_settlements_block(settlements_with_candidates):
    parts = []
    for i, (settlement, candidates) in enumerate(settlements_with_candidates, 1):
        parts.append(
            f"SETTLEMENT {i}: settlement_id={settlement['settlement_id']}, "
            f"reference_id={settlement['reference_id']}, amount={settlement['amount']}, "
            f"date={settlement['date']}, status={settlement['status']}\n"
            f"CANDIDATES FOR SETTLEMENT {i}:\n{_format_candidates(candidates)}"
        )
    return "\n\n".join(parts)


def _parse_batch_verdicts(raw, settlements_with_candidates):
    """Same never-raise, never-fabricate contract as _parse_verdict, for a
    batch response. A settlement missing from the response, or whose
    matched_bank_txn_id isn't in ITS OWN candidate set (not merely present
    somewhere in the batch — see BATCH_PROMPT_TEMPLATE's explicit warning
    against cross-settlement matches), falls back to a safe "no match"."""
    candidates_by_sid = {
        s["settlement_id"]: {c["txn_id"] for c in cands} for s, cands in settlements_with_candidates
    }
    all_sids = list(candidates_by_sid.keys())

    def fallback_all(reason):
        return {sid: {"match_found": False, "matched_bank_txn_id": None, "reasoning": reason} for sid in all_sids}

    start = raw.find("[")
    if start == -1:
        return fallback_all(f"LLM batch response was not a parseable JSON array: {raw[:200]!r}")
    try:
        parsed, _ = json.JSONDecoder().raw_decode(raw, start)
    except json.JSONDecodeError:
        return fallback_all(f"LLM batch response had malformed JSON: {raw[:200]!r}")
    if not isinstance(parsed, list):
        return fallback_all(f"LLM batch response was not a JSON array: {raw[:200]!r}")

    verdicts = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        sid = item.get("settlement_id")
        if sid not in candidates_by_sid:
            continue  # unknown/missing settlement_id — never guess which of ours it meant
        txn_id = item.get("matched_bank_txn_id")
        reasoning = item.get("reasoning", "")
        match_found = item.get("match_found") is True
        if match_found and txn_id in candidates_by_sid[sid]:
            verdicts[sid] = {"match_found": True, "matched_bank_txn_id": txn_id, "reasoning": reasoning}
        elif match_found:
            verdicts[sid] = {
                "match_found": False,
                "matched_bank_txn_id": None,
                "reasoning": f"LLM named a bank_txn_id not in {sid}'s own candidate set ({txn_id!r}); discarded as invalid.",
            }
        else:
            verdicts[sid] = {"match_found": False, "matched_bank_txn_id": None, "reasoning": reasoning}

    for sid in all_sids:
        if sid not in verdicts:
            verdicts[sid] = {
                "match_found": False,
                "matched_bank_txn_id": None,
                "reasoning": "LLM batch response did not include a verdict for this settlement",
            }
    return verdicts


def get_llm_verdicts_batch(settlements_with_candidates, model=None, sleep_fn=time.sleep):
    """Same contract as get_llm_verdict, but decides a whole batch of
    settlements in one call: settlements_with_candidates is a list of
    (settlement_dict, candidate_dicts) pairs. Returns dict
    settlement_id -> verdict. Never raises — a failed call (after retries)
    or a malformed/incomplete response falls every settlement in the batch
    back to a safe "no match", exactly like get_llm_verdict's single-item
    guarantee, never a fabricated match.

    Exists because the LLM tier can't safely be parallelized against this
    account's Ollama cloud endpoint (see docs/BUILD-CHALLENGES.md) — cutting
    the number of sequential round trips by batching multiple settlements
    per call is the remaining lever for real wall-clock time.
    """
    model = model or DEFAULT_MODEL
    prompt = BATCH_PROMPT_TEMPLATE.format(
        settlements_block=_format_settlements_block(settlements_with_candidates)
    )

    last_error = None
    max_attempts = MAX_ATTEMPTS
    attempt = 0
    while attempt < max_attempts:
        try:
            resp = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
            raw = resp["message"]["content"]
        except Exception as e:
            last_error = e
            rate_limited = getattr(e, "status_code", None) == 429
            if rate_limited:
                max_attempts = max(max_attempts, MAX_ATTEMPTS_RATE_LIMITED)
                backoff_base = BACKOFF_BASE_SECONDS_RATE_LIMITED
            else:
                backoff_base = BACKOFF_BASE_SECONDS
            if attempt < max_attempts - 1:
                delay = backoff_base * (2 ** attempt)
                logger.warning(
                    "LLM batch call failed on attempt %d/%d (%s), retrying in %.1fs",
                    attempt + 1, max_attempts, e, delay,
                )
                sleep_fn(delay)
            else:
                logger.warning(
                    "LLM batch call failed on attempt %d/%d (%s), gave up",
                    attempt + 1, max_attempts, e,
                )
            attempt += 1
            continue
        return _parse_batch_verdicts(raw, settlements_with_candidates)

    sids = [s["settlement_id"] for s, _ in settlements_with_candidates]
    return {
        sid: {
            "match_found": False,
            "matched_bank_txn_id": None,
            "reasoning": f"LLM batch call failed after {max_attempts} attempts: {last_error}",
        }
        for sid in sids
    }


def get_llm_verdict(settlement, candidates, model=None, sleep_fn=time.sleep):
    """Ask Ollama to pick a matching candidate (or none) for a settlement
    record. Returns {"match_found": bool, "matched_bank_txn_id": str|None,
    "reasoning": str}. Never raises — any failure (network or parse) comes
    back as a safe "no match" with the failure reason, so a bad LLM call
    degrades to an honest exception, not a fabricated match.

    Retries up to MAX_ATTEMPTS times with exponential backoff on a network/
    call failure (a transient blip shouldn't cost a real match); a bad or
    unparseable response is not retried, since re-sending the same prompt
    to a temperature=0 model won't fix a parse failure.
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

    last_error = None
    max_attempts = MAX_ATTEMPTS
    attempt = 0
    while attempt < max_attempts:
        try:
            resp = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0},
            )
            raw = resp["message"]["content"]
        except Exception as e:
            last_error = e
            settlement_id = settlement.get("settlement_id", "?")
            rate_limited = getattr(e, "status_code", None) == 429
            if rate_limited:
                # Widen the budget the first time a 429 is seen, so a call
                # that only ever hits rate-limiting (never a real error)
                # gets the full rate-limited retry budget even though it
                # started counting against the smaller default one.
                max_attempts = max(max_attempts, MAX_ATTEMPTS_RATE_LIMITED)
                backoff_base = BACKOFF_BASE_SECONDS_RATE_LIMITED
            else:
                backoff_base = BACKOFF_BASE_SECONDS
            if attempt < max_attempts - 1:
                delay = backoff_base * (2 ** attempt)
                logger.warning(
                    "LLM call failed for %s on attempt %d/%d (%s), retrying in %.1fs",
                    settlement_id, attempt + 1, max_attempts, e, delay,
                )
                sleep_fn(delay)
            else:
                logger.warning(
                    "LLM call failed for %s on attempt %d/%d (%s), gave up",
                    settlement_id, attempt + 1, max_attempts, e,
                )
            attempt += 1
            continue
        return _parse_verdict(raw, candidates)

    return {
        "match_found": False,
        "matched_bank_txn_id": None,
        "reasoning": f"LLM call failed after {max_attempts} attempts: {last_error}",
    }
