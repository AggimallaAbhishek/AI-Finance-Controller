from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

import audit
from qa_agent import _build_tool_dispatch
from reconcile import BankEntry, Settlement


@pytest.fixture
def conn(tmp_path):
    c = audit.connect(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def run_with_one_resolution(conn):
    """2 rule matches, 1 open exception, plus one settlement/bank exception
    pair that gets resolved into a match — mirrors what a real batch with
    one human resolution looks like."""
    run_id = "run1"
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(), "s.csv", "b.csv", None, {
        "total_settlements": 4, "total_bank_entries": 4,
        "matched": 2, "rule_matched": 2, "llm_matched": 0,
        "settlement_exceptions": 2, "bank_exceptions": 1,
        "match_rate": 0.5,
    })
    audit.save_settlements(conn, run_id, [
        Settlement("STL1", "R1", Decimal("10"), date(2026, 7, 1), "settled"),
        Settlement("STL2", "R2", Decimal("20"), date(2026, 7, 1), "settled"),
        Settlement("STL3", "R3", Decimal("30"), date(2026, 7, 1), "settled"),
    ])
    audit.save_bank_entries(conn, run_id, [
        BankEntry("BTXN1", "R1", Decimal("10"), date(2026, 7, 1), "n"),
        BankEntry("BTXN3", "R3", Decimal("30"), date(2026, 7, 1), "n"),
    ])
    audit.save_audit_entries(conn, run_id, [
        {"timestamp": "t", "settlement_ref": "STL1", "bank_ref": "BTXN1",
         "match_status": "matched", "confidence": "exact", "reason": "r", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": "STL2", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "no match", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": "STL3", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "no match", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": None, "bank_ref": "BTXN3",
         "match_status": "exception", "confidence": None, "reason": "orphan", "tier": "rule"},
    ])
    # Resolve STL3 <-> BTXN3 into a human match, leaving STL2 as the one
    # genuinely still-open exception.
    audit.resolve_exception(conn, run_id, "STL3", "match", "verified", matched_record_id="BTXN3")
    return run_id


def test_get_stats_reflects_current_state_not_the_frozen_snapshot(conn, run_with_one_resolution):
    # Regression: get_stats() used to return the run's stored stats_json —
    # frozen at reconcile time, never updated by a later resolution. A
    # user asking the Q&A agent "how many exceptions" got a DIFFERENT,
    # stale number than the dashboard (which computes live) — the exact
    # kind of contradiction this project's honesty bar exists to prevent.
    dispatch = _build_tool_dispatch(conn, run_with_one_resolution)
    stats = dispatch["get_stats"]()

    assert stats["matched"] == 2  # 1 original rule match + 1 human resolution
    assert stats["rule_matched"] == 1
    assert stats["human_resolved"] == 1
    assert stats["settlement_exceptions"] == 1  # only STL2 remains open
    assert stats["bank_exceptions"] == 0  # BTXN3 was resolved into the match


def test_list_matches_can_filter_to_human_resolved(conn, run_with_one_resolution):
    # Regression: the tool schema's confidence enum didn't include
    # "human-resolved", so the Q&A agent had no correct way to ask for
    # human-resolved matches specifically — confirmed live, the model
    # answered "the available data does not indicate" for a question the
    # data actually could answer.
    dispatch = _build_tool_dispatch(conn, run_with_one_resolution)
    human_matches = dispatch["list_matches"](confidence="human-resolved")
    assert len(human_matches) == 1
    assert human_matches[0]["settlement_ref"] == "STL3"


def test_human_resolved_is_a_valid_tool_schema_enum_value():
    from qa_agent import TOOLS_SCHEMA

    list_matches_tool = next(t for t in TOOLS_SCHEMA if t["function"]["name"] == "list_matches")
    enum = list_matches_tool["function"]["parameters"]["properties"]["confidence"]["enum"]
    assert "human-resolved" in enum
