"""Eval harness: run the reconciliation engine against a synthetic batch and
score its output against that batch's ground_truth.csv (dev-only — the
engine itself never reads ground truth).

Reports, per ground-truth category:
  - TP: engine matched exactly the expected counterpart
  - FP: engine matched something that ground truth says shouldn't match
        (either a wrong counterpart, or a record that should be an
        exception but got force-matched)
  - FN: ground truth expects a match but the engine produced an exception
  - TN: ground truth expects no match and the engine produced an exception

Also reports wall-clock time and how many records reached the LLM tier,
so it can be used to compare before/after an optimization (rule-tier
changes, LLM parallelization, etc.) on the same batch.

Usage:
  python eval_reconcile.py --dir ../data/batch_1000 [--no-llm] [--model MODEL]
"""

import argparse
import time
from pathlib import Path

import reconcile


def load_ground_truth(path):
    expected_for_settlement = {}  # settlement_id -> (expected_bank_txn_id or None, category)
    expected_for_bank = {}        # bank_txn_id -> (expected_settlement_id or None, category)
    with open(path, newline="") as f:
        import csv
        for row in csv.DictReader(f):
            sid, bid = row["settlement_id"], row["bank_txn_id"]
            expect = row["expected_match"] == "true"
            category = row["category"]
            if sid:
                expected_for_settlement[sid] = (bid if expect else None, category)
            if bid:
                expected_for_bank[bid] = (sid if expect else None, category)
    return expected_for_settlement, expected_for_bank


def score(matches, exceptions, expected_for_settlement, expected_for_bank):
    actual_settlement_to_bank = {m["settlement_ref"]: m["bank_ref"] for m in matches if m["settlement_ref"]}
    actual_bank_to_settlement = {m["bank_ref"]: m["settlement_ref"] for m in matches if m["bank_ref"]}

    by_category = {}  # category -> {tp, fp, fn, tn}

    def bump(category, key):
        by_category.setdefault(category, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})[key] += 1

    # A matched-pair ground-truth row appears twice — once keyed by
    # settlement_id, once by bank_txn_id, both describing the same pair.
    # Score it once (from the settlement side) and skip its bank_txn_id
    # counterpart entirely when iterating the bank side below, regardless
    # of whether the engine actually produced that match — otherwise every
    # false negative (and every true positive) double-counts.
    consumed_bank_ids = {bid for bid, category in expected_for_settlement.values() if bid is not None}

    for sid, (expected_bid, category) in expected_for_settlement.items():
        actual_bid = actual_settlement_to_bank.get(sid)
        if expected_bid is not None:
            if actual_bid == expected_bid:
                bump(category, "tp")
            else:
                bump(category, "fn")
        else:
            if actual_bid is None:
                bump(category, "tn")
            else:
                bump(category, "fp")

    for bid, (expected_sid, category) in expected_for_bank.items():
        if bid in consumed_bank_ids:
            continue  # already scored from the settlement side above
        actual_sid = actual_bank_to_settlement.get(bid)
        if expected_sid is not None:
            bump(category, "fn")
        else:
            if actual_sid is None:
                bump(category, "tn")
            else:
                bump(category, "fp")

    return by_category


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True,
                         help="directory containing settlement.csv, bank_statement.csv, ground_truth.csv")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    settlements = reconcile.load_settlements(args.dir / "settlement.csv")
    bank_entries = reconcile.load_bank_entries(args.dir / "bank_statement.csv")
    expected_for_settlement, expected_for_bank = load_ground_truth(args.dir / "ground_truth.csv")

    stage_times = {}
    t_stage_start = {"t": time.monotonic()}

    def on_progress(stage, done, total):
        if done == total:
            stage_times[stage] = time.monotonic() - t_stage_start["t"]
            t_stage_start["t"] = time.monotonic()

    t0 = time.monotonic()
    matches, exceptions, audit_entries, stats = reconcile.run_reconciliation(
        settlements, bank_entries, use_llm=not args.no_llm, model=args.model, progress_cb=on_progress,
    )
    elapsed = time.monotonic() - t0

    by_category = score(matches, exceptions, expected_for_settlement, expected_for_bank)

    print(f"batch: {args.dir}")
    print(f"settlements={len(settlements)} bank_entries={len(bank_entries)} "
          f"use_llm={not args.no_llm} model={args.model or reconcile.DEFAULT_MODEL if not args.no_llm else '-'}")
    print(f"wall_clock_seconds={elapsed:.2f}  stage_times={ {k: round(v, 2) for k, v in stage_times.items()} }")
    print(f"engine stats: {stats}")
    print()
    print(f"{'category':<28}{'tp':>6}{'fp':>6}{'fn':>6}{'tn':>6}")
    total_tp = total_fp = total_fn = total_tn = 0
    for category, counts in sorted(by_category.items()):
        print(f"{category:<28}{counts['tp']:>6}{counts['fp']:>6}{counts['fn']:>6}{counts['tn']:>6}")
        total_tp += counts["tp"]
        total_fp += counts["fp"]
        total_fn += counts["fn"]
        total_tn += counts["tn"]
    print(f"{'TOTAL':<28}{total_tp:>6}{total_fp:>6}{total_fn:>6}{total_tn:>6}")

    correct = total_tp + total_tn
    total = correct + total_fp + total_fn
    accuracy = correct / total if total else 0.0
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 1.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 1.0
    print(f"\naccuracy={accuracy:.4f}  precision={precision:.4f}  recall={recall:.4f}")
    if total_fp:
        print(f"WARNING: {total_fp} false positive(s) — wrong or spurious match(es)")


if __name__ == "__main__":
    main()
