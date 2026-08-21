import llm_matcher

SETTLEMENT = {"settlement_id": "STL1", "reference_id": "RZP1", "amount": "100.00",
               "date": "2026-07-01", "status": "settled"}
CANDIDATES = [{"txn_id": "BTXN123", "reference_id": "RZP1", "amount": "100.00",
               "date": "2026-07-01", "narration": "x"}]


def test_retries_after_transient_failure_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky_chat(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("transient network blip")
        return {"message": {"content": '{"match_found": true, "matched_bank_txn_id": "BTXN123", "reasoning": "ok"}'}}

    monkeypatch.setattr(llm_matcher.ollama, "chat", flaky_chat)
    sleeps = []
    verdict = llm_matcher.get_llm_verdict(SETTLEMENT, CANDIDATES, sleep_fn=sleeps.append)

    assert verdict["match_found"] is True
    assert calls["n"] == 2
    assert len(sleeps) == 1  # slept once, between the failed and successful attempt


def test_gives_up_after_persistent_failure(monkeypatch):
    def always_fails(**kwargs):
        raise ConnectionError("backend unreachable")

    monkeypatch.setattr(llm_matcher.ollama, "chat", always_fails)
    sleeps = []
    verdict = llm_matcher.get_llm_verdict(SETTLEMENT, CANDIDATES, sleep_fn=sleeps.append)

    assert verdict["match_found"] is False
    assert verdict["matched_bank_txn_id"] is None
    assert "backend unreachable" in verdict["reasoning"]
    assert len(sleeps) == llm_matcher.MAX_ATTEMPTS - 1  # backoff between each attempt, none after the last


def test_retry_and_failure_are_logged_for_operational_visibility(monkeypatch, caplog):
    def always_fails(**kwargs):
        raise ConnectionError("backend unreachable")

    monkeypatch.setattr(llm_matcher.ollama, "chat", always_fails)
    with caplog.at_level("WARNING", logger="llm_matcher"):
        llm_matcher.get_llm_verdict(SETTLEMENT, CANDIDATES, sleep_fn=lambda s: None)

    messages = [r.message for r in caplog.records]
    assert any("attempt" in m.lower() for m in messages)
    assert any("gave up" in m.lower() or "failed after" in m.lower() for m in messages)


def test_no_retry_overhead_when_first_call_succeeds(monkeypatch):
    calls = {"n": 0}

    def working_chat(**kwargs):
        calls["n"] += 1
        return {"message": {"content": '{"match_found": true, "matched_bank_txn_id": "BTXN123", "reasoning": "ok"}'}}

    monkeypatch.setattr(llm_matcher.ollama, "chat", working_chat)
    sleeps = []
    verdict = llm_matcher.get_llm_verdict(SETTLEMENT, CANDIDATES, sleep_fn=sleeps.append)

    assert verdict["match_found"] is True
    assert calls["n"] == 1
    assert sleeps == []
