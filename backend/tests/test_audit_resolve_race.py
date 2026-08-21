from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal

import audit
from reconcile import BankEntry, Settlement


def test_concurrent_match_resolves_of_the_same_settlement_are_serialized(tmp_path):
    """Two near-simultaneous "match" attempts for the same settlement, to
    two different bank counterparts — e.g. a double-click, or two browser
    tabs each picking a different candidate. These ARE mutually exclusive
    (a settlement can't be matched twice), so exactly one must win and the
    other must see it's no longer an open exception and be rejected.

    (A concurrent "match" + "no_match" pair is deliberately NOT tested as
    a conflict here — "no_match" keeps match_status="exception" by design,
    so a human can legitimately revisit and link a match later, even
    moments later. That's a valid sequential workflow racing, not a bug —
    confirmed by instrumented timing during this test's development: the
    first version of this test asserted exactly that combination could
    never both succeed, and it was the test's premise that was wrong, not
    the locking.)"""
    db_path = tmp_path / "test.db"
    conn = audit.connect(db_path)
    run_id = "run1"
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(), "s.csv", "b.csv", None, {})
    audit.save_settlements(conn, run_id, [Settlement("STL1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "settled")])
    audit.save_bank_entries(conn, run_id, [
        BankEntry("BTXN1", "RZPX", Decimal("100.00"), date(2026, 7, 1), "n"),
        BankEntry("BTXN2", "RZPY", Decimal("100.00"), date(2026, 7, 1), "n"),
    ])
    audit.save_audit_entries(conn, run_id, [
        {"timestamp": "t", "settlement_ref": "STL1", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "no match", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": None, "bank_ref": "BTXN1",
         "match_status": "exception", "confidence": None, "reason": "orphan", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": None, "bank_ref": "BTXN2",
         "match_status": "exception", "confidence": None, "reason": "orphan", "tier": "rule"},
    ])
    conn.close()

    results = []

    def attempt(counterpart):
        c = audit.connect(db_path)
        try:
            audit.resolve_exception(c, run_id, "STL1", "match", f"linked to {counterpart}", matched_record_id=counterpart)
            results.append(f"{counterpart}: ok")
        except ValueError as e:
            results.append(f"{counterpart}: rejected ({e})")
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, ["BTXN1", "BTXN2"]))

    successes = [r for r in results if r.endswith(": ok")]
    assert len(successes) == 1, f"expected exactly one winner, got: {results}"
    assert any("rejected" in r for r in results), results
