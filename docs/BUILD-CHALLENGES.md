# Build Challenges & Technical Obstacles

What issues came up while building, and how they were solved. Updated as
they happen, in order — most recent entry at the bottom.

---

### Phase 0 — `timeout` not available on macOS
**Issue:** Tried to bound an `ollama run` smoke-test call with the `timeout`
command; macOS's default shell doesn't ship it (`command not found`).
**Fix:** Dropped the shell-level `timeout` and used the tool runner's own
timeout parameter instead to bound the call.

### Phase 0 — curl raced the backend startup
**Issue:** Started `uvicorn` in the background and curled `/health`
immediately after; curl returned exit code 7 (connection refused) because
the server hadn't finished binding to the port yet.
**Fix:** Added a short sleep before the health check, then confirmed via
the log output that the server had actually started before retrying.

### Phase 2 — Ollama's `format` (structured-output) schema isn't enforced for cloud models
**Issue:** Passed a JSON schema via `format=` to `ollama.chat(model="gpt-oss:20b-cloud", ...)`
expecting constrained JSON output (this works for local models via grammar-based
decoding). The cloud-routed model ignored it entirely and returned a free-text
markdown table instead.
**Fix:** Dropped `format=`. Instead, the prompt explicitly instructs "respond
with ONLY a single JSON object, no markdown, no commentary" and the client
extracts the first `{...}` block via regex before `json.loads`. If parsing
still fails (or the returned `matched_bank_txn_id` isn't one of the actual
candidates), the verdict is treated as invalid and the record is escalated to
an exception rather than guessed at — never trust an unparseable or
out-of-range LLM response into a "match".

### Phases 0-4 review — systematic bug scan
**Issue:** Ran a full read-through of every Phase 0-4 file using the
systematic-debugging process (reproduce before fixing, one fix at a time,
verify after each). Found and confirmed 4 real bugs, all reproduced in
isolation before any fix was applied:
1. `llm_matcher.py`'s JSON extraction used a greedy regex
   (`re.search(r"\{.*\}", raw, re.DOTALL)`) that captures from the first `{`
   to the *last* `}` in the whole response — any trailing text containing a
   brace after the real JSON object broke parsing and wrongly discarded a
   valid LLM verdict as unparseable.
2. In the same function, `if verdict.get("match_found") and ...` used
   Python truthiness on a JSON field — `"match_found": "false"` (a string,
   not a bool) is truthy in Python, so a stringly-typed "no" could have been
   read as a "yes".
3. `main.py`'s `/matches`, `/exceptions`, `/audit` endpoints silently
   returned HTTP 200 with an empty list for a nonexistent `?run_id=`,
   indistinguishable from a real run with zero matches.
4. `reconcile.py`'s rule tier picked whichever unclaimed bank row it
   encountered *first* in file order when a settlement had multiple
   candidates at different fuzzy tiers, instead of the objectively closest
   one — dormant only because the synthetic data generator guarantees
   unique reference_ids, not because the logic was right.

**Fix:**
1. Replaced the regex with `json.JSONDecoder().raw_decode()` anchored at
   the first `{`, which parses exactly one JSON value and ignores anything
   after it.
2. Changed the check to `verdict.get("match_found") is True` — only a
   literal JSON boolean `true` counts as a match.
3. `resolve_run_id()` now validates the run_id exists via `audit.get_run()`
   before using it, 404ing on an unknown id instead of silently returning
   empty.
4. Rule-tier candidate selection now ranks all valid candidates by
   `(amount_diff, date_diff)` and keeps the closest, instead of
   first-found-unless-exact. Amount was chosen as the primary tie-break key
   since two unrelated transactions rarely share both a reference_id and an
   exact amount by coincidence, while date drift is routine.

All four fixes verified against isolated repro cases, then the full batch
was re-run end-to-end and re-validated against `ground_truth.csv`
(66/66 correct, unchanged) plus a full API endpoint smoke test — no
regressions.

---

## Template for new entries

```
### Phase N — short title
**Issue:** what broke or went wrong, and the observed symptom.
**Fix:** what changed to resolve it.
```
