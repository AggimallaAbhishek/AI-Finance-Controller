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

---

## Template for new entries

```
### Phase N — short title
**Issue:** what broke or went wrong, and the observed symptom.
**Fix:** what changed to resolve it.
```
