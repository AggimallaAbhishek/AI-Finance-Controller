from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

import audit
from reconcile import Settlement, BankEntry


@pytest.fixture
def conn(tmp_path):
    c = audit.connect(tmp_path / "test_audit.db")
    yield c
    c.close()


@pytest.fixture
def seeded(conn):
    """One settlement-side exception (STL1) and one bank-side exception
    (BTXN1), unrelated to each other, plus one already-matched pair
    (STL2/BTXN2) that a resolution should never be allowed to touch."""
    run_id = "run1"
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(),
                    "s.csv", "b.csv", None, {})
    audit.save_settlements(conn, run_id, [
        Settlement("STL1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "settled"),
        Settlement("STL2", "RZP2", Decimal("200.00"), date(2026, 7, 1), "settled"),
    ])
    audit.save_bank_entries(conn, run_id, [
        BankEntry("BTXN1", "RZPX", Decimal("150.00"), date(2026, 7, 3), "orphan"),
        BankEntry("BTXN2", "RZP2", Decimal("200.00"), date(2026, 7, 1), "n"),
    ])
    audit.save_audit_entries(conn, run_id, [
        {"timestamp": "t1", "settlement_ref": "STL1", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "no candidate", "tier": "rule"},
        {"timestamp": "t2", "settlement_ref": None, "bank_ref": "BTXN1",
         "match_status": "exception", "confidence": None, "reason": "no settlement", "tier": "rule"},
        {"timestamp": "t3", "settlement_ref": "STL2", "bank_ref": "BTXN2",
         "match_status": "matched", "confidence": "exact", "reason": "exact match", "tier": "rule"},
    ])
    return run_id


def test_resolve_settlement_exception_to_match(conn, seeded):
    result = audit.resolve_exception(conn, seeded, "STL1", "match", "manually verified",
                                      matched_record_id="BTXN1")
    assert result["match_status"] == "matched"

    matches = audit.list_matches(conn, seeded)
    resolved = next(m for m in matches if m["settlement_ref"] == "STL1")
    assert resolved["bank_ref"] == "BTXN1"
    assert resolved["tier"] == "human"
    assert resolved["confidence"] == "human-resolved"
    assert resolved["reason"] == "manually verified"


def test_resolve_bank_exception_to_match(conn, seeded):
    audit.resolve_exception(conn, seeded, "BTXN1", "match", "found it", matched_record_id="STL1")
    matches = audit.list_matches(conn, seeded)
    resolved = next(m for m in matches if m["bank_ref"] == "BTXN1")
    assert resolved["settlement_ref"] == "STL1"


def test_resolved_match_removes_both_sides_from_exceptions(conn, seeded):
    audit.resolve_exception(conn, seeded, "STL1", "match", "verified", matched_record_id="BTXN1")
    exceptions = audit.list_exceptions(conn, seeded)
    remaining_ids = {e["settlement_ref"] or e["bank_ref"] for e in exceptions}
    assert "STL1" not in remaining_ids
    assert "BTXN1" not in remaining_ids


def test_confirm_no_match_creates_human_tier_exception_row(conn, seeded):
    audit.resolve_exception(conn, seeded, "STL1", "no_match", "checked manually, genuinely unmatched")

    exceptions = audit.list_exceptions(conn, seeded)
    current = next(e for e in exceptions if e["settlement_ref"] == "STL1")
    assert current["tier"] == "human"
    assert current["reason"] == "checked manually, genuinely unmatched"
    # exactly one current row for STL1, not the stale original alongside it
    assert sum(1 for e in exceptions if e["settlement_ref"] == "STL1") == 1


def test_get_trace_preserves_full_resolution_history(conn, seeded):
    audit.resolve_exception(conn, seeded, "STL1", "no_match", "confirmed by ops")
    trace = audit.get_trace(conn, "STL1", seeded)
    reasons = [d["reason"] for d in trace["decisions"]]
    assert reasons == ["no candidate", "confirmed by ops"]  # original, then resolution, in order


def test_resolved_bank_exception_excluded_from_over_amount_listing(conn, seeded):
    # BTXN1 (Rs 150) would show up in an over-Rs-100 listing while it's a
    # live exception; once resolved it must not, or the Q&A tool that
    # backs this function would cite a stale, already-resolved record.
    before = audit.list_unmatched_bank_entries_over_amount(conn, seeded, 100)
    assert any(h["txn_id"] == "BTXN1" for h in before)

    audit.resolve_exception(conn, seeded, "BTXN1", "match", "verified", matched_record_id="STL1")

    after = audit.list_unmatched_bank_entries_over_amount(conn, seeded, 100)
    assert not any(h["txn_id"] == "BTXN1" for h in after)


def test_resolve_rejects_unknown_record(conn, seeded):
    with pytest.raises(ValueError):
        audit.resolve_exception(conn, seeded, "STL_NOPE", "no_match", "note")


def test_resolve_rejects_record_that_is_already_matched(conn, seeded):
    with pytest.raises(ValueError):
        audit.resolve_exception(conn, seeded, "STL2", "no_match", "note")


def test_resolve_match_rejects_counterpart_that_is_already_matched(conn, seeded):
    # STL1 is a genuine exception, but BTXN2 is already matched to STL2 —
    # must not be allowed to double-claim it.
    with pytest.raises(ValueError):
        audit.resolve_exception(conn, seeded, "STL1", "match", "note", matched_record_id="BTXN2")
