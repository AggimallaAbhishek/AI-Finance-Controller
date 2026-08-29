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
import hashlib
import json
import time
from pathlib import Path

import reconcile
from llm_matcher import get_llm_verdict, get_llm_verdicts_batch


def adapt_single_to_batch(llm_fn):
    """Wrap a single-item llm_fn (real, mock, or cached) into the
    llm_batch_fn shape by calling it once per item — lets --mock-llm and
    --cache validate the new batching/grouping code path in reconcile.py
    without needing a batch-shaped mock, though it doesn't exercise a real
    multi-settlement prompt (only --batch-size with neither flag does)."""
    def batch_fn(items, model=None):
        return {
            settlement_dict["settlement_id"]: llm_fn(settlement_dict, candidate_dicts, model=model)
            for settlement_dict, candidate_dicts in items
        }
    return batch_fn


def make_cached_llm(llm_fn, cache_path):
    """Wrap an llm_fn so identical (settlement, candidates, model) calls are
    answered from a local JSON cache instead of hitting Ollama again. Only
    used by this eval harness — reconcile.py's real code path never
    caches, since a live run should always reflect the current model.
    Speeds up repeated test iterations on the same batch after a code
    change: the first real run pays full LLM latency once; every rerun
    against the same data after that is near-instant."""
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    hits = [0]

    def cached(settlement_dict, candidate_dicts, model=None):
        key = json.dumps(
            {"s": settlement_dict, "c": candidate_dicts, "m": model or reconcile.DEFAULT_MODEL},
            sort_keys=True,
        )
        digest = hashlib.sha256(key.encode()).hexdigest()
        if digest in cache:
            hits[0] += 1
            return cache[digest]
        verdict = llm_fn(settlement_dict, candidate_dicts, model=model)
        cache[digest] = verdict
        cache_path.write_text(json.dumps(cache))
        return verdict

    cached.hits = hits
    return cached


def make_mock_llm(ground_truth_path):
    """Answer from ground_truth.csv instead of calling any model — for
    testing the engine's matching LOGIC (candidate shortlisting, tie-break,
    concurrency-safety, exception bookkeeping) at full speed, not real
    model reasoning quality. Never used by reconcile.py itself."""
    import csv
    expected = {}
    with open(ground_truth_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["settlement_id"] and row["expected_match"] == "true":
                expected[row["settlement_id"]] = row["bank_txn_id"]

    def mock(settlement_dict, candidate_dicts, model=None):
        sid = settlement_dict["settlement_id"]
        expected_bid = expected.get(sid)
        candidate_ids = {c["txn_id"] for c in candidate_dicts}
        if expected_bid in candidate_ids:
            return {"match_found": True, "matched_bank_txn_id": expected_bid, "reasoning": "mock-oracle"}
        return {"match_found": False, "matched_bank_txn_id": None, "reasoning": "mock-oracle: no correct candidate present"}

    return mock


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
    parser.add_argument("--mock-llm", action="store_true",
                         help="answer from ground_truth.csv instead of calling Ollama — tests engine "
                              "logic (shortlisting, concurrency-safety, bookkeeping) at full speed, "
                              "not real model quality")
    parser.add_argument("--cache", action="store_true",
                         help="cache real LLM verdicts to <dir>/.llm_cache.json; reruns on the same "
                              "batch reuse cached answers instead of re-calling Ollama")
    parser.add_argument("--batch-size", type=int, default=1,
                         help="settlements per LLM call (default 1 = one call per settlement). "
                              ">1 uses the real batched-prompt path unless --mock-llm/--cache is "
                              "also given, in which case that mock/cache is adapted per-item instead "
                              "of exercising a real multi-settlement prompt.")
    args = parser.parse_args()

    settlements = reconcile.load_settlements(args.dir / "settlement.csv")
    bank_entries = reconcile.load_bank_entries(args.dir / "bank_statement.csv")
    expected_for_settlement, expected_for_bank = load_ground_truth(args.dir / "ground_truth.csv")

    llm_fn = get_llm_verdict
    if args.mock_llm:
        llm_fn = make_mock_llm(args.dir / "ground_truth.csv")
    elif args.cache:
        llm_fn = make_cached_llm(get_llm_verdict, args.dir / ".llm_cache.json")

    if args.batch_size > 1:
        llm_batch_fn = get_llm_verdicts_batch if not (args.mock_llm or args.cache) else adapt_single_to_batch(llm_fn)
    else:
        llm_batch_fn = get_llm_verdicts_batch

    stage_times = {}
    t_stage_start = {"t": time.monotonic()}

    def on_progress(stage, done, total):
        if done == total:
            stage_times[stage] = time.monotonic() - t_stage_start["t"]
            t_stage_start["t"] = time.monotonic()

    t0 = time.monotonic()
    matches, exceptions, audit_entries, stats = reconcile.run_reconciliation(
        settlements, bank_entries, use_llm=not args.no_llm, llm_fn=llm_fn,
        model=args.model, progress_cb=on_progress,
        batch_size=args.batch_size, llm_batch_fn=llm_batch_fn,
    )
    elapsed = time.monotonic() - t0

    by_category = score(matches, exceptions, expected_for_settlement, expected_for_bank)

    print(f"batch: {args.dir}")
    print(f"settlements={len(settlements)} bank_entries={len(bank_entries)} "
          f"use_llm={not args.no_llm} model={args.model or reconcile.DEFAULT_MODEL if not args.no_llm else '-'}")
    print(f"wall_clock_seconds={elapsed:.2f}  stage_times={ {k: round(v, 2) for k, v in stage_times.items()} }")
    if args.cache and hasattr(llm_fn, "hits"):
        print(f"llm cache hits: {llm_fn.hits[0]}")
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
