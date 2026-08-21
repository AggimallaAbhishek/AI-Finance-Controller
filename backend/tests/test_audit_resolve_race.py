from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal

import audit
from reconcile import BankEntry, Settlement


def test_concurrent_conflicting_resolves_of_the_same_exception_are_serialized(tmp_path):
    """Two near-simultaneous resolve attempts for the same record, with
    mutually exclusive outcomes (one links it to a match, the other
    confirms no-match) — e.g. a double-click, or two browser tabs. Only
    one may win; the other must see the record is no longer an open
    exception and be rejected, not silently also succeed.

    (Two concurrent "no_match" confirmations are NOT a conflict — that
    resolution keeps match_status="exception" by design, so a human can
    re-confirm/update their note later. The race only matters when the
    two outcomes can't both be true.)"""
    db_path = tmp_path / "test.db"
    conn = audit.connect(db_path)
    run_id = "run1"
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(), "s.csv", "b.csv", None, {})
    audit.save_settlements(conn, run_id, [Settlement("STL1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "settled")])
    audit.save_bank_entries(conn, run_id, [BankEntry("BTXN1", "RZPX", Decimal("100.00"), date(2026, 7, 1), "n")])
    audit.save_audit_entries(conn, run_id, [
        {"timestamp": "t", "settlement_ref": "STL1", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "no match", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": None, "bank_ref": "BTXN1",
         "match_status": "exception", "confidence": None, "reason": "orphan", "tier": "rule"},
    ])
    conn.close()

    results = []

    def attempt_match():
        c = audit.connect(db_path)
        try:
            audit.resolve_exception(c, run_id, "STL1", "match", "linked", matched_record_id="BTXN1")
            results.append("match: ok")
        except ValueError as e:
            results.append(f"match: rejected ({e})")
        finally:
            c.close()

    def attempt_no_match():
        c = audit.connect(db_path)
        try:
            audit.resolve_exception(c, run_id, "STL1", "no_match", "confirmed unmatched")
            results.append("no_match: ok")
        except ValueError as e:
            results.append(f"no_match: rejected ({e})")
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda fn: fn(), [attempt_match, attempt_no_match]))

    successes = [r for r in results if r.endswith(": ok")]
    assert len(successes) == 1, f"expected exactly one winner, got: {results}"
    # The loser must have been rejected with a real error, not silently
    # dropped or double-applied.
    assert len(results) == 2 and any("rejected" in r for r in results), results
