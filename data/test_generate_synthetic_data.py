"""Tests for generate_synthetic_data.py's data-quality invariants.

Not part of the backend pytest suite (backend/pytest.ini scopes testpaths
to backend/tests) — run directly:
    python3 -m pytest data/test_generate_synthetic_data.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_synthetic_data import build_batch


def test_no_duplicate_settlement_ids_at_scale():
    # A duplicate settlement_id isn't just a labeling quirk: audit.py's
    # `settlements` table has PRIMARY KEY (run_id, settlement_id), so a
    # duplicate crashes the real app with an IntegrityError the first time
    # this batch is actually reconciled — confirmed directly against
    # audit.save_settlements() before this test was written.
    settlement_rows, _, _ = build_batch(50000, seed=42)
    ids = [r["settlement_id"] for r in settlement_rows]
    assert len(ids) == len(set(ids))


def test_no_duplicate_txn_ids_at_scale():
    # Same PRIMARY KEY risk as settlement_id, on bank_entries(run_id, txn_id).
    _, bank_rows, _ = build_batch(50000, seed=42)
    ids = [r["txn_id"] for r in bank_rows]
    assert len(ids) == len(set(ids))


def test_no_duplicate_reference_ids_at_scale():
    # Every settlement (matched or settlement-only) is assigned exactly one
    # reference_id; every matched bank row shares its settlement's
    # reference_id by design (that's the join key, not a duplicate); every
    # orphan bank row gets its own independent one. None of those should
    # collide with each other — a coincidental collision would mean two
    # unrelated settlements share an identifying reference, or an "orphan"
    # accidentally becomes matchable to a settlement it has nothing to do
    # with.
    settlement_rows, bank_rows, ground_truth_rows = build_batch(50000, seed=42)
    orphan_txn_ids = {r["bank_txn_id"] for r in ground_truth_rows if r["category"] == "bank_only_exception"}
    bank_by_txn = {b["txn_id"]: b for b in bank_rows}

    refs = [s["reference_id"] for s in settlement_rows]
    refs += [bank_by_txn[txn_id]["reference_id"] for txn_id in orphan_txn_ids]
    assert len(refs) == len(set(refs))


def test_settlement_and_bank_row_counts_stay_equal_across_scales():
    # Regression: n_orphans was once a fixed 6 regardless of batch size,
    # while settlement-only exceptions scaled with --count — the two only
    # matched by coincidence at count=60, diverging at every other size
    # (e.g. 500 settlements vs. 456 bank entries) until n_orphans was tied
    # to n_settlement_only.
    for count in [60, 500, 1000, 10000, 50000]:
        settlement_rows, bank_rows, _ = build_batch(count, seed=42)
        assert len(settlement_rows) == count
        assert len(bank_rows) == count
