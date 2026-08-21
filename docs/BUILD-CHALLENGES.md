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

---

## Template for new entries

```
### Phase N — short title
**Issue:** what broke or went wrong, and the observed symptom.
**Fix:** what changed to resolve it.
```
