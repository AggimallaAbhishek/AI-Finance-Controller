"""Reconciliation engine: matches settlement.csv against bank_statement.csv.

Tier 1-3 (rules, deterministic): exact reference_id join, then within
DATE_TOLERANCE_DAYS / AMOUNT_TOLERANCE_RS.
Tier 3.5 (algorithmic reference reconstruction): catches the specific
failure mode of a bank-mangled reference_id (case flip, truncation, or an
adjacent-character transposition) with an exact amount and narration that
still names the true reference's tail — identified by edit-distance, then
confirmed with a single-candidate LLM call before being accepted (an
edit-distance match is strong evidence, not an identity check). See
algo_tier().
Tier 4 (Ollama): records neither of the above could confidently resolve get
sent, with their top candidate bank entries, for a reasoned match/no-match
verdict. Anything left over becomes an exception.

Runnable as a script:
  python reconcile.py --settlement ../data/settlement.csv --bank ../data/bank_statement.csv
"""

import argparse
import csv
import difflib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import audit
from llm_matcher import get_llm_verdict, get_llm_verdicts_batch, DEFAULT_MODEL

logger = logging.getLogger("reconcile")

# Configurable without a code change — see docs/glossary.md for what these
# tolerances mean. Defaults match the ones the batch was designed against.
DATE_TOLERANCE_DAYS = int(os.environ.get("RECONCILE_DATE_TOLERANCE_DAYS", "2"))
AMOUNT_TOLERANCE_RS = Decimal(os.environ.get("RECONCILE_AMOUNT_TOLERANCE_RS", "10"))
CANDIDATE_SCORE_FLOOR = 0.45
MAX_CANDIDATES = 3
# Tier 3.5 thresholds — deliberately independent of DATE_TOLERANCE_DAYS
# above (which governs a *clean* reference match): a corrupted reference
# needs corroborating evidence (exact amount + narration) before a wider
# date window is trusted, so this tolerance can safely be looser than the
# rule tier's without that meaning "we trust dates more" in general.
ALGO_DATE_TOLERANCE_DAYS = int(os.environ.get("RECONCILE_ALGO_DATE_TOLERANCE_DAYS", "7"))
ALGO_REF_EDIT_DISTANCE_MAX = int(os.environ.get("RECONCILE_ALGO_REF_EDIT_DISTANCE", "3"))
# The LLM tier is network-bound (each call is a round trip to Ollama), so
# calls are issued concurrently up to this many in flight at once — IF the
# endpoint actually tolerates it. Default is 1 (effectively sequential):
# a concurrency probe using real reconciliation-shaped prompts (not a
# trivial "reply with a number" one — see docs/BUILD-CHALLENGES.md for why
# that first probe was misleading) found gpt-oss:20b-cloud fails ~90% of
# calls with HTTP 429 at just 2 concurrent requests, because a real call
# holds the connection open for ~30s of actual reasoning — long enough for
# concurrent calls to genuinely overlap and collide with what looks like a
# near-single-flight limit on this account/endpoint. Only raise this via
# RECONCILE_LLM_MAX_WORKERS if your Ollama account/model is confirmed (via
# the same realistic-prompt probe methodology) to tolerate more.
LLM_MAX_WORKERS = int(os.environ.get("RECONCILE_LLM_MAX_WORKERS", "1"))
# With concurrency off the table, the remaining lever for real wall-clock
# time is fewer round trips: batch this many settlements into one LLM call
# (get_llm_verdicts_batch) instead of one call per settlement. Validated via
# the eval harness against real gpt-oss:20b-cloud calls (batch_size=1 vs. 4
# on the same 20 llm-tier settlements from data/batch_1000): accuracy held
# at 100% both ways (no batching-induced FP/FN), and wall clock dropped from
# 288.9s to 249.7s (~13% fewer seconds per call) — see docs/BUILD-CHALLENGES.md.
# Tests that mock llm_fn directly (not llm_batch_fn) pass batch_size=1
# explicitly so they're unaffected by this default.
LLM_BATCH_SIZE = int(os.environ.get("RECONCILE_LLM_BATCH_SIZE", "4"))


@dataclass
class Settlement:
    settlement_id: str
    reference_id: str
    amount: Decimal
    date: date
    status: str


@dataclass
class BankEntry:
    txn_id: str
    reference_id: str
    amount: Decimal
    date: date
    narration: str


def load_settlements(path):
    with open(path, newline="") as f:
        return [
            Settlement(
                settlement_id=row["settlement_id"],
                reference_id=row["reference_id"],
                amount=Decimal(row["amount"]),
                date=date.fromisoformat(row["date"]),
                status=row["status"],
            )
            for row in csv.DictReader(f)
        ]


def load_bank_entries(path):
    with open(path, newline="") as f:
        return [
            BankEntry(
                txn_id=row["txn_id"],
                reference_id=row["reference_id"],
                amount=Decimal(row["amount"]),
                date=date.fromisoformat(row["date"]),
                narration=row["narration"],
            )
            for row in csv.DictReader(f)
        ]


def _ref_key(reference_id):
    """Case-normalized reference_id, used both to index bank entries for
    O(1) lookup and to decide whether a rule-tier match required case
    normalization. A bank export re-casing a reference_id (e.g. lowercasing
    it) doesn't change which transaction it identifies, so comparing on
    this key is exact-identity matching, not fuzzy matching — the
    reference_id namespace (RZP + 10 digits) is wide enough that a
    same-key-different-case collision between two unrelated transactions is
    not a realistic risk."""
    return reference_id.lower()


def rule_tier(settlement, bank, date_tolerance_days=None, amount_tolerance_rs=None):
    """Return (confidence, reason) if settlement/bank match within rule
    tolerance, else None. Requires the reference_id to match exactly once
    case-normalized — that's what makes a rule verdict trustworthy without
    reasoning over free text; a same-case exact match still gets its own
    "exact"/"fuzzy-*" confidence, while a match that needed case
    normalization is labeled "*-ci" so the audit trail stays honest about
    what evidence the match actually rested on.
    Tolerances default to the module-level (environment-configurable)
    constants; pass explicit values to override per call."""
    date_tolerance_days = DATE_TOLERANCE_DAYS if date_tolerance_days is None else date_tolerance_days
    amount_tolerance_rs = AMOUNT_TOLERANCE_RS if amount_tolerance_rs is None else amount_tolerance_rs

    if _ref_key(settlement.reference_id) != _ref_key(bank.reference_id):
        return None
    case_matched = settlement.reference_id == bank.reference_id
    suffix = "" if case_matched else "-ci"
    ref_note = "reference_id" if case_matched else "reference_id (case-insensitive)"

    date_diff = abs((settlement.date - bank.date).days)
    amount_diff = abs(settlement.amount - bank.amount)

    if date_diff == 0 and amount_diff == 0:
        return f"exact{suffix}", f"{ref_note}, amount, and date all matched exactly"
    if amount_diff == 0 and date_diff <= date_tolerance_days:
        return f"fuzzy-date{suffix}", (
            f"{ref_note} and amount matched exactly; date differs by "
            f"{date_diff} day(s), within {date_tolerance_days}-day tolerance"
        )
    if date_diff == 0 and amount_diff <= amount_tolerance_rs:
        return f"fuzzy-amount{suffix}", (
            f"{ref_note} and date matched exactly; amount differs by "
            f"Rs {amount_diff}, within Rs {amount_tolerance_rs} tolerance"
        )
    if date_diff <= date_tolerance_days and amount_diff <= amount_tolerance_rs:
        return f"fuzzy-date-amount{suffix}", (
            f"{ref_note} matched; date differs by {date_diff} day(s) "
            f"and amount by Rs {amount_diff}, both within tolerance"
        )
    return None


def _restricted_edit_distance(a, b):
    """Levenshtein distance with adjacent transpositions counted as a
    single edit (the "optimal string alignment" variant — simpler than
    full Damerau-Levenshtein since it doesn't need to handle a
    transposed pair being re-edited later, which never matters for
    reference IDs this short). O(len(a) * len(b)); cheap for ~13-char
    strings. Matches the corruption styles a bank export realistically
    introduces: a substituted/dropped character or one swapped pair."""
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,         # deletion
                d[i][j - 1] + 1,         # insertion
                d[i - 1][j - 1] + cost,  # substitution
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)  # adjacent transposition
    return d[la][lb]


def algo_tier(settlement, bank):
    """Return ("algo-reconstructed", reason) if a corrupted bank
    reference_id can be confidently reconstructed against this
    settlement, else None.

    Targets the one failure mode the rule tier structurally can't reach:
    rule_tier() requires reference_id equality (case-normalized) up
    front, so a bank export that truncates, transposes, or otherwise
    mangles the reference never even gets compared on date/amount. This
    tier runs only on settlements the rule tier already gave up on
    (candidates come from the same shortlist built for the LLM), and
    requires ALL of:
      - amount matches exactly (no drift tolerance — a corrupted
        reference is already one uncertain signal; stacking a fuzzy
        amount on top would make coincidental collisions too likely)
      - the two reference_ids (case-folded) are within
        ALGO_REF_EDIT_DISTANCE_MAX edits of each other
      - the settlement reference's last 6 characters appear in the bank
        narration (independent corroboration, not derived from the
        edit-distance check)
      - date differs by no more than ALGO_DATE_TOLERANCE_DAYS (wider
        than the rule tier's window, since the other three signals
        already establish identity; still bounded, not unlimited)
    Any single signal here is too weak to trust alone — together they're
    strong enough to identify a candidate worth proposing, but the caller
    (run_reconciliation) still sends it to the LLM for a single-candidate
    confirmation before accepting it; this function only identifies the
    candidate, it never calls the LLM itself."""
    if settlement.amount != bank.amount:
        return None

    date_diff = abs((settlement.date - bank.date).days)
    if date_diff > ALGO_DATE_TOLERANCE_DAYS:
        return None

    ref_tail = settlement.reference_id[-6:].lower()
    if ref_tail not in bank.narration.lower():
        return None

    distance = _restricted_edit_distance(
        settlement.reference_id.lower(), bank.reference_id.lower()
    )
    if distance > ALGO_REF_EDIT_DISTANCE_MAX:
        return None

    return "algo-reconstructed", (
        f"amount matched exactly; bank reference_id '{bank.reference_id}' is "
        f"within edit distance {distance} of settlement reference_id "
        f"'{settlement.reference_id}' (case-insensitive), and narration "
        f"'{bank.narration}' contains its tail '{settlement.reference_id[-6:]}'; "
        f"date differs by {date_diff} day(s), beyond the {DATE_TOLERANCE_DAYS}-day "
        f"rule tolerance but within the {ALGO_DATE_TOLERANCE_DAYS}-day algorithmic window"
    )


def candidate_score(settlement, bank):
    """Similarity score (0 to 1.2, with the narration bonus) used to
    shortlist LLM candidates for a settlement the rules couldn't resolve.
    Not a matching decision — just ranks which unclaimed bank rows are
    worth showing the LLM."""
    ref_sim = difflib.SequenceMatcher(
        None, settlement.reference_id.lower(), bank.reference_id.lower()
    ).ratio()

    amount_diff = abs(settlement.amount - bank.amount)
    amount_score = max(Decimal("0"), Decimal("1") - amount_diff / max(settlement.amount, Decimal("1")))

    date_diff = abs((settlement.date - bank.date).days)
    date_score = max(0.0, 1 - date_diff / 10)

    narration_bonus = 0.3 if settlement.reference_id[-6:].lower() in bank.narration.lower() else 0.0

    return float(ref_sim) * 0.4 + float(amount_score) * 0.3 + date_score * 0.2 + narration_bonus


def shortlist_candidates(settlement, unclaimed_bank):
    scored = [(candidate_score(settlement, b), b) for b in unclaimed_bank]
    scored = [(s, b) for s, b in scored if s >= CANDIDATE_SCORE_FLOOR]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [b for _, b in scored[:MAX_CANDIDATES]]


def run_reconciliation(settlements, bank_entries, use_llm=True, llm_fn=get_llm_verdict, model=None,
                        progress_cb=None, batch_size=None, llm_batch_fn=get_llm_verdicts_batch):
    """Returns (matches, exceptions, audit_entries, stats).

    progress_cb(stage, done, total), if given, is called with real counts as
    each tier processes — stages "rules", "llm" (only if any settlement
    falls to it), "persisting" — so a caller (the async /reconcile job) can
    show real progress instead of a spinner that looks stuck.

    batch_size (default: LLM_BATCH_SIZE, itself defaulting to 1) controls
    how many settlements go into one LLM call. 1 preserves the original
    one-settlement-per-call behavior via llm_fn exactly. >1 groups
    settlements needing the LLM tier into chunks and calls llm_batch_fn
    once per chunk instead — see docs/BUILD-CHALLENGES.md for why batching,
    not concurrency, is the real lever for wall-clock time on this
    account's Ollama endpoint."""
    batch_size = LLM_BATCH_SIZE if batch_size is None else batch_size
    def report(stage, done, total):
        if progress_cb:
            progress_cb(stage, done, total)

    bank_by_id = {b.txn_id: b for b in bank_entries}
    bank_by_ref = {}
    for b in bank_entries:
        bank_by_ref.setdefault(_ref_key(b.reference_id), []).append(b)
    claimed = set()
    matches = []
    audit_entries = []
    unresolved = []

    settlements_sorted = sorted(settlements, key=lambda s: s.settlement_id)

    # Tier 1-3: rules. rule_tier() requires (case-normalized) reference_id
    # equality, so only bank entries sharing that key can ever match a given
    # settlement — looking them up via bank_by_ref instead of scanning every
    # bank entry turns this from O(settlements x bank_entries) into
    # effectively O(settlements), the dominant cost at large batch sizes.
    for i, s in enumerate(settlements_sorted):
        best = None  # (b, confidence, reason, amount_diff, date_diff)
        for b in bank_by_ref.get(_ref_key(s.reference_id), []):
            if b.txn_id in claimed:
                continue
            verdict = rule_tier(s, b)
            if verdict is None:
                continue
            confidence, reason = verdict
            date_diff = abs((s.date - b.date).days)
            amount_diff = abs(s.amount - b.amount)
            # Rank by amount closeness first, then date closeness: two
            # unrelated transactions rarely share both a reference_id and an
            # exact amount by coincidence, while date drift is routine
            # operational noise — so amount is the stronger tie-breaker.
            if best is None or (amount_diff, date_diff) < (best[3], best[4]):
                best = (b, confidence, reason, amount_diff, date_diff)
        if best:
            b, confidence, reason, _, _ = best
            claimed.add(b.txn_id)
            matches.append({
                "match_status": "matched",
                "settlement_ref": s.settlement_id,
                "bank_ref": b.txn_id,
                "confidence": confidence,
                "reason": reason,
            })
            audit_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "settlement_ref": s.settlement_id,
                "bank_ref": b.txn_id,
                "match_status": "matched",
                "confidence": confidence,
                "reason": reason,
                "tier": "rule",
            })
        else:
            unresolved.append(s)
        report("rules", i + 1, len(settlements_sorted))

    # Tier 4: LLM for the ambiguous middle. Each call is a network round
    # trip to Ollama, so it's the dominant wall-clock cost at scale — calls
    # are issued concurrently (up to LLM_MAX_WORKERS in flight) instead of
    # one at a time.
    #
    # Correctness: a settlement's candidate shortlist depends on which bank
    # entries are still unclaimed, and that set changes as earlier
    # settlements in this tier get matched — the original sequential loop
    # relied on `claimed` always being fully up to date at shortlist time.
    # Running calls concurrently means each settlement's candidates get
    # frozen (computed once, against claimed-after-rules) before any
    # verdict comes back, so by the time we're ready to apply one, an
    # earlier-applied settlement may have since claimed one of its
    # candidates. So at apply time we recompute the live shortlist and only
    # trust the concurrently-fetched verdict when it's identical to what
    # was actually shown to the LLM; otherwise we redo that one
    # settlement's call synchronously against the live candidates — exactly
    # what the strictly sequential version would have done. This keeps the
    # output identical to before, while parallelizing the common case.
    def build_candidates(s, live_claimed):
        unclaimed_bank = [b for b in bank_entries if b.txn_id not in live_claimed]
        candidates = shortlist_candidates(s, unclaimed_bank)
        candidate_dicts = [
            {"txn_id": b.txn_id, "reference_id": b.reference_id, "amount": str(b.amount),
             "date": b.date.isoformat(), "narration": b.narration}
            for b in candidates
        ]
        return candidates, candidate_dicts

    settlement_dicts = {
        s.settlement_id: {
            "settlement_id": s.settlement_id, "reference_id": s.reference_id,
            "amount": str(s.amount), "date": s.date.isoformat(), "status": s.status,
        }
        for s in unresolved
    }

    claimed_after_rules = set(claimed)
    frozen = {}       # settlement_id -> (candidates, candidate_dicts) at freeze time
    llm_jobs = {}      # settlement_id -> Settlement, for those that actually need a call
    algo_resolved_ids = set()  # settlement_ids Tier 3.5 resolved (LLM-verified)
    for s in unresolved:
        # A non-"settled" settlement (reversed/pending) has no live bank-side
        # money movement to find a counterpart for, so it can never have a
        # genuine match — skip the O(bank_entries) shortlist scoring for it
        # entirely rather than fuzzy-searching for a counterpart that by
        # definition doesn't exist. This is the dominant cost saving at
        # scale (shortlist_candidates is the other O(settlements x
        # bank_entries) hotspot, separate from the rule tier), since
        # roughly half of what reaches this tier is typically this status.
        if s.status != "settled":
            frozen[s.settlement_id] = ([], [])
            continue
        candidates, candidate_dicts = build_candidates(s, claimed_after_rules)

        # Tier 3.5: identify a candidate deterministically against this same
        # shortlist (already ranked by candidate_score, which rewards
        # reference similarity/amount/date/narration), then require an LLM
        # call to confirm it before accepting — edit-distance + narration is
        # strong evidence but still a heuristic, not an identity check, so
        # every algo-identified candidate gets a second opinion rather than
        # being auto-accepted. Only runs when an LLM is actually available
        # (use_llm) — without one, a Tier 3.5 candidate falls through to the
        # normal Tier 4 path below like any other ambiguous-middle
        # settlement, never auto-accepted unverified. Sequential like the
        # rule tier above — not concurrent like Tier 4 — so claiming a
        # candidate here is immediately visible to every later settlement's
        # shortlist in this same loop.
        algo_verified = None
        if use_llm:
            for i, b in enumerate(candidates):
                verdict = algo_tier(s, b)
                if not verdict:
                    continue
                confidence, reason = verdict
                check = llm_fn(settlement_dicts[s.settlement_id], [candidate_dicts[i]], model=model)
                if check["match_found"] and check["matched_bank_txn_id"] == b.txn_id:
                    algo_verified = (b, confidence, f"{reason}; LLM-confirmed: {check['reasoning']}")
                else:
                    logger.info(
                        "Tier 3.5 candidate for %s (%s) rejected by LLM verification (%s) — "
                        "falling through to Tier 4 with the full candidate set",
                        s.settlement_id, b.txn_id, check["reasoning"],
                    )
                break  # only the top algo candidate is tried; a rejection falls through, not to candidate #2
        if algo_verified:
            b, confidence, reason = algo_verified
            claimed_after_rules.add(b.txn_id)
            claimed.add(b.txn_id)
            algo_resolved_ids.add(s.settlement_id)
            matches.append({
                "match_status": "matched",
                "settlement_ref": s.settlement_id,
                "bank_ref": b.txn_id,
                "confidence": confidence,
                "reason": reason,
            })
            audit_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "settlement_ref": s.settlement_id,
                "bank_ref": b.txn_id,
                "match_status": "matched",
                "confidence": confidence,
                "reason": reason,
                "tier": "algo",
                "model": model or DEFAULT_MODEL,
                "candidates_considered": [b.txn_id],
            })
            continue

        frozen[s.settlement_id] = (candidates, candidate_dicts)
        if use_llm and candidates:
            llm_jobs[s.settlement_id] = s

    llm_remaining = [s for s in unresolved if s.settlement_id not in algo_resolved_ids]

    verdicts = {}
    if llm_jobs and batch_size <= 1:
        with ThreadPoolExecutor(max_workers=min(LLM_MAX_WORKERS, len(llm_jobs))) as pool:
            future_to_sid = {}
            for sid, s in llm_jobs.items():
                _, candidate_dicts = frozen[sid]
                future = pool.submit(llm_fn, settlement_dicts[sid], candidate_dicts, model=model)
                future_to_sid[future] = sid
            for future in as_completed(future_to_sid):
                verdicts[future_to_sid[future]] = future.result()
    elif llm_jobs:
        # Batched path: group settlements needing the LLM tier into chunks
        # of batch_size and issue one llm_batch_fn call per chunk (each
        # chunk-call still goes through the same worker pool, so it's
        # still safely bounded by LLM_MAX_WORKERS if that's ever raised
        # above 1). Cuts round trips, not concurrency.
        job_sids = list(llm_jobs.keys())
        chunks = [job_sids[i:i + batch_size] for i in range(0, len(job_sids), batch_size)]
        with ThreadPoolExecutor(max_workers=min(LLM_MAX_WORKERS, len(chunks))) as pool:
            future_to_chunk = {}
            for chunk in chunks:
                items = [(settlement_dicts[sid], frozen[sid][1]) for sid in chunk]
                future = pool.submit(llm_batch_fn, items, model=model)
                future_to_chunk[future] = chunk
            for future in as_completed(future_to_chunk):
                verdicts.update(future.result())

    exceptions = []
    for i, s in enumerate(llm_remaining):
        candidates, candidate_dicts = frozen[s.settlement_id]

        if not use_llm or not candidates:
            if not use_llm:
                reason = "LLM tier skipped (--no-llm); no rule match found"
                if candidates:
                    reason += f"; {len(candidates)} candidate(s) existed but were not reviewed"
                tier = "skipped-llm"
                if s.status != "settled":
                    reason += f"; settlement status is '{s.status}'"
            elif s.status != "settled":
                reason = f"no bank counterpart search performed; settlement status is '{s.status}', not 'settled'"
                tier = "rule"
            else:
                reason = "no plausible bank counterpart found (no candidates cleared the similarity floor)"
                tier = "rule"
            exceptions.append({
                "match_status": "exception",
                "settlement_ref": s.settlement_id,
                "bank_ref": None,
                "confidence": None,
                "reason": reason,
            })
            audit_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "settlement_ref": s.settlement_id,
                "bank_ref": None,
                "match_status": "exception",
                "confidence": None,
                "reason": reason,
                "tier": tier,
            })
            report("llm", i + 1, len(llm_remaining))
            continue

        live_candidates, live_candidate_dicts = build_candidates(s, claimed)
        if [c.txn_id for c in live_candidates] == [c.txn_id for c in candidates]:
            verdict = verdicts[s.settlement_id]
            used_candidate_dicts = candidate_dicts
        elif not live_candidates:
            reason = "no plausible bank counterpart found (no candidates cleared the similarity floor)"
            if s.status != "settled":
                reason += f"; settlement status is '{s.status}'"
            exceptions.append({
                "match_status": "exception",
                "settlement_ref": s.settlement_id,
                "bank_ref": None,
                "confidence": None,
                "reason": reason,
            })
            audit_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "settlement_ref": s.settlement_id,
                "bank_ref": None,
                "match_status": "exception",
                "confidence": None,
                "reason": reason,
                "tier": "rule",
            })
            report("llm", i + 1, len(llm_remaining))
            continue
        else:
            # A concurrently-processed settlement claimed one of this
            # settlement's candidates since it was frozen — redo the call
            # synchronously against the now-current candidate set, same as
            # sequential processing would have done at this point.
            verdict = llm_fn(settlement_dicts[s.settlement_id], live_candidate_dicts, model=model)
            used_candidate_dicts = live_candidate_dicts

        if verdict["match_found"]:
            b = bank_by_id[verdict["matched_bank_txn_id"]]
            claimed.add(b.txn_id)
            matches.append({
                "match_status": "matched",
                "settlement_ref": s.settlement_id,
                "bank_ref": b.txn_id,
                "confidence": "llm-reasoned",
                "reason": verdict["reasoning"],
            })
            audit_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "settlement_ref": s.settlement_id,
                "bank_ref": b.txn_id,
                "match_status": "matched",
                "confidence": "llm-reasoned",
                "reason": verdict["reasoning"],
                "tier": "llm",
                "model": model or DEFAULT_MODEL,
                "candidates_considered": [c["txn_id"] for c in used_candidate_dicts],
            })
        else:
            reason = f"LLM reviewed {len(used_candidate_dicts)} candidate(s), no match: {verdict['reasoning']}"
            exceptions.append({
                "match_status": "exception",
                "settlement_ref": s.settlement_id,
                "bank_ref": None,
                "confidence": None,
                "reason": reason,
            })
            audit_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "settlement_ref": s.settlement_id,
                "bank_ref": None,
                "match_status": "exception",
                "confidence": None,
                "reason": reason,
                "tier": "llm",
                "model": model or DEFAULT_MODEL,
                "candidates_considered": [c["txn_id"] for c in used_candidate_dicts],
            })
        report("llm", i + 1, len(llm_remaining))

    # Unclaimed bank rows are bank-side exceptions
    for b in bank_entries:
        if b.txn_id not in claimed:
            reason = "no matching settlement record found"
            exceptions.append({
                "match_status": "exception",
                "settlement_ref": None,
                "bank_ref": b.txn_id,
                "confidence": None,
                "reason": reason,
            })
            audit_entries.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "settlement_ref": None,
                "bank_ref": b.txn_id,
                "match_status": "exception",
                "confidence": None,
                "reason": reason,
                "tier": "rule",
            })

    # A "reversed"/"pending" settlement has no live bank-side money movement
    # by definition (see the "skip the shortlist scoring" comment above) —
    # it can never have a genuine counterpart, so it isn't a matching
    # failure the engine could have avoided. match_rate below still counts
    # it against the denominator (an honest, literal "of everything we were
    # handed, what fraction matched"), but matchable_match_rate excludes it
    # to answer the separate, equally honest question "of what could
    # plausibly reconcile, what fraction did" — useful because the two can
    # diverge a lot on a batch with many reversals/pending settlements, and
    # blending them into one number hides that.
    settled_settlements = sum(1 for s in settlements if s.status == "settled")
    stats = {
        "total_settlements": len(settlements),
        "total_bank_entries": len(bank_entries),
        "settled_settlements": settled_settlements,
        "matched": len(matches),
        "rule_matched": sum(1 for m in matches if m["confidence"] not in ("llm-reasoned", "algo-reconstructed")),
        "algo_matched": sum(1 for m in matches if m["confidence"] == "algo-reconstructed"),
        "llm_matched": sum(1 for m in matches if m["confidence"] == "llm-reasoned"),
        "settlement_exceptions": sum(1 for e in exceptions if e["settlement_ref"]),
        "bank_exceptions": sum(1 for e in exceptions if e["bank_ref"] and not e["settlement_ref"]),
        "match_rate": round(len(matches) / len(settlements), 4) if settlements else 0.0,
        "matchable_match_rate": round(len(matches) / settled_settlements, 4) if settled_settlements else 0.0,
    }
    report("persisting", 0, 1)
    return matches, exceptions, audit_entries, stats


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_and_persist(settlement_path=None, bank_path=None, outdir=None, db_path=None,
                     use_llm=True, model=None, progress_cb=None,
                     settlement_source="csv", razorpay_key_id=None, razorpay_key_secret=None,
                     razorpay_from_ts=None, razorpay_to_ts=None):
    """Load the batch, run reconciliation, write matches/exceptions.csv, and
    persist the full audit trail to SQLite. Shared by the CLI (below) and
    the FastAPI /reconcile route, so both go through the exact same path.
    Returns {"run_id", "stats", "matches", "exceptions", "outdir", "db_path"}.

    settlement_source="csv" (default) loads settlement_path as a CSV via
    load_settlements() — existing behavior, completely unchanged.
    settlement_source="razorpay" instead fetches live settlements via
    razorpay_client.load_settlements_from_razorpay(), mapped into the same
    Settlement dataclass, so nothing below this point needs to know which
    source produced its input. Bank statements stay CSV-only either way —
    see docs/ADR-002 for why.
    """
    bank_path = Path(bank_path)
    if outdir:
        outdir = Path(outdir)
    elif settlement_source == "csv":
        outdir = Path(settlement_path).parent / "output"
    else:
        outdir = bank_path.parent / "output"
    outdir.mkdir(parents=True, exist_ok=True)
    db_path = Path(db_path) if db_path else (outdir / "audit.db")

    if settlement_source == "razorpay":
        # Deferred import: razorpay_client imports Settlement from this
        # module, so a top-level import here would be circular. By call
        # time reconcile is already fully loaded, so it's safe.
        from razorpay_client import load_settlements_from_razorpay
        settlements = load_settlements_from_razorpay(
            razorpay_key_id, razorpay_key_secret,
            from_ts=razorpay_from_ts, to_ts=razorpay_to_ts,
        )
        settlement_path = f"razorpay:{razorpay_from_ts or ''}-{razorpay_to_ts or ''}"
    else:
        settlement_path = Path(settlement_path)
        settlements = load_settlements(settlement_path)
    bank_entries = load_bank_entries(bank_path)

    matches, exceptions, audit_entries, stats = run_reconciliation(
        settlements, bank_entries, use_llm=use_llm, model=model, progress_cb=progress_cb
    )

    fieldnames = ["match_status", "settlement_ref", "bank_ref", "confidence", "reason"]
    write_csv(outdir / "matches.csv", matches, fieldnames)
    write_csv(outdir / "exceptions.csv", exceptions, fieldnames)

    model_used = None if not use_llm else (model or DEFAULT_MODEL)
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:6]}"
    conn = audit.connect(db_path)
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(),
                    settlement_path, bank_path, model_used, stats)
    audit.save_settlements(conn, run_id, settlements)
    audit.save_bank_entries(conn, run_id, bank_entries)
    audit.save_audit_entries(conn, run_id, audit_entries)
    conn.close()
    if progress_cb:
        progress_cb("persisting", 1, 1)

    return {
        "run_id": run_id, "stats": stats, "matches": matches, "exceptions": exceptions,
        "outdir": outdir, "db_path": db_path,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settlement", type=Path, default=Path("../data/settlement.csv"))
    parser.add_argument("--bank", type=Path, default=Path("../data/bank_statement.csv"))
    parser.add_argument("--outdir", type=Path, default=None,
                         help="default: same directory as --settlement, in an output/ subfolder")
    parser.add_argument("--db", type=Path, default=None,
                         help="audit DB path (default: <outdir>/audit.db)")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM tier (rules only)")
    parser.add_argument("--model", default=None, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--source", choices=["csv", "razorpay"], default="csv",
                         help="settlement data source (default: csv). razorpay reads "
                              "RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET from the environment "
                              "and ignores --settlement.")
    args = parser.parse_args()

    if args.source == "razorpay":
        result = run_and_persist(
            bank_path=args.bank, outdir=args.outdir, db_path=args.db,
            use_llm=not args.no_llm, model=args.model,
            settlement_source="razorpay",
            razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID"),
            razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET"),
        )
    else:
        result = run_and_persist(
            args.settlement, args.bank, outdir=args.outdir, db_path=args.db,
            use_llm=not args.no_llm, model=args.model,
        )

    print(json.dumps(result["stats"], indent=2))
    print(f"\nrun_id: {result['run_id']}")
    print(f"wrote {result['outdir'] / 'matches.csv'}")
    print(f"wrote {result['outdir'] / 'exceptions.csv'}")
    print(f"wrote {result['db_path']} (audit trail — query with: "
          f"python3 audit_cli.py --db {result['db_path']} trace <record_id>)")


if __name__ == "__main__":
    main()
