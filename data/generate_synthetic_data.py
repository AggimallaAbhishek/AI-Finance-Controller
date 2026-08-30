"""Generate synthetic settlement.csv / bank_statement.csv pairs for the
AI Finance Controller reconciliation engine.

Also writes ground_truth.csv — the intended pairing + category per record.
This file is for OUR OWN validation of the reconciliation engine's output
(Phase 2/7 testing) and must never be read by the engine itself; feeding it
ground truth would make the "honest match rate" claim meaningless.

Rule-tier tolerances this batch is designed against (must match the
reconciliation engine in backend/reconcile.py):
  - date drift  <= 2 days  -> rule-resolved (fuzzy-date)
  - amount diff <= Rs 10   -> rule-resolved (fuzzy-amount)
  - beyond both            -> LLM-reasoned tier or exception

Usage:
  python generate_synthetic_data.py --count 60 --seed 42
  python generate_synthetic_data.py --count 60 --seed 7 --outdir ../data   # a fresh, differently-seeded batch for Phase 7
"""

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

BASE_DATE = date(2026, 7, 1)
DATE_SPREAD_DAYS = 14

CLEAN_NARRATIONS = [
    "UPI-RAZORPAY SOFTWARE PVT LTD-{ref}",
    "NEFT CR-{ref}-RAZORPAY",
    "IMPS/{ref}/RAZORPAY SETTLEMENT",
    "RTGS-{ref}-RAZORPAY SOFTWARE PVT LTD",
]

# Narration still names the merchant/order clearly, but the reference_id
# column itself gets mangled by the (simulated) bank export.
NOISY_NARRATIONS = [
    "UPI-RAZORPAY SETTLEMENT ORDER {ref_tail}",
    "NEFT CR RAZORPAY SOFTWARE-{ref_tail}",
    "IMPS/RZP/{ref_tail}/PAYOUT",
]

ORPHAN_NARRATIONS = [
    "ATM WDL {city}",
    "SWIGGY ORDER PAYMENT",
    "ELECTRICITY BILL AUTOPAY",
    "SALARY CREDIT XYZ CORP",
    "ZOMATO ONLINE ORDER",
    "AMAZON RETAIL PAYMENT",
    "NETFLIX SUBSCRIPTION",
    "IRCTC TICKET BOOKING",
]

CITIES = ["BLR", "MUM", "DEL", "HYD", "CHN"]


def rand_amount(rng, lo=500, hi=75000):
    return round(rng.uniform(lo, hi), 2)


def rand_date(rng):
    return BASE_DATE + timedelta(days=rng.randint(0, DATE_SPREAD_DAYS))


def _make_unique_id(rng, prefix, digits, seen):
    """Retry on collision within this batch — plain rng.randint alone hits
    real birthday-bound collisions well within the batch sizes this
    generator is asked to produce (e.g. ~14 duplicate 8-digit settlement_ids
    confirmed at count=50000), and a duplicate settlement_id isn't just a
    cosmetic risk: audit.save_settlements()'s (run_id, settlement_id)
    PRIMARY KEY makes it a real IntegrityError crash the first time that
    batch is actually reconciled through the app, not merely a synthetic-
    data quirk. `seen` is scoped to one build_batch() call/one output
    batch — collisions across unrelated batches don't matter, since their
    CSVs are never loaded together."""
    lo, hi = 10 ** (digits - 1), 10**digits - 1
    while True:
        candidate = f"{prefix}{rng.randint(lo, hi)}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate


def make_reference_id(rng, seen):
    return _make_unique_id(rng, "RZP", 10, seen)


def make_settlement_id(rng, seen):
    return _make_unique_id(rng, "STL", 8, seen)


def make_txn_id(rng, seen):
    return _make_unique_id(rng, "BTXN", 10, seen)


def corrupt_reference_id(rng, ref):
    """Simulate a bank export mangling the reference_id column."""
    style = rng.choice(["lowercase", "truncate", "transpose"])
    if style == "lowercase":
        return ref.lower()
    if style == "truncate":
        return ref[:-3]
    chars = list(ref)
    i = rng.randrange(len(chars) - 1)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def build_batch(count, seed):
    rng = random.Random(seed)
    seen_settlement_ids = set()
    seen_txn_ids = set()
    # Shared by pair references AND orphan bank rows' own reference_id
    # (line below) — an orphan coincidentally sharing a reference_id with
    # some settlement would stop being a genuine orphan.
    seen_refs = set()

    n_exact = round(count * 0.55)
    n_fuzzy_date = round(count * 0.15)
    n_fuzzy_amount = round(count * 0.10)
    n_llm = round(count * 0.10)
    n_settlement_only = count - (n_exact + n_fuzzy_date + n_fuzzy_amount + n_llm)
    # Mirrors n_settlement_only exactly (rather than a fixed count) so
    # settlement.csv and bank_statement.csv always end up the same length:
    # every matched category already contributes exactly one row to each
    # side, so the two "no counterpart on the other side" buckets need to
    # be equal in size too, not just each individually non-empty. A fixed
    # small n_orphans (previously 6) matched settlement.csv's length only
    # by coincidence at count=60 and silently diverged from it at every
    # other batch size.
    n_orphans = n_settlement_only

    settlement_rows = []
    bank_rows = []
    ground_truth_rows = []

    def add_matched_pair(category, settlement_id, ref, amount, s_date, b_date,
                          b_amount, narration):
        txn_id = make_txn_id(rng, seen_txn_ids)
        settlement_rows.append({
            "settlement_id": settlement_id,
            "reference_id": ref,
            "amount": f"{amount:.2f}",
            "date": s_date.isoformat(),
            "status": "settled",
        })
        bank_rows.append({
            "txn_id": txn_id,
            "reference_id": ref,
            "amount": f"{b_amount:.2f}",
            "date": b_date.isoformat(),
            "narration": narration,
        })
        ground_truth_rows.append({
            "settlement_id": settlement_id,
            "bank_txn_id": txn_id,
            "category": category,
            "expected_match": "true",
        })

    # Exact matches
    for _ in range(n_exact):
        ref = make_reference_id(rng, seen_refs)
        amount = rand_amount(rng)
        s_date = rand_date(rng)
        narration = rng.choice(CLEAN_NARRATIONS).format(ref=ref)
        add_matched_pair("exact", make_settlement_id(rng, seen_settlement_ids), ref, amount,
                          s_date, s_date, amount, narration)

    # Fuzzy date-drift matches (1-2 days, within rule tolerance)
    for _ in range(n_fuzzy_date):
        ref = make_reference_id(rng, seen_refs)
        amount = rand_amount(rng)
        s_date = rand_date(rng)
        b_date = s_date + timedelta(days=rng.choice([1, 2]))
        narration = rng.choice(CLEAN_NARRATIONS).format(ref=ref)
        add_matched_pair("fuzzy_date", make_settlement_id(rng, seen_settlement_ids), ref, amount,
                          s_date, b_date, amount, narration)

    # Fuzzy amount matches (Rs 1-9 deduction, within rule tolerance)
    for _ in range(n_fuzzy_amount):
        ref = make_reference_id(rng, seen_refs)
        amount = rand_amount(rng)
        b_amount = round(amount - rng.uniform(1, 9), 2)
        s_date = rand_date(rng)
        narration = rng.choice(CLEAN_NARRATIONS).format(ref=ref)
        add_matched_pair("fuzzy_amount", make_settlement_id(rng, seen_settlement_ids), ref, amount,
                          s_date, s_date, b_amount, narration)

    # LLM-reasoned: reference_id corrupted AND date drifts 3-5 days
    # (beyond rule tolerance), but narration still names the merchant/order.
    for _ in range(n_llm):
        ref = make_reference_id(rng, seen_refs)
        noisy_ref = corrupt_reference_id(rng, ref)
        amount = rand_amount(rng)
        s_date = rand_date(rng)
        b_date = s_date + timedelta(days=rng.choice([3, 4, 5]))
        narration = rng.choice(NOISY_NARRATIONS).format(ref_tail=ref[-6:])
        add_matched_pair("llm_reasoned", make_settlement_id(rng, seen_settlement_ids), ref, amount,
                          s_date, b_date, amount, narration)
        # overwrite the just-appended bank row's reference_id with the noisy one
        # (corrupt_reference_id's output is deliberately NOT deduplicated: it
        # lands in bank_entries.reference_id, which is not a primary/unique
        # key anywhere, so a coincidental collision there is a rare, low-
        # impact matching-ambiguity risk, not a crash risk — not worth the
        # complexity of retrying the corruption style/positions to avoid it)
        bank_rows[-1]["reference_id"] = noisy_ref

    # Settlement-only exceptions: reversed/pending, no bank counterpart
    for _ in range(n_settlement_only):
        settlement_id = make_settlement_id(rng, seen_settlement_ids)
        ref = make_reference_id(rng, seen_refs)
        amount = rand_amount(rng)
        s_date = rand_date(rng)
        status = rng.choice(["reversed", "pending"])
        settlement_rows.append({
            "settlement_id": settlement_id,
            "reference_id": ref,
            "amount": f"{amount:.2f}",
            "date": s_date.isoformat(),
            "status": status,
        })
        ground_truth_rows.append({
            "settlement_id": settlement_id,
            "bank_txn_id": "",
            "category": "settlement_only_exception",
            "expected_match": "false",
        })

    # Bank-only orphans: unrelated transactions, no settlement counterpart
    for _ in range(n_orphans):
        txn_id = make_txn_id(rng, seen_txn_ids)
        narration = rng.choice(ORPHAN_NARRATIONS).format(city=rng.choice(CITIES))
        bank_rows.append({
            "txn_id": txn_id,
            "reference_id": make_reference_id(rng, seen_refs),
            "amount": f"{rand_amount(rng, 100, 20000):.2f}",
            "date": rand_date(rng).isoformat(),
            "narration": narration,
        })
        ground_truth_rows.append({
            "settlement_id": "",
            "bank_txn_id": txn_id,
            "category": "bank_only_exception",
            "expected_match": "false",
        })

    rng.shuffle(settlement_rows)
    rng.shuffle(bank_rows)
    return settlement_rows, bank_rows, ground_truth_rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60,
                         help="number of settlement records (default 60)")
    parser.add_argument("--seed", type=int, default=42,
                         help="random seed, for reproducible batches")
    parser.add_argument("--outdir", type=Path, default=Path(__file__).parent,
                         help="output directory (default: this script's dir)")
    args = parser.parse_args()

    settlement_rows, bank_rows, ground_truth_rows = build_batch(args.count, args.seed)

    args.outdir.mkdir(parents=True, exist_ok=True)
    write_csv(args.outdir / "settlement.csv", settlement_rows,
               ["settlement_id", "reference_id", "amount", "date", "status"])
    write_csv(args.outdir / "bank_statement.csv", bank_rows,
               ["txn_id", "reference_id", "amount", "date", "narration"])
    write_csv(args.outdir / "ground_truth.csv", ground_truth_rows,
               ["settlement_id", "bank_txn_id", "category", "expected_match"])

    print(f"seed={args.seed} count={args.count}")
    print(f"  settlement.csv     : {len(settlement_rows)} rows")
    print(f"  bank_statement.csv : {len(bank_rows)} rows")
    print(f"  ground_truth.csv   : {len(ground_truth_rows)} rows (dev-only, not for the engine)")


if __name__ == "__main__":
    main()
