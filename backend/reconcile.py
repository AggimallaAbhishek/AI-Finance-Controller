"""Reconciliation engine: matches settlement.csv against bank_statement.csv.

Tier 1-3 (rules, deterministic): exact reference_id join, then within
DATE_TOLERANCE_DAYS / AMOUNT_TOLERANCE_RS.
Tier 4 (Ollama): records the rules can't confidently resolve get sent, with
their top candidate bank entries, for a reasoned match/no-match verdict.
Anything left over becomes an exception.

Runnable as a script:
  python reconcile.py --settlement ../data/settlement.csv --bank ../data/bank_statement.csv
"""

import argparse
import csv
import difflib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import audit
from llm_matcher import get_llm_verdict, DEFAULT_MODEL

# Configurable without a code change — see docs/glossary.md for what these
# tolerances mean. Defaults match the ones the batch was designed against.
DATE_TOLERANCE_DAYS = int(os.environ.get("RECONCILE_DATE_TOLERANCE_DAYS", "2"))
AMOUNT_TOLERANCE_RS = Decimal(os.environ.get("RECONCILE_AMOUNT_TOLERANCE_RS", "10"))
CANDIDATE_SCORE_FLOOR = 0.45
MAX_CANDIDATES = 3


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


def rule_tier(settlement, bank, date_tolerance_days=None, amount_tolerance_rs=None):
    """Return (confidence, reason) if settlement/bank match within rule
    tolerance, else None. Requires an exact reference_id match — that's what
    makes a rule verdict trustworthy without reasoning over free text.
    Tolerances default to the module-level (environment-configurable)
    constants; pass explicit values to override per call."""
    date_tolerance_days = DATE_TOLERANCE_DAYS if date_tolerance_days is None else date_tolerance_days
    amount_tolerance_rs = AMOUNT_TOLERANCE_RS if amount_tolerance_rs is None else amount_tolerance_rs

    if settlement.reference_id != bank.reference_id:
        return None
    date_diff = abs((settlement.date - bank.date).days)
    amount_diff = abs(settlement.amount - bank.amount)

    if date_diff == 0 and amount_diff == 0:
        return "exact", "reference_id, amount, and date all matched exactly"
    if amount_diff == 0 and date_diff <= date_tolerance_days:
        return "fuzzy-date", (
            f"reference_id and amount matched exactly; date differs by "
            f"{date_diff} day(s), within {date_tolerance_days}-day tolerance"
        )
    if date_diff == 0 and amount_diff <= amount_tolerance_rs:
        return "fuzzy-amount", (
            f"reference_id and date matched exactly; amount differs by "
            f"Rs {amount_diff}, within Rs {amount_tolerance_rs} tolerance"
        )
    if date_diff <= date_tolerance_days and amount_diff <= amount_tolerance_rs:
        return "fuzzy-date-amount", (
            f"reference_id matched exactly; date differs by {date_diff} day(s) "
            f"and amount by Rs {amount_diff}, both within tolerance"
        )
    return None


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
                        progress_cb=None):
    """Returns (matches, exceptions, audit_entries, stats).

    progress_cb(stage, done, total), if given, is called with real counts as
    each tier processes — stages "rules", "llm" (only if any settlement
    falls to it), "persisting" — so a caller (the async /reconcile job) can
    show real progress instead of a spinner that looks stuck."""
    def report(stage, done, total):
        if progress_cb:
            progress_cb(stage, done, total)

    bank_by_id = {b.txn_id: b for b in bank_entries}
    claimed = set()
    matches = []
    audit_entries = []
    unresolved = []

    settlements_sorted = sorted(settlements, key=lambda s: s.settlement_id)

    # Tier 1-3: rules
    for i, s in enumerate(settlements_sorted):
        best = None  # (b, confidence, reason, amount_diff, date_diff)
        for b in bank_entries:
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

    # Tier 4: LLM for the ambiguous middle
    exceptions = []
    for i, s in enumerate(unresolved):
        unclaimed_bank = [b for b in bank_entries if b.txn_id not in claimed]
        candidates = shortlist_candidates(s, unclaimed_bank)

        if not use_llm or not candidates:
            if not use_llm:
                reason = "LLM tier skipped (--no-llm); no rule match found"
                if candidates:
                    reason += f"; {len(candidates)} candidate(s) existed but were not reviewed"
                tier = "skipped-llm"
            else:
                reason = "no plausible bank counterpart found (no candidates cleared the similarity floor)"
                tier = "rule"
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
                "tier": tier,
            })
            report("llm", i + 1, len(unresolved))
            continue

        candidate_dicts = [
            {"txn_id": b.txn_id, "reference_id": b.reference_id, "amount": str(b.amount),
             "date": b.date.isoformat(), "narration": b.narration}
            for b in candidates
        ]
        settlement_dict = {
            "settlement_id": s.settlement_id, "reference_id": s.reference_id,
            "amount": str(s.amount), "date": s.date.isoformat(), "status": s.status,
        }
        verdict = llm_fn(settlement_dict, candidate_dicts, model=model)

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
                "candidates_considered": [c["txn_id"] for c in candidate_dicts],
            })
        else:
            reason = f"LLM reviewed {len(candidates)} candidate(s), no match: {verdict['reasoning']}"
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
                "candidates_considered": [c["txn_id"] for c in candidate_dicts],
            })
        report("llm", i + 1, len(unresolved))

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

    stats = {
        "total_settlements": len(settlements),
        "total_bank_entries": len(bank_entries),
        "matched": len(matches),
        "rule_matched": sum(1 for m in matches if m["confidence"] != "llm-reasoned"),
        "llm_matched": sum(1 for m in matches if m["confidence"] == "llm-reasoned"),
        "settlement_exceptions": sum(1 for e in exceptions if e["settlement_ref"]),
        "bank_exceptions": sum(1 for e in exceptions if e["bank_ref"] and not e["settlement_ref"]),
        "match_rate": round(len(matches) / len(settlements), 4) if settlements else 0.0,
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
