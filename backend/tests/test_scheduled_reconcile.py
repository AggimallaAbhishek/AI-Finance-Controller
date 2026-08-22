import json

from scheduled_reconcile import build_digest, main


def stats(match_rate, settlement_exceptions=0, bank_exceptions=0):
    return {"match_rate": match_rate, "settlement_exceptions": settlement_exceptions,
            "bank_exceptions": bank_exceptions}


def test_digest_has_no_delta_when_there_is_no_previous_run():
    digest = build_digest("run2", stats(0.9), None, None)
    assert digest["match_rate_delta"] is None
    assert digest["previous_run_id"] is None
    assert digest["match_rate"] == 0.9


def test_digest_computes_positive_delta_when_match_rate_improves():
    digest = build_digest("run2", stats(0.9), "run1", stats(0.8))
    assert digest["match_rate_delta"] == 0.1


def test_digest_computes_negative_delta_when_match_rate_drops():
    digest = build_digest("run2", stats(0.7), "run1", stats(0.9))
    assert digest["match_rate_delta"] == -0.2


def test_digest_exception_count_sums_both_sides():
    digest = build_digest("run1", stats(0.5, settlement_exceptions=3, bank_exceptions=2), None, None)
    assert digest["exception_count"] == 5


def test_digest_carries_run_ids_through():
    digest = build_digest("run2", stats(1.0), "run1", stats(1.0))
    assert digest["run_id"] == "run2"
    assert digest["previous_run_id"] == "run1"


def test_main_second_run_reports_delta_against_the_first(tmp_path, monkeypatch, capsys):
    # Regression guard: previous_run_id/previous_stats must be captured
    # BEFORE the new run persists, not after — otherwise a run would
    # always be compared against itself and delta would always be 0.
    settlement_path = tmp_path / "settlement.csv"
    settlement_path.write_text(
        "settlement_id,reference_id,amount,date,status\n"
        "STL1,RZP1,100.00,2026-07-01,settled\n"
        "STL2,RZP2,200.00,2026-07-01,settled\n"
    )
    bank_path = tmp_path / "bank_statement.csv"
    bank_path.write_text(
        "txn_id,reference_id,amount,date,narration\n"
        "BTXN1,RZP1,100.00,2026-07-01,n\n"
    )
    outdir = tmp_path / "output"
    db_path = outdir / "audit.db"

    argv = ["scheduled_reconcile.py", "--settlement", str(settlement_path), "--bank", str(bank_path),
            "--outdir", str(outdir), "--db", str(db_path), "--no-llm"]

    monkeypatch.setattr("sys.argv", argv)
    main()
    first_digest = json.loads(capsys.readouterr().out)
    assert first_digest["previous_run_id"] is None
    assert first_digest["match_rate_delta"] is None

    monkeypatch.setattr("sys.argv", argv)
    main()
    second_digest = json.loads(capsys.readouterr().out)
    assert second_digest["previous_run_id"] == first_digest["run_id"]
    assert second_digest["match_rate_delta"] == 0.0  # identical data, identical rate
