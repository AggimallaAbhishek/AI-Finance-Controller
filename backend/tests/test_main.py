from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import audit
import main
from reconcile import Settlement, BankEntry


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test_audit.db"

    def override_get_conn():
        conn = audit.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    main.app.dependency_overrides[main.get_conn] = override_get_conn
    yield TestClient(main.app), db_path
    main.app.dependency_overrides.clear()


@pytest.fixture
def seeded_run(client):
    """Seed one run with a match and an exception, directly via audit.py
    (not through /reconcile, which would need a real or mocked LLM call).
    Writes straight to the same db_path the override points requests at,
    rather than manually driving the dependency generator (which gets
    garbage-collected — and its `finally: conn.close()` fires — the moment
    nothing holds a reference to it)."""
    _, db_path = client
    conn = audit.connect(db_path)
    run_id = "run1"
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(),
                    "s.csv", "b.csv", None, {"match_rate": 0.5, "matched": 1})
    s1 = Settlement("STL1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "settled")
    s2 = Settlement("STL2", "RZP2", Decimal("200.00"), date(2026, 7, 1), "settled")
    b1 = BankEntry("BTXN1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "n")
    audit.save_settlements(conn, run_id, [s1, s2])
    audit.save_bank_entries(conn, run_id, [b1])
    audit.save_audit_entries(conn, run_id, [
        {"timestamp": "t", "settlement_ref": "STL1", "bank_ref": "BTXN1",
         "match_status": "matched", "confidence": "exact", "reason": "r", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": "STL2", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "no match", "tier": "rule"},
    ])
    conn.close()
    return run_id


def test_health(client):
    test_client, _ = client
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_matches_and_exceptions_reflect_seeded_data(client, seeded_run):
    test_client, _ = client
    resp = test_client.get("/matches")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    resp = test_client.get("/exceptions")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_audit_trace_returns_source_records(client, seeded_run):
    test_client, _ = client
    resp = test_client.get("/audit/STL1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["settlement_record"]["reference_id"] == "RZP1"
    assert body["counterpart_bank_record"]["txn_id"] == "BTXN1"


def test_audit_trace_404s_for_unknown_record(client, seeded_run):
    test_client, _ = client
    resp = test_client.get("/audit/DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_invalid_run_id_404s_instead_of_silent_empty_result(client, seeded_run):
    # Regression: this used to return HTTP 200 with an empty list,
    # indistinguishable from a real run with zero matches.
    test_client, _ = client
    resp = test_client.get("/matches?run_id=totally-bogus")
    assert resp.status_code == 404


def test_matches_without_any_run_404s(client):
    test_client, _ = client
    resp = test_client.get("/matches")
    assert resp.status_code == 404


@pytest.fixture
def two_open_exceptions(client):
    """A settlement-side and a bank-side exception, unrelated to each
    other — enough to exercise a resolve-to-match across both sides."""
    _, db_path = client
    conn = audit.connect(db_path)
    run_id = "run1"
    audit.save_run(conn, run_id, datetime.now(timezone.utc).isoformat(),
                    "s.csv", "b.csv", None, {})
    audit.save_settlements(conn, run_id, [Settlement("STL1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "settled")])
    audit.save_bank_entries(conn, run_id, [BankEntry("BTXN1", "RZPX", Decimal("100.00"), date(2026, 7, 1), "n")])
    audit.save_audit_entries(conn, run_id, [
        {"timestamp": "t", "settlement_ref": "STL1", "bank_ref": None,
         "match_status": "exception", "confidence": None, "reason": "no match", "tier": "rule"},
        {"timestamp": "t", "settlement_ref": None, "bank_ref": "BTXN1",
         "match_status": "exception", "confidence": None, "reason": "orphan", "tier": "rule"},
    ])
    conn.close()
    return run_id


def test_resolve_to_match_via_api(client, two_open_exceptions):
    test_client, _ = client
    resp = test_client.post("/exceptions/STL1/resolve",
                             json={"resolution": "match", "note": "verified manually", "matched_record_id": "BTXN1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["match_status"] == "matched"
    assert body["tier"] == "human"
    assert body["confidence"] == "human-resolved"

    resp = test_client.get("/exceptions")
    assert resp.json()["count"] == 0  # both sides resolved out of the exception list

    resp = test_client.get("/matches")
    assert resp.json()["count"] == 1


def test_resolve_no_match_via_api(client, two_open_exceptions):
    test_client, _ = client
    resp = test_client.post("/exceptions/STL1/resolve",
                             json={"resolution": "no_match", "note": "confirmed genuinely unmatched"})
    assert resp.status_code == 200
    assert resp.json()["tier"] == "human"

    resp = test_client.get("/exceptions")
    body = resp.json()
    assert body["count"] == 2  # still 2 open exceptions — STL1 stayed one, just re-reasoned
    stl1 = next(e for e in body["exceptions"] if e["settlement_ref"] == "STL1")
    assert stl1["reason"] == "confirmed genuinely unmatched"


def test_resolve_invalid_resolution_returns_400(client, two_open_exceptions):
    test_client, _ = client
    resp = test_client.post("/exceptions/STL1/resolve", json={"resolution": "bogus", "note": "x"})
    assert resp.status_code == 400


def test_resolve_unknown_record_returns_400(client, two_open_exceptions):
    test_client, _ = client
    resp = test_client.post("/exceptions/NOPE/resolve", json={"resolution": "no_match", "note": "x"})
    assert resp.status_code == 400


def test_qa_with_no_run_gives_honest_answer_not_a_crash(client):
    test_client, _ = client
    resp = test_client.post("/qa", json={"question": "what is the match rate?"})
    assert resp.status_code == 200
    assert "run" in resp.json()["answer"].lower()
