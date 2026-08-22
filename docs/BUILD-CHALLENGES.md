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

### Phase 6 review — sticky chat panel's height guess didn't match reality
**Issue:** Systematic re-scan of the frontend, using `get_page_text`
(DOM-based) instead of screenshots after this remote browser environment's
viewport turned out to drift unpredictably between calls (confirmed via
`window.innerWidth`/`innerHeight` — the same unchanged coordinates and
resize requests produced different effective sizes across calls, a tooling
instability, not an app issue — one apparent "row won't expand" failure
was a false alarm caused by this, disproven by re-testing with `find` +
`get_page_text` which are coordinate-independent).

The one real finding: `.chat-panel`'s desktop height used
`calc(100svh - 24px - 24px - 90px)`, guessing the stats header's height at
90px so the sticky sidebar wouldn't overflow the viewport in its natural
(pre-scroll) position. Measured via `getBoundingClientRect()`: the actual
header height was 104.9px — a 15px underestimate. It hadn't visibly broken
in testing (there was enough slack at the viewport sizes tested), but it
was a real, evidence-based inaccuracy, not a hypothetical one.
**Fix:** Updated the subtracted constant to the measured value (112px,
with a small safety margin) rather than tweaking it blindly. Verified via
`getBoundingClientRect()` at two different actual viewport sizes
(657px and 813px tall) that the panel's bottom edge stays within the
viewport with real margin to spare in both.

### v2.0 Phase 9 — test fixture closed its own DB connection before use
**Issue:** Writing the FastAPI `TestClient` tests, a seeding fixture drove
the `get_conn` dependency generator manually to grab a connection for
seed data: `next(main.app.dependency_overrides[main.get_conn]())`. Every
`save_run` call in the fixture failed with
`sqlite3.ProgrammingError: Cannot operate on a closed database` —
immediately, on the very first write. Root cause: the generator object
returned by calling the override function had no variable holding a
reference to it — only the yielded `conn` value was kept. With nothing
referencing the generator itself, Python garbage-collected it right after
`next()` returned, and GC-ing a suspended generator calls `.close()` on
it, which fires its `finally: conn.close()` block — closing the
connection before the fixture ever got to use it.
**Fix:** Stopped driving the dependency generator manually for test
seeding entirely — the fixture now opens its own connection directly via
`audit.connect(db_path)` pointed at the same file the override serves
requests from, sidestepping the generator-lifetime issue altogether rather
than working around it (e.g. by holding a reference and remembering to
call `.close()` in the right order).

### v2.0 Phase 10 — SQLite connections broke under concurrent requests
**Issue:** Live-testing the new Resolve UI, the dashboard intermittently
failed to refresh after a successful resolution — "Failed to fetch" in
the browser. Isolated it by testing concurrent `curl` requests directly
against `/matches` and `/exceptions` (bypassing the browser entirely):
reproducible 500s starting from the second concurrent round. The backend
log showed the real cause: `sqlite3.ProgrammingError: SQLite objects
created in a thread can only be used in that same thread.` FastAPI runs
sync route handlers and generator dependencies via a thread pool, and
doesn't guarantee `get_conn()`'s `yield` and the route handler's body run
on the same OS thread — under concurrent load, `audit.connect()`'s
connection could be created on one worker thread and used on another,
which plain `sqlite3` rejects by default. This bug has existed since
`Depends(get_conn)` was introduced in Phase 4; it never surfaced because
every prior test and manual check was sequential — Phase 10 is the first
thing in this project to fire concurrent requests (the dashboard's
`refresh()` fetches `/matches` and `/exceptions` together via
`Promise.all`).
**Fix:** `sqlite3.connect(db_path, check_same_thread=False)`. Safe here
specifically because each connection is only ever used within one
request's own create-use-close lifecycle, never shared between two
concurrent requests. Reproduced first with a targeted pytest test
(create a connection on the main thread, use it from a
`ThreadPoolExecutor` thread, assert it doesn't raise) before fixing, then
re-ran the exact concurrent-curl repro against the live server to confirm
— 5 rounds clean, versus failing from round 2 onward before the fix.

Separately, while investigating: the resolve form called
`onResolved()` (the dashboard refresh) without awaiting it, so if the
refresh itself ever failed independently of a successful resolve, the
error became an unhandled promise rejection the form never saw — stuck
permanently on "Resolving…" with no way to recover short of a manual
reload. Fixed by awaiting it inside the same try/catch, so a refresh
failure surfaces in the form exactly like a resolve failure would.

### v2.0 Phases 9 & 10 review — systematic bug scan
**Issue:** Fresh re-scan of all Phase 9/10 code. Found and fixed 4 real
issues, all reproduced before fixing:

1. **Race condition in `resolve_exception`**: it read "is this currently
   an exception" then wrote, with no transaction wrapping the two. This
   turned into a two-layer debugging story, worth recording honestly:
   - *First repro attempt was itself flawed*: it fired two concurrent
     "no_match" resolutions at the same record and asserted only one
     could succeed. Both succeeded every time — but that's *correct*,
     not a bug: "no_match" deliberately keeps `match_status="exception"`
     (so a human can revisit and confirm again later), so two of them
     racing isn't a real conflict.
   - *Redesigned around a genuine conflict* (two concurrent "match"
     attempts linking the same settlement to two different bank
     counterparts — truly mutually exclusive) and added a `BEGIN
     IMMEDIATE` transaction. It passed 8/8 on the first check — which
     turned out to be false confidence. A later full-suite run failed
     once; re-running the race test 20x in isolation showed a genuine
     ~25% failure rate. Instrumented timing across failures showed both
     "attempts" completing in well under a millisecond with overlapping
     lifetimes — the manual `conn.execute("BEGIN IMMEDIATE")` wasn't
     reliably serializing against Python's own implicit legacy
     transaction handling (the sqlite3 module's default
     `isolation_level=""` auto-manages transactions around DML in ways
     that can conflict with manually issuing `BEGIN` as raw SQL). A
     smaller isolated test (one thread holds the lock for a full second)
     showed the second connection correctly blocking — proving the
     locking mechanism itself works; the flakiness was specifically in
     the fast-path interaction with Python's implicit transaction state.
2. **`resolve_exception` accepted an empty or whitespace-only note** —
   only the frontend's `disabled` guard prevented it, not the seam that
   actually matters. A direct API call could create an unexplained
   "human" decision, undermining the entire point of an audited
   resolution.
3. **The Q&A agent and the dashboard could report contradictory numbers
   for the same run** — the most serious finding. `qa_agent.py`'s
   `get_stats()` returned the run's stored `stats_json`, frozen at
   reconcile time and never updated by a later resolution, while the
   dashboard (Phase 10) computes stats live. Confirmed live: after
   resolving 2 exceptions into 1 match, the dashboard correctly showed 10
   exceptions while the Q&A agent answered "12" for the identical
   question — a direct violation of the project's core honesty
   principle. Compounding this, `list_matches`'s tool schema had a
   hardcoded `confidence` enum from Phase 5 that didn't include the new
   `"human-resolved"` value, so asking specifically about human
   resolutions made the agent answer "the available data does not
   indicate" — even though the data existed, just not through the tool
   it reached for.
**Fix:**
1. Wrapped the check-then-write in a `BEGIN IMMEDIATE` transaction (so
   SQLite serializes genuinely conflicting concurrent resolves) *and* set
   `isolation_level=None` on the connection, handing SQLite's manual
   transaction control fully to explicit `BEGIN`/`COMMIT`/`ROLLBACK`
   rather than leaving Python's own implicit transaction bookkeeping in
   the mix. Verification standard raised to match the failure rate this
   found: 80 consecutive clean runs of the corrected race test (30, then
   50 more) plus 5 consecutive full-suite runs, instead of trusting one
   green run.
2. Added a non-empty check at the top of `resolve_exception`, raising
   `ValueError` — defense in depth, not relying on the frontend alone.
3. `get_stats()` now computes matched/exceptions/rule/llm/human counts
   live from `list_matches()`/`list_exceptions()` (which already
   correctly reflect resolutions), keeping only the static
   `total_settlements`/`total_bank_entries` from the stored snapshot.
   Added `"human-resolved"` to the `list_matches` tool schema's enum.
   Re-ran the exact live repro that caught this after the fix: both
   questions now answer correctly and consistently with the dashboard.

All fixes covered by new tests (`test_audit_resolve_race.py`,
`test_qa_agent.py`, plus additions to `test_audit_resolve.py`) —
55 tests total, full suite green, live end-to-end re-verification clean.

## Phase 11 — a phantom double reconciliation run during live testing

**Issue:** while live-testing the new "Run reconciliation" button
end-to-end, one intentional click produced a run as expected — but a
few minutes later, after several unrelated actions (switching runs via
the picker, clicking the Exceptions tab, changing filters), a *second*
reconciliation run appeared in `GET /runs` that was never explicitly
requested. Only one deliberate button click had been made. Before
assuming this was a double-submit bug in `ReconcileRunner` (a classic
class of bug: a button that isn't disabled fast enough, or an effect
that re-fires), it was reproduced in isolation rather than patched on
suspicion.

**Investigation:** counted `POST /reconcile/async` calls in the backend
log directly rather than trusting UI state — exactly 2 for 1 intended
click, ruling out "it never actually double-posted, the UI just looked
odd." Checked for a second dev server process (`ps aux`) — none;
checked for a `useEffect` or other non-click path to `start()` in
`ReconcileRunner.jsx` — none exists, `start()` is only reachable from
the button's `onClick`. Reloaded the page fresh and fired a single
programmatic `.click()` via `javascript_tool` (bypassing coordinate-
based clicking entirely) with the backend log's POST count checked
immediately before and after: exactly one POST, exactly one new run.
Repeated once more with the same result.

**Root cause:** not a code defect. The anomalous second trigger
happened in a window where the run picker had just been switched via a
direct DOM `dispatchEvent`, re-rendering the tab panel; a subsequent
click aimed at the "Exceptions" tab, using an element reference
obtained from an earlier `find` call, landed on the "Run reconciliation"
button instead — a known instability of this environment's browser-
automation tooling with stale element references across a React
re-render, not application behavior. The isolated single-click test
conclusively rules out a real double-submit bug: `ReconcileRunner` has
no code path that can fire two jobs from one click.

**Fix:** none needed in application code. Documented here specifically
*because* the instinct after seeing "1 click → 2 runs" is to add
defensive code (disable-on-mousedown, a submission-lock ref, etc.)
against a bug that doesn't exist — which would have been effort spent
solving the wrong problem. The two extra runs this produced in
`data/output/audit.db` were left in place (real, valid 90%-match-rate
runs, not corrupted data) — they exercise the run-history/trend-chart
feature usefully rather than needing cleanup.

---

## Template for new entries

```
### Phase N — short title
**Issue:** what broke or went wrong, and the observed symptom.
**Fix:** what changed to resolve it.
```
