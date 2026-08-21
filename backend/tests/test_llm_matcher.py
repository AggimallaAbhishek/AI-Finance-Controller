from llm_matcher import _parse_verdict

CANDIDATES = [{"txn_id": "BTXN123", "reference_id": "RZP1", "amount": "100.00",
               "date": "2026-07-01", "narration": "x"}]


def test_parses_clean_match_verdict():
    raw = '{"match_found": true, "matched_bank_txn_id": "BTXN123", "reasoning": "clean"}'
    verdict = _parse_verdict(raw, CANDIDATES)
    assert verdict == {"match_found": True, "matched_bank_txn_id": "BTXN123", "reasoning": "clean"}


def test_parses_no_match_verdict():
    raw = '{"match_found": false, "matched_bank_txn_id": null, "reasoning": "no evidence"}'
    verdict = _parse_verdict(raw, CANDIDATES)
    assert verdict == {"match_found": False, "matched_bank_txn_id": None, "reasoning": "no evidence"}


def test_ignores_trailing_commentary_after_json():
    # Regression: a greedy regex would capture from the first { to the
    # LAST } in the whole response, breaking on trailing text like this.
    raw = ('{"match_found": true, "matched_bank_txn_id": "BTXN123", "reasoning": "ok"}\n'
           'Let me know if you need {more detail}.')
    verdict = _parse_verdict(raw, CANDIDATES)
    assert verdict["match_found"] is True
    assert verdict["matched_bank_txn_id"] == "BTXN123"


def test_stringly_typed_match_found_is_treated_as_false():
    # Regression: Python truthiness on a non-empty string "false" is True.
    raw = '{"match_found": "false", "matched_bank_txn_id": "BTXN123", "reasoning": "not a match"}'
    verdict = _parse_verdict(raw, CANDIDATES)
    assert verdict["match_found"] is False
    assert verdict["matched_bank_txn_id"] is None


def test_matched_txn_id_not_in_candidates_is_discarded():
    raw = '{"match_found": true, "matched_bank_txn_id": "BTXN999", "reasoning": "hallucinated"}'
    verdict = _parse_verdict(raw, CANDIDATES)
    assert verdict["match_found"] is False
    assert verdict["matched_bank_txn_id"] is None


def test_malformed_json_falls_back_safely():
    raw = '{"match_found": true, "matched_bank_txn_id": "BTXN123"'  # truncated, no closing brace
    verdict = _parse_verdict(raw, CANDIDATES)
    assert verdict["match_found"] is False
    assert verdict["matched_bank_txn_id"] is None


def test_no_json_object_falls_back_safely():
    raw = "I cannot determine a match for this record."
    verdict = _parse_verdict(raw, CANDIDATES)
    assert verdict["match_found"] is False
    assert verdict["matched_bank_txn_id"] is None
