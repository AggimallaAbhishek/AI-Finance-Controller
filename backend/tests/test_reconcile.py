import importlib
from datetime import date
from decimal import Decimal

import reconcile
from reconcile import (
    Settlement, BankEntry, rule_tier, algo_tier, _restricted_edit_distance,
    run_reconciliation, run_and_persist,
)


def settlement(id="STL1", ref="RZP1", amount="1000.00", d=date(2026, 7, 10), status="settled"):
    return Settlement(id, ref, Decimal(amount), d, status)


def bank(id="BTXN1", ref="RZP1", amount="1000.00", d=date(2026, 7, 10), narration="x"):
    return BankEntry(id, ref, Decimal(amount), d, narration)


def test_exact_match_resolves_by_rule():
    s = settlement()
    b = bank()
    matches, exceptions, _, stats = run_reconciliation([s], [b], use_llm=False)

    assert len(matches) == 1
    assert matches[0]["confidence"] == "exact"
    assert matches[0]["settlement_ref"] == "STL1"
    assert matches[0]["bank_ref"] == "BTXN1"
    assert exceptions == []
    assert stats["match_rate"] == 1.0


def test_fuzzy_date_within_tolerance_resolves_by_rule():
    s = settlement(d=date(2026, 7, 10))
    b = bank(d=date(2026, 7, 12))  # 2 days later, within tolerance
    matches, exceptions, _, _ = run_reconciliation([s], [b], use_llm=False)

    assert len(matches) == 1
    assert matches[0]["confidence"] == "fuzzy-date"


def test_fuzzy_amount_within_tolerance_resolves_by_rule():
    s = settlement(amount="1000.00")
    b = bank(amount="995.00")  # Rs 5 off, within Rs 10 tolerance
    matches, exceptions, _, _ = run_reconciliation([s], [b], use_llm=False)

    assert len(matches) == 1
    assert matches[0]["confidence"] == "fuzzy-amount"


def test_beyond_rule_tolerance_falls_to_llm_tier():
    s = settlement(ref="RZP1", d=date(2026, 7, 1))
    b = bank(ref="RZP1", d=date(2026, 7, 10))  # 9 days off, beyond 2-day tolerance

    def fake_llm_match(settlement_dict, candidate_dicts, model=None):
        return {"match_found": True, "matched_bank_txn_id": candidate_dicts[0]["txn_id"], "reasoning": "fake"}

    matches, exceptions, _, _ = run_reconciliation([s], [b], use_llm=True, llm_fn=fake_llm_match, batch_size=1)

    assert len(matches) == 1
    assert matches[0]["confidence"] == "llm-reasoned"
    assert matches[0]["reason"] == "fake"


def test_llm_no_match_becomes_exception():
    s = settlement(ref="RZP1", d=date(2026, 7, 1))
    b = bank(ref="RZP1", d=date(2026, 7, 10))

    def fake_llm_no_match(settlement_dict, candidate_dicts, model=None):
        return {"match_found": False, "matched_bank_txn_id": None, "reasoning": "no evidence"}

    matches, exceptions, _, stats = run_reconciliation([s], [b], use_llm=True, llm_fn=fake_llm_no_match, batch_size=1)

    assert matches == []
    assert len(exceptions) == 2  # settlement-side AND the now-unclaimed bank entry
    assert stats["match_rate"] == 0.0


def test_no_llm_flag_skips_llm_tier_entirely():
    s = settlement(ref="RZP1", d=date(2026, 7, 1))
    b = bank(ref="RZP1", d=date(2026, 7, 10))

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("llm_fn should never be called when use_llm=False")

    matches, exceptions, _, _ = run_reconciliation([s], [b], use_llm=False, llm_fn=should_not_be_called)

    assert matches == []
    assert len(exceptions) == 2


def test_bank_only_entry_becomes_exception():
    s = settlement(ref="RZP1")
    orphan = bank(id="BTXN_ORPHAN", ref="RZP_UNRELATED", amount="500.00", narration="ATM WDL")
    matches, exceptions, _, stats = run_reconciliation([s], [orphan], use_llm=False)

    assert matches == []
    assert len(exceptions) == 2  # settlement has no counterpart, and the orphan bank entry
    bank_exception = next(e for e in exceptions if e["bank_ref"] == "BTXN_ORPHAN")
    assert bank_exception["settlement_ref"] is None


def test_restricted_edit_distance_counts_adjacent_transposition_as_one():
    assert _restricted_edit_distance("RZP1234567890", "RZP1234567890") == 0
    assert _restricted_edit_distance("RZP1234567890", "RZP2134567890") == 1  # swapped first two digits
    assert _restricted_edit_distance("RZP1234567890", "RZP1234567") == 3     # truncated 3 chars
    assert _restricted_edit_distance("abc", "xyz") == 3


def test_algo_tier_reconstructs_truncated_reference_beyond_date_tolerance():
    s = settlement(ref="RZP1234567890", amount="1000.00", d=date(2026, 7, 1))
    b = bank(ref="RZP1234567", amount="1000.00", d=date(2026, 7, 5),  # 4 days off
             narration="UPI-RAZORPAY SETTLEMENT ORDER 567890")  # contains ref[-6:]

    verdict = algo_tier(s, b)
    assert verdict is not None
    confidence, reason = verdict
    assert confidence == "algo-reconstructed"
    assert "567890" in reason


def test_algo_tier_rejects_without_narration_corroboration():
    # Same truncated reference and exact amount, but narration says nothing
    # about the original reference — too weak to trust without that signal.
    s = settlement(ref="RZP1234567890", amount="1000.00", d=date(2026, 7, 1))
    b = bank(ref="RZP1234567", amount="1000.00", d=date(2026, 7, 5), narration="ATM WDL")
    assert algo_tier(s, b) is None


def test_algo_tier_rejects_fuzzy_amount():
    # Amount must match exactly — a corrupted reference plus a fuzzy amount
    # would stack two uncertain signals instead of one.
    s = settlement(ref="RZP1234567890", amount="1000.00", d=date(2026, 7, 1))
    b = bank(ref="RZP1234567", amount="995.00", d=date(2026, 7, 5),
             narration="UPI-RAZORPAY SETTLEMENT ORDER 567890")
    assert algo_tier(s, b) is None


def test_algo_tier_rejects_beyond_date_window():
    s = settlement(ref="RZP1234567890", amount="1000.00", d=date(2026, 7, 1))
    b = bank(ref="RZP1234567", amount="1000.00", d=date(2026, 7, 20),  # 19 days off
             narration="UPI-RAZORPAY SETTLEMENT ORDER 567890")
    assert algo_tier(s, b) is None


def test_run_reconciliation_verifies_algo_match_with_llm_before_accepting():
    # A Tier 3.5 candidate is identified deterministically but still sent to
    # the LLM for a single-candidate confirmation before being accepted —
    # never auto-accepted on edit-distance/narration evidence alone.
    s = settlement(ref="RZP1234567890", amount="1000.00", d=date(2026, 7, 1))
    b = bank(ref="RZP1234567", amount="1000.00", d=date(2026, 7, 5),
             narration="UPI-RAZORPAY SETTLEMENT ORDER 567890")

    calls = []

    def confirming_llm(settlement_dict, candidate_dicts, model=None):
        calls.append(candidate_dicts)
        return {"match_found": True, "matched_bank_txn_id": candidate_dicts[0]["txn_id"], "reasoning": "confirmed"}

    matches, exceptions, _, stats = run_reconciliation(
        [s], [b], use_llm=True, llm_fn=confirming_llm, batch_size=1,
    )

    assert len(calls) == 1  # exactly one verification call, for the single algo candidate
    assert len(calls[0]) == 1
    assert len(matches) == 1
    assert matches[0]["confidence"] == "algo-reconstructed"
    assert "LLM-confirmed" in matches[0]["reason"]
    assert exceptions == []
    assert stats["algo_matched"] == 1
    assert stats["llm_matched"] == 0


def test_algo_candidate_rejected_by_llm_falls_through_to_tier4():
    # A narrower single-candidate verification prompt says no, but the full
    # multi-candidate Tier 4 reasoning (with more context) still finds it —
    # the rejection must fall through, not just give up.
    s = settlement(ref="RZP1234567890", amount="1000.00", d=date(2026, 7, 1))
    b = bank(ref="RZP1234567", amount="1000.00", d=date(2026, 7, 5),
             narration="UPI-RAZORPAY SETTLEMENT ORDER 567890")

    call_sizes = []

    def picky_llm(settlement_dict, candidate_dicts, model=None):
        # First call is Tier 3.5's verification (rejected); second is Tier
        # 4's own call for the same settlement after the fallthrough.
        call_sizes.append(len(candidate_dicts))
        if len(call_sizes) == 1:
            return {"match_found": False, "matched_bank_txn_id": None, "reasoning": "not sure yet"}
        return {"match_found": True, "matched_bank_txn_id": b.txn_id, "reasoning": "confirmed on reconsideration"}

    matches, exceptions, _, stats = run_reconciliation(
        [s], [b], use_llm=True, llm_fn=picky_llm, batch_size=1,
    )

    assert call_sizes == [1, 1]  # verification call, then Tier 4's own single-item call
    assert len(matches) == 1
    assert matches[0]["confidence"] == "llm-reasoned"
    assert matches[0]["bank_ref"] == b.txn_id
    assert exceptions == []
    assert stats["algo_matched"] == 0
    assert stats["llm_matched"] == 1


def test_algo_candidate_skipped_entirely_without_llm():
    # use_llm=False means no LLM is available to verify with — a Tier 3.5
    # candidate must not be auto-accepted just because an LLM isn't around;
    # it falls through to the same "LLM tier skipped" exception path any
    # other ambiguous-middle settlement gets.
    s = settlement(ref="RZP1234567890", amount="1000.00", d=date(2026, 7, 1))
    b = bank(ref="RZP1234567", amount="1000.00", d=date(2026, 7, 5),
             narration="UPI-RAZORPAY SETTLEMENT ORDER 567890")

    matches, exceptions, _, stats = run_reconciliation([s], [b], use_llm=False)

    assert matches == []
    assert len(exceptions) == 2  # the settlement, and the now-unclaimed bank entry
    assert stats["algo_matched"] == 0


def test_matchable_match_rate_excludes_non_settled_settlements():
    # A reversed/pending settlement has no bank-side counterpart by
    # definition — it shouldn't be held against the "of what could
    # plausibly reconcile" rate the way it is against the plain one.
    matched_s = settlement(id="STL1", ref="RZP1")
    matched_b = bank(id="BTXN1", ref="RZP1")
    reversed_s = settlement(id="STL2", ref="RZP2", status="reversed")

    matches, exceptions, _, stats = run_reconciliation(
        [matched_s, reversed_s], [matched_b], use_llm=False,
    )

    assert stats["total_settlements"] == 2
    assert stats["settled_settlements"] == 1
    assert stats["matched"] == 1
    assert stats["match_rate"] == 0.5           # 1/2 — plain, literal rate
    assert stats["matchable_match_rate"] == 1.0  # 1/1 — excludes the reversed settlement


def test_rule_tier_tolerance_is_overridable_per_call():
    s = settlement(ref="RZP1", d=date(2026, 7, 1))
    b = bank(ref="RZP1", d=date(2026, 7, 4))  # 3 days off

    assert rule_tier(s, b) is None  # beyond the default 2-day tolerance
    confidence, _ = rule_tier(s, b, date_tolerance_days=3)
    assert confidence == "fuzzy-date"


def test_tolerance_constants_are_configurable_via_environment(monkeypatch):
    monkeypatch.setenv("RECONCILE_DATE_TOLERANCE_DAYS", "5")
    monkeypatch.setenv("RECONCILE_AMOUNT_TOLERANCE_RS", "25")
    reloaded = importlib.reload(reconcile)
    try:
        assert reloaded.DATE_TOLERANCE_DAYS == 5
        assert reloaded.AMOUNT_TOLERANCE_RS == Decimal("25")
    finally:
        importlib.reload(reconcile)  # restore defaults for subsequent tests


def test_progress_cb_reports_real_stage_and_counts():
    # Phase 11: the trigger-run button needs real progress, not a spinner
    # that looks stuck — progress_cb must fire with actual done/total
    # counts as each tier processes, not just a start/end pair.
    s1 = settlement(id="STL1", ref="RZP1", d=date(2026, 7, 1))
    s2 = settlement(id="STL2", ref="RZP2", d=date(2026, 7, 1))
    b1 = bank(id="BTXN1", ref="RZP1", d=date(2026, 7, 1))
    b2 = bank(id="BTXN2", ref="RZP2", d=date(2026, 7, 20))  # beyond tolerance -> LLM tier

    def fake_llm_match(settlement_dict, candidate_dicts, model=None):
        return {"match_found": True, "matched_bank_txn_id": candidate_dicts[0]["txn_id"], "reasoning": "fake"}

    events = []
    run_reconciliation(
        [s1, s2], [b1, b2], use_llm=True, llm_fn=fake_llm_match, batch_size=1,
        progress_cb=lambda stage, done, total: events.append((stage, done, total)),
    )

    stages = {e[0] for e in events}
    assert "rules" in stages
    assert "llm" in stages
    assert "persisting" in stages
    rule_events = [e for e in events if e[0] == "rules"]
    assert rule_events[-1][1:] == (2, 2)  # done reaches total for the rule tier
    llm_events = [e for e in events if e[0] == "llm"]
    assert llm_events[-1][1:] == (1, 1)  # one settlement fell to the LLM tier


def test_progress_cb_is_optional():
    matches, exceptions, _, _ = run_reconciliation([settlement()], [bank()], use_llm=False)
    assert len(matches) == 1  # no progress_cb passed — must not raise


def test_rule_tier_prefers_closer_amount_over_closer_date():
    # Regression: the engine previously kept whichever candidate was
    # encountered first in list order rather than the objectively closer
    # one. Amount closeness is the intended primary tie-break.
    s = settlement(ref="RZP_DUP", amount="1000.00", d=date(2026, 7, 10))
    far_date_exact_amount = bank(id="BTXN_FAR", ref="RZP_DUP", amount="1000.00", d=date(2026, 7, 12))
    close_date_off_amount = bank(id="BTXN_CLOSE", ref="RZP_DUP", amount="995.00", d=date(2026, 7, 10))

    matches, _, _, _ = run_reconciliation([s], [far_date_exact_amount, close_date_off_amount], use_llm=False)
    assert matches[0]["bank_ref"] == "BTXN_FAR"

    # Order-independence: same result regardless of input list order.
    matches_reversed, _, _, _ = run_reconciliation(
        [s], [close_date_off_amount, far_date_exact_amount], use_llm=False
    )
    assert matches_reversed[0]["bank_ref"] == "BTXN_FAR"


def _write_bank_csv(path):
    path.write_text(
        "txn_id,reference_id,amount,date,narration\n"
        "BTXN1,RZP1,100.00,2026-07-01,payment ref RZP1\n"
    )


def test_run_and_persist_defaults_to_csv_source(tmp_path):
    settlement_path = tmp_path / "settlement.csv"
    settlement_path.write_text(
        "settlement_id,reference_id,amount,date,status\n"
        "STL1,RZP1,100.00,2026-07-01,settled\n"
    )
    bank_path = tmp_path / "bank_statement.csv"
    _write_bank_csv(bank_path)

    result = run_and_persist(settlement_path, bank_path, outdir=tmp_path / "output")
    assert result["stats"]["matched"] == 1
    assert result["matches"][0]["settlement_ref"] == "STL1"


def test_run_and_persist_razorpay_source_never_touches_settlement_csv(tmp_path, monkeypatch):
    # settlement_path is deliberately never passed — the razorpay source
    # must not require it.
    bank_path = tmp_path / "bank_statement.csv"
    _write_bank_csv(bank_path)

    def fake_load_settlements_from_razorpay(key_id, key_secret, from_ts=None, to_ts=None):
        assert key_id == "test-key"
        assert key_secret == "test-secret"
        return [Settlement("setl_1", "RZP1", Decimal("100.00"), date(2026, 7, 1), "processed")]

    import razorpay_client
    monkeypatch.setattr(razorpay_client, "load_settlements_from_razorpay", fake_load_settlements_from_razorpay)

    result = run_and_persist(
        bank_path=bank_path, outdir=tmp_path / "output",
        settlement_source="razorpay", razorpay_key_id="test-key", razorpay_key_secret="test-secret",
    )
    assert result["stats"]["matched"] == 1
    assert result["matches"][0]["settlement_ref"] == "setl_1"
