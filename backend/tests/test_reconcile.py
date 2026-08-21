import importlib
from datetime import date
from decimal import Decimal

import reconcile
from reconcile import Settlement, BankEntry, rule_tier, run_reconciliation


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

    matches, exceptions, _, _ = run_reconciliation([s], [b], use_llm=True, llm_fn=fake_llm_match)

    assert len(matches) == 1
    assert matches[0]["confidence"] == "llm-reasoned"
    assert matches[0]["reason"] == "fake"


def test_llm_no_match_becomes_exception():
    s = settlement(ref="RZP1", d=date(2026, 7, 1))
    b = bank(ref="RZP1", d=date(2026, 7, 10))

    def fake_llm_no_match(settlement_dict, candidate_dicts, model=None):
        return {"match_found": False, "matched_bank_txn_id": None, "reasoning": "no evidence"}

    matches, exceptions, _, stats = run_reconciliation([s], [b], use_llm=True, llm_fn=fake_llm_no_match)

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
