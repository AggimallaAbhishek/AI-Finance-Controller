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


def make_run(conn, run_id="run1"):
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(),
                    "settlement.csv", "bank.csv", "test-model", {"match_rate": 0.9})
    return run_id


def test_save_and_get_run_roundtrip(conn):
    make_run(conn, "run1")
    run = audit.get_run(conn, "run1")
    assert run["run_id"] == "run1"
    assert run["model"] == "test-model"


def test_get_run_returns_none_for_unknown_run(conn):
    assert audit.get_run(conn, "does-not-exist") is None


def test_latest_run_id_returns_most_recent_by_timestamp(conn):
    audit.save_run(conn, "older", "2026-01-01T00:00:00+00:00", "s.csv", "b.csv", None, {})
    audit.save_run(conn, "newer", "2026-06-01T00:00:00+00:00", "s.csv", "b.csv", None, {})
    assert audit.latest_run_id(conn) == "newer"


def test_get_trace_returns_source_records_and_decision(conn):
    run_id = make_run(conn)
    s = Settlement("STL1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "settled")
    b = BankEntry("BTXN1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "narration")
    audit.save_settlements(conn, run_id, [s])
    audit.save_bank_entries(conn, run_id, [b])
    audit.save_audit_entries(conn, run_id, [{
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "settlement_ref": "STL1", "bank_ref": "BTXN1", "match_status": "matched",
        "confidence": "exact", "reason": "test reason", "tier": "rule",
    }])

    trace = audit.get_trace(conn, "STL1", run_id)
    assert trace["settlement_record"]["reference_id"] == "RZP1"
    assert trace["counterpart_bank_record"]["txn_id"] == "BTXN1"
    assert trace["decisions"][0]["reason"] == "test reason"


def test_get_trace_parses_candidates_considered_into_a_list(conn):
    # Regression: this field is stored as a JSON string; a prior bug left
    # it unparsed for one of get_trace's two callers.
    run_id = make_run(conn)
    audit.save_audit_entries(conn, run_id, [{
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "settlement_ref": "STL1", "bank_ref": "BTXN1", "match_status": "matched",
        "confidence": "llm-reasoned", "reason": "r", "tier": "llm",
        "candidates_considered": ["BTXN1", "BTXN2"],
    }])

    trace = audit.get_trace(conn, "STL1", run_id)
    assert trace["decisions"][0]["candidates_considered"] == ["BTXN1", "BTXN2"]
    assert isinstance(trace["decisions"][0]["candidates_considered"], list)


def test_list_matches_and_exceptions_filter_by_status(conn):
    run_id = make_run(conn)
    audit.save_audit_entries(conn, run_id, [
        {"timestamp": "t", "settlement_ref": "STL1", "bank_ref": "BTXN1",
         "match_status": "matched", "confidence": "exact", "reason": "r", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": "STL2", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "r", "tier": "rule"},
    ])

    assert len(audit.list_matches(conn, run_id)) == 1
    assert len(audit.list_exceptions(conn, run_id)) == 1


def test_list_matches_are_enriched_with_amount_and_date(conn):
    # Phase 11: the Matches/Exceptions tabs filter by amount range and date
    # range, which audit_log itself doesn't carry (only refs) — enrich from
    # the source settlement/bank rows at read time.
    run_id = make_run(conn)
    s = Settlement("STL1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "settled")
    b = BankEntry("BTXN1", "RZP1", Decimal("100.00"), date(2026, 7, 3), "n")
    audit.save_settlements(conn, run_id, [s])
    audit.save_bank_entries(conn, run_id, [b])
    audit.save_audit_entries(conn, run_id, [{
        "timestamp": "t", "settlement_ref": "STL1", "bank_ref": "BTXN1",
        "match_status": "matched", "confidence": "fuzzy-date", "reason": "r", "tier": "rule",
    }])

    match = audit.list_matches(conn, run_id)[0]
    # Settlement side wins when both exist — an arbitrary but consistent
    # choice, since the two can differ within tolerance.
    assert match["amount"] == "100.00"
    assert match["date"] == "2026-07-01"


def test_list_exceptions_are_enriched_from_whichever_side_exists(conn):
    run_id = make_run(conn)
    b = BankEntry("BTXN1", "RZP_UNRELATED", Decimal("250.00"), date(2026, 7, 5), "n")
    audit.save_bank_entries(conn, run_id, [b])
    audit.save_audit_entries(conn, run_id, [{
        "timestamp": "t", "settlement_ref": None, "bank_ref": "BTXN1",
        "match_status": "exception", "confidence": None, "reason": "r", "tier": "rule",
    }])

    exception = audit.list_exceptions(conn, run_id)[0]
    assert exception["amount"] == "250.00"
    assert exception["date"] == "2026-07-05"


def test_list_unmatched_bank_entries_over_amount_excludes_at_threshold(conn):
    run_id = make_run(conn)
    b = BankEntry("BTXN1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "n")
    audit.save_bank_entries(conn, run_id, [b])
    audit.save_audit_entries(conn, run_id, [{
        "timestamp": "t", "settlement_ref": None, "bank_ref": "BTXN1",
        "match_status": "exception", "confidence": None, "reason": "r", "tier": "rule",
    }])

    # Strictly greater-than: exactly at the threshold should not qualify.
    assert audit.list_unmatched_bank_entries_over_amount(conn, run_id, 100) == []
    hits = audit.list_unmatched_bank_entries_over_amount(conn, run_id, 99.99)
    assert len(hits) == 1
    assert hits[0]["txn_id"] == "BTXN1"
