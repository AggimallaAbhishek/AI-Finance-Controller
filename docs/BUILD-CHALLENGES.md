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

### Phase 5 review — sourced_from silently dropping cited record IDs
**Issue:** Symbol-reference audit (grep-based, since Serena's CLI turned out
to expose its tools only via a running MCP server, not one-shot flags —
disproportionate setup for a 7-file codebase already fully understood)
turned up an inconsistency: `main.py`'s `/audit/{record_id}` endpoint parsed
`candidates_considered` from its raw JSON-string DB form before use, but
`qa_agent.py`'s `get_trace` tool called `audit.get_trace()` directly and
never did — the two callers had drifted. Reproduced end-to-end: asked the
agent "what candidates were considered before matching STL33357554", got a
**correct** answer (the LLM parsed the double-encoded string on its own),
but `sourced_from` only listed 1 of the 3 record IDs the answer actually
cited — the exact groundedness guarantee Phase 5 exists to provide was
silently broken. A second, deeper layer of the same bug: even after fixing
the JSON parsing, `_extract_record_ids` only recursed into dicts/lists and
had no handling for a list of *bare* ID strings (which is what
`candidates_considered` actually is) — reproduced in isolation before
fixing.
**Fix:** Moved the parsing into `audit.get_trace()` itself so every caller
gets already-parsed data (fixing at the source instead of patching each of
the two call sites separately, since leaving it caller-responsibility is
what caused the drift in the first place); removed the now-redundant (and
would-crash-by-double-parsing) post-processing in `main.py`. Extended
`_extract_record_ids` to also collect bare strings matching known ID
prefixes (`STL`/`BTXN`) when walking a list, not just dict fields. Verified
against both repros, then re-ran the full regression suite (ground-truth
validation + API smoke tests) — no regressions.

### Phase 6 — Q&A agent's markdown answers rendered as raw text
**Issue:** The backend `/qa` agent naturally produces markdown (bold,
tables — confirmed in Phase 5 testing). The chat panel initially rendered
`res.answer` as plain text, so `**90%**` showed literal asterisks and
"unmatched bank entries" answers (which come back as full markdown tables)
rendered as unreadable pipe-delimited text.
**Fix:** Added `react-markdown` + `remark-gfm` (table support) to render
assistant messages properly, with a custom `table` renderer that wraps
tables in a horizontally-scrollable container — the chat sidebar is only
~330px wide and Q&A tables can have 5 columns.

### Phase 6 — focus ring clipped by the exception list's `overflow: hidden`
**Issue:** `.exception-list__items` used `overflow: hidden` to clip its
children's corners to the container's `border-radius`. This also clipped
the `outline` (with `outline-offset: 2px`) of any focused row's button,
leaving keyboard-focused rows with no visible focus indicator — a real
accessibility regression, confirmed visually via a zoomed screenshot.
**Fix:** Removed the `overflow: hidden` and instead rounded the first/last
row's own corners directly (via longhand `border-*-radius` properties so
both rules combine correctly when there's only one row). Confirmed the
focus ring now renders as a full, unclipped, correctly-rounded outline.

### Phase 6 — mobile chat toggle button overlapped the chat input
**Issue:** The mobile slide-over chat panel used `top: auto` on its fixed
positioning, which (combined with the inner panel's `height: 100%`)
produced an ambiguous, content-sized box rather than a full-viewport
overlay. The fixed-position toggle button (higher z-index) then visually
overlapped the chat form's input and Send button at the bottom of the
screen — confirmed via screenshot on a narrow viewport.
**Fix:** Changed the overlay to fill the full viewport (`inset: 0`, no
`top: auto`) with `padding-bottom` reserving space for the toggle button,
so the input row always sits above it instead of underneath.

---

## Template for new entries

```
### Phase N — short title
**Issue:** what broke or went wrong, and the observed symptom.
**Fix:** what changed to resolve it.
```
