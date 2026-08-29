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

### Phase 11 — Matches-tab tier filter silently emptied the Exceptions tab

**Issue:** running a systematic-debugging pass over the Phase 11 dashboard
files (no failing test or crash — just a read-through of `FilterBar.jsx`
and `App.jsx` looking for logic bugs) surfaced a real, reproducible one:
`filters.tiers` is shared React state between the Matches and Exceptions
tabs. `FilterBar` only *hides* the tier chips when `showTier` is false on
the Exceptions tab — it never stopped `applyFilters` from still applying
`filters.tiers` to exception rows. Exceptions always carry
`confidence: null` (`reconcile.py` never sets a confidence on an
exception), so picking any tier chip while on Matches, then switching to
Exceptions, made `filters.tiers.includes(null)` false for every row —
the Exceptions tab silently rendered "No exceptions match these filters"
even with real, unresolved exceptions present. Confirmed in isolation
with a standalone reproduction of `applyFilters` (0 of 2 exceptions
survived with a leftover tier filter) before touching any code.

The `side` filter avoided this exact trap already: `filteredMatches` is
computed by calling `applyFilters(matches, filters)` *without* a `side`
accessor, so the side filter is structurally inert for Matches. The tier
filter had no equivalent guard for Exceptions — that asymmetry was the
root cause, not a one-off typo.

**Fix:** added an `ignoreTiers` option to `applyFilters` (mirroring the
existing optional `side` accessor pattern) and passed
`ignoreTiers: true` when computing `filteredExceptions` in `App.jsx`, so
a Matches-tab tier selection can never suppress Exceptions-tab rows.
Verified via the same standalone reproduction (now 2 of 2 exceptions
survive) plus the full `pytest` suite (62 passed) and a clean
`vite build`.

---

### Phase 12 — two same-labeled buttons fooled test automation, not just a human

**Issue:** live-testing the new "Upload & Run" tab, a blind
`document.querySelectorAll('button').find(b => b.textContent.includes('Run reconciliation'))`
(used to bypass an earlier coordinate-click miss) silently clicked the
*toolbar's* `ReconcileRunner` button instead of the intended
`UploadRunner` button in the tab content — both were labeled exactly
"Run reconciliation", and `.find()` returns the first DOM match, which
was the toolbar's. This fired a real reconciliation against the
server's default CSVs while genuinely uploaded test files sat unused,
and cost real debugging time chasing why "nothing happened" (network
tracking briefly appeared to show zero requests for an unrelated
reason, compounding the confusion) before comparing `window.fetch` logs
against the actual endpoint hit (`/reconcile/async`, not
`/reconcile/upload`) revealed the mismatch.

**Root cause:** not an application bug — scoping the click to
`.upload-runner button.reconcile-runner__button` instead of a
page-wide `querySelectorAll` immediately hit the right element and
the whole upload flow worked correctly end-to-end (upload → validate →
async job → poll → complete → auto-switch off the Upload & Run tab →
correct match/exception rows for the uploaded data). But two buttons
on one page sharing identical, non-specific text ("Run reconciliation")
with no further context is a real clarity risk for a human user too,
not just for blind DOM queries — confirmed by the fact that it fooled
this session's own click targeting first.

**Fix:** relabeled `UploadRunner`'s button from "Run reconciliation" to
"Run on these files" — cheap, removes the ambiguity, and needed no
other application changes since the underlying flow was already
correct.

### v2.1 Phase 14 — a real keyboard trap in the counterpart picker, found by an actual keyboard walk

**Issue:** while doing a live, keyboard-only pass across the dashboard
(recording every `focusin` target via a temporary listener rather than
trusting a visual read), tabbing from the counterpart-picker's search
input walked through every one of its open dropdown's candidate
buttons (up to 8) one at a time, then jumped past the "Note (why?)"
field and the Cancel/Submit buttons entirely, landing on an unrelated
exception row further down the page. A keyboard-only user could never
reach Submit via Tab once the dropdown had candidates in it.

**Root cause:** the dropdown's option `<button>` elements had no
`tabIndex`, so they defaulted into the page's normal sequential focus
order — the standard combobox/listbox ARIA pattern requires listbox
options to be excluded from Tab order entirely (`tabIndex={-1}`) and
navigated via Arrow keys on the owning input instead, which this
component already did correctly for Arrow/Enter but hadn't done for
Tab. A second, related issue surfaced while fixing the first: once the
buttons were excluded, Tab landed on the dropdown's `<ul>` container
instead — Chrome makes an `overflow:auto` container an implicit tab
stop once its content overflows, even with no `tabindex` set at all.

**Fix:** added `tabIndex={-1}` to both the option buttons and the
`<ul>` listbox container in `ExceptionList.jsx`'s `CounterpartPicker`.
Verified structurally via direct DOM inspection (`tabIndexProp: -1`
confirmed present on exactly the right elements post-fix) — full live
re-verification of the resulting Tab sequence was cut short mid-pass
when the browser tab lost foreground/input-routing status
(`document.hidden` flipped to `true` partway through, and the same
"Tab doesn't move focus" symptom then reproduced even on unrelated,
previously-working elements like the tab bar — confirming it was a
session/environment issue, not a regression from the fix). Not chased
further, per the standing "don't rabbit-hole on browser-automation
instability" guidance — `tabIndex={-1}`'s exclusion from sequential
focus navigation is basic, universal HTML platform behavior, not
something an app-level quirk could plausibly override, so the direct
DOM check stands as sufficient verification.

### v2.1 Phase 15 — a CSS Grid `minmax()` overflow trap, and a color-role collision the palette itself introduced

**Issue:** an isolated re-critique after the Phase 15 design pass (provenance
color palette, restructured stats header, self-hosted display font)
reproduced a real bug: in `MatchList.jsx`'s expanded detail view, a
bank narration value ("IMPS/RZP1637385475/RZP/PAY...") visually
overlapped the adjacent "Bank amount" figure — in the exact view a user
opens to verify *why* the LLM trusted a match.

**Root cause:** `.detail-grid`'s `grid-template-columns: repeat(auto-fit,
minmax(140px, 1fr))` combined with CSS Grid's default `min-width: auto`
on grid items. A long unbreakable run in the narration text can force
its item's intrinsic minimum width past the 140px track constraint,
widening that track and pushing/overlapping the next column — a
well-known Grid gotcha, not something the `minmax()` value alone
guards against.

**Fix:** `min-width: 0` on the grid item `div`s (lets the track actually
shrink to its constraint) plus `overflow-wrap: anywhere` on `dd` (wraps
long unbreakable content within its own box instead of overflowing it).
Verified live: zero geometric overlap between any two `dd` elements in
an expanded LLM-reasoned match's detail grid, confirmed via bounding-box
comparison, not just a visual read.

**A second finding, from the same re-critique:** the Phase 15 palette
gave the LLM tier its own color (reusing `--accent`, the existing
violet) — but `--accent` was *already* the settlement-side badge's
color and the app's primary action color. The same hue now meant
"click this," "the LLM decided this," and "this is the settlement
side" simultaneously — reintroducing a smaller version of the exact
"one undifferentiated accent" problem the palette was built to solve,
just relocated to a new pair of components. Root cause: adding a new
semantic role for a color (tier provenance) without auditing every
*other* place that color was already doing a different job.

**Fix:** gave `.side-badge` (settlement) a neutral bordered treatment
(`--surface`/`--text-h`/`--border`) instead of `--accent` — "which
side" is structural metadata, not a trust signal, so it no longer
borrows a color that means something else elsewhere. `.side-badge--bank`
was untouched (already used `--warn`, not part of the collision).

Both fixes verified via a full re-critique: score moved from the
Phase 12 baseline of 23/40 to 27/40, with the P0 and one of the three
original P1s already resolved by earlier phases, and both P1s found by
*this* re-critique fixed the same session they were found. See
`.impeccable/critique/` for both full snapshots.

### v2.1 final verification — `MatchList` rows didn't inherit `ExceptionList`'s flex-shrink wrapper, overflowing the page on real LLM-matched data

**Issue:** a post-close-out systematic-debugging pass (live against a
real 100-record run, not just lint/build/tests) found the Matches tab
overflowing the page horizontally — `document.documentElement.scrollWidth`
exceeded `window.innerWidth` by 800px+. It only showed up on the 10
`llm-reasoned` matches, whose reason text is a full generated sentence
(up to 256 chars) rather than the short fixed-form text `exact`/`fuzzy`
matches use, so it was invisible on typical fixture data and never
caught by a visual read of the first few rows.

**Root cause:** `ExceptionList.jsx` wraps its row button in a
`<div className="exception-row__head">` (`display: flex`), which is
what makes `.exception-row__summary { flex: 1; min-width: 0 }` actually
take effect and let `.exception-row__reason`'s `overflow: hidden;
text-overflow: ellipsis` truncate long text. `MatchList.jsx` never got
that wrapper — its row button was a direct child of `<li>`, a plain
block box, so the button's own `flex: 1; min-width: 0` had no effect
(flex properties are inert on an element that isn't itself a flex item).
The `<button>` shrink-to-fit its own content instead, and every match
row silently sized itself to its reason text's full width — confirmed
by measuring all 90 rows: button width tracked reason-text length
1:1 (844px for 50 chars, 2333px for 256 chars) instead of the uniform
column width a working flex layout produces.

**Fix:** wrapped `MatchRow`'s button in the same `.exception-row__head`
div `ExceptionList.jsx` uses (`MatchList.jsx`). Verified precisely, not
just visually: all 90 rows now measure a uniform width regardless of
reason length, `scrollWidth` no longer exceeds `innerWidth`, and row
expand/collapse still works post-fix. Lint, build, and the full 46-test
Vitest suite stay clean — this is a pure-CSS/JSX structural fix with no
behavior change, so no new test was added (the existing suite has no
DOM-rendering harness; the bug was a layout defect, not a logic one,
and was caught and verified live in-browser instead).

Also worth recording since it shaped how long this took to isolate:
the same debugging session's *first* two "failures" it found (a
"Couldn't load the dashboard: Failed to fetch" error, then intermittent
`503`s on `/runs`) turned out to be entirely self-inflicted — a second
backend and a second frontend dev server started on top of ones already
running, landing on the wrong port and the wrong CORS origin. Neither
was a real app bug; both resolved by killing the redundant processes
and re-testing against the app's actual already-running instances.
Recorded here as a reminder that "reproduce against a freshly started
dev server" is not automatically a clean baseline in a repo where
`npm run dev` may already be running.

---

### Scale-testing — parallelizing the LLM tier overwhelmed the Ollama cloud endpoint's concurrency limit

**Issue:** after parallelizing `reconcile.py`'s LLM tier (Tier 4) to fire up
to `LLM_MAX_WORKERS=8` concurrent Ollama calls instead of one at a time,
running the real (non-mocked) engine against `data/batch_1000` produced
far worse match quality than the sequential version — 69 of the 100
LLM-eligible settlements exhausted all 3 retries and fell back to a false
"no match" exception. The backend log showed the actual cause immediately:
`LLM call failed ... (too many concurrent requests (status code: 429)),
gave up`, repeated for the same handful of settlements. Caught before
trusting the run's output, by reading `docs/BUILD-CHALLENGES.md`-style log
output rather than only the final accuracy number.

**Investigation:** reproduced directly against the real endpoint rather
than guessing a safe worker count — a standalone concurrency probe
(`ThreadPoolExecutor` firing N concurrent `ollama.chat()` calls against
`gpt-oss:20b-cloud`, mirroring the real batch's sustained load) showed
6 workers completing 30/30 calls cleanly, while 8 workers rejected
roughly two-thirds of calls outright with HTTP 429 — and the rejections
returned in ~0.3-0.4s, far faster than any real inference, confirming the
endpoint was bouncing the request before even attempting it, not timing
out under load.

**Fix:** lowered `LLM_MAX_WORKERS`'s default from 8 to 5 (a margin below
the empirically-confirmed 6-workers-safe/8-workers-fails boundary, leaving
room for other concurrent Ollama traffic such as the Q&A agent). Separately
hardened `llm_matcher.get_llm_verdict()` to detect a 429 specifically (via
`ollama.ResponseError.status_code`, a structured field, not string
matching) and give it a longer, wider retry budget
(`MAX_ATTEMPTS_RATE_LIMITED=6`, 1.0s backoff base) than a generic failure,
since a rate-limit rejection is a near-guaranteed success on retry once
other in-flight calls clear — unlike a genuine error, it shouldn't "give
up" on the same short budget. Re-verified with the same concurrency probe
methodology (6 and 30-call sustained-load probes both clean) before
re-running the real batch.

Later hardened further: even 5-6 concurrent workers turned out to still
occasionally 429 under sustained multi-endpoint load (the Q&A agent and
reconciliation competing for the same account), so `LLM_MAX_WORKERS`'s
default was lowered again to 1 (fully sequential) as the only setting
confirmed reliable across sessions. With concurrency off the table, the
batching effort below became the only remaining lever for wall-clock time.

---

### Batching the LLM tier instead of parallelizing it

**Context:** with `LLM_MAX_WORKERS` pinned to 1 for reliability (above),
concurrency can't reduce wall-clock time on the LLM tier — so
`reconcile.py` was changed to optionally group multiple settlements into
one Ollama call (`get_llm_verdicts_batch`, via `RECONCILE_LLM_BATCH_SIZE`)
instead of one call per settlement, trading round trips for a slightly
larger prompt per call. Shipped at a conservative default of
`LLM_BATCH_SIZE=1` (identical to the original one-call-per-settlement
behavior) pending validation that a real multi-settlement prompt doesn't
degrade match quality.

**Validation:** ran `eval_reconcile.py` against a 20-settlement slice of
`data/batch_1000`'s LLM-eligible records (real `gpt-oss:20b-cloud` calls,
no mock/cache — those adapt per-item and wouldn't exercise the real
batched prompt) at `--batch-size 1` vs. `--batch-size 4`. Both runs scored
100% accuracy/precision/recall with zero false positives or negatives —
batching didn't change any verdict. Wall clock dropped from 288.9s to
249.7s for the same 20 calls (~13% faster; batching amortizes round-trip
overhead but each call now reasons over more input, so the gain is
sub-linear, not 4x).

**Fix:** raised `LLM_BATCH_SIZE`'s default from 1 to 4 now that accuracy
is confirmed to hold. Tests that mock `llm_fn` directly (not
`llm_batch_fn`) now pass `batch_size=1` explicitly so they stay pinned to
the single-item code path regardless of this default.

---

### Tier 3.5 — resolving the LLM tier's cases with an edit-distance algorithm instead

**Context:** inspecting the synthetic generator (`data/generate_synthetic_data.py`)
showed the `llm_reasoned` category isn't arbitrary — it's always: amount
identical, reference_id corrupted one of three specific ways (lowercased,
truncated by 3 chars, or one adjacent-pair transposition), date drifted
3-5 days, and the narration always contains the original reference's last
6 characters. That's a deterministic pattern, not a case that needs
reasoning — `rule_tier()` only fails on it because it requires reference
equality up front and never gets to compare date/amount at all.

**Fix:** added `algo_tier()` (Tier 3.5, `reconcile.py`): a restricted
edit-distance check (Levenshtein + adjacent transposition,
`_restricted_edit_distance()`) between settlement and candidate
reference_ids, gated behind three independent signals so no single one
carries the decision alone — amount must match exactly
(no tolerance stacking), the narration must contain the settlement
reference's last 6 characters, and the date must fall within
`RECONCILE_ALGO_DATE_TOLERANCE_DAYS` (default 7 — wider than the rule
tier's 2, since the other signals already establish identity). Runs
against the same shortlisted candidates already computed for the LLM
tier, so settlements it resolves never generate an LLM call at all.

**Validation:** ran `eval_reconcile.py --mock-llm` (llm_fn never actually
invoked, since nothing reached the LLM tier) across `batch_500`,
`batch_1000`, and `batch_10000`: 100% of what was previously
`llm_matched` became `algo_matched`, `llm_matched` dropped to 0, and
accuracy/precision/recall held at 1.0000 with zero false positives —
confirmed with `--no-llm` too, showing the tier works independent of
Ollama being reachable at all. At `batch_50000`, the harness reported 2
false positives; tracing them (row-level, not the harness's
settlement_id-keyed dict) showed both were `exact`/`fuzzy-*` (pure Tier
1-3) matches on one of 14 settlement_ids that collide at that scale — the
generator's 8-digit ID space (9x10^7 combinations) hits the birthday
bound around 50k rows, and both the eval harness's scoring and the
engine's own match list are keyed by settlement_id, so a genuine ID
collision misattributes one of the two colliding settlements' matches.
Confirmed pre-existing and unrelated to Tier 3.5 directly: a row-level
check of the exact (settlement_id, bank_txn_id) pairs found all 5,000
`algo_matched` records at that scale exactly correct, with zero missed
`llm_reasoned` pairs. Not fixed here (out of scope — it's a synthetic-data
ID-density issue, not a reconciliation bug) but worth knowing before
trusting `batch_50000`'s eval-harness accuracy number at face value.

---

### Tier 3.5 auto-accepted without an LLM call — reversed to require verification

**Context:** the previous entry's Tier 3.5 auto-accepted an edit-distance +
narration match with zero LLM involvement. That's correct on this
synthetic data (validated at the time), but edit-distance + a narration
substring is still a heuristic, not an identity check — on real (non-
synthetic) bank exports it's plausible for an unrelated reference_id to
coincidentally land within edit distance with a coincidentally-matching
narration substring, especially at scale. Explicitly requested: require an
LLM to confirm every Tier 3.5 candidate before accepting it, rather than
trusting the heuristic alone.

**Fix:** `run_reconciliation()`'s Tier 3.5 loop now sends each
algorithmically-identified candidate to `llm_fn` as a single-candidate
verification call before accepting it (`reconcile.py`, the `algo_verified`
block). Three outcomes:
  - LLM confirms → accepted as `algo-reconstructed`, same as before, with
    the LLM's reasoning appended to the audit reason and `model`/
    `candidates_considered` populated for traceability.
  - LLM rejects → falls through to the normal Tier 4 path with the full
    multi-candidate shortlist (not discarded, and not retried against a
    second algo candidate) — confirmed working on real data below.
  - `use_llm=False` → Tier 3.5 doesn't fire at all (nothing to verify
    with), same "LLM tier skipped" exception path any other
    ambiguous-middle settlement gets without an LLM available.

**Validation:** re-ran the same real-`gpt-oss:20b-cloud`, no-mock/no-cache
methodology as the batching validation — 20 llm-tier settlements sliced
from `data/batch_1000`. Result: 19/20 confirmed by the verification call
and accepted as `algo-reconstructed`; 1 was rejected by the narrower
single-candidate prompt but correctly fell through and was resolved by
Tier 4's full-context reasoning (`llm-reasoned`) — the fallthrough path
worked on a real rejection, not just in a hand-written test. Final
accuracy/precision/recall: 1.0000, zero false positives, across both
paths combined. Wall clock: 79.7s for those 20 calls (~4s/call average) —
notably faster than the original pre-Tier-3.5 baseline's ~14.5s/call
(same doc, batching section), because a single-candidate yes/no
confirmation prompt is simpler for the model to reason over than the
original multi-candidate prompt, even though a call is now made for
essentially every one of these settlements again.

---

### Two failed attempts to speed up Tier 3.5 verification, and why the third was declined

**Context:** with every Tier 3.5 candidate now requiring an LLM
confirmation (previous entry), a 1000-settlement batch with ~100
candidates took ~7 minutes — ~100 sequential round trips at ~4s/call,
since `LLM_MAX_WORKERS` stays at 1 for the documented rate-limit reasons
above. Two optimizations were tried and measured against the real cloud
endpoint before either was kept or discarded.

**Attempt 1 — batch verification calls across settlements, the same lever
that worked for Tier 4:** grouping several different settlements' single-
candidate confirmations into one prompt (reusing `get_llm_verdicts_batch`)
measured **slower**, not faster: 125.9s vs. a 79.7s baseline for the same
20 real items. Tracing why: batching made the model measurably more
conservative — more rejections, and each rejection falls through to a
full Tier 4 call (more expensive than the verification call it replaced),
so fewer round trips didn't translate to less wall-clock time. Reverted;
Tier 3.5 verification stays one call per candidate.

**Attempt 2 — reduce reasoning effort via Ollama's `think` parameter:** an
isolated benchmark (same fixed prompt, 8 interleaved trials) showed
`think="low"` averaging 2.65s vs. 3.53s unset (~25% faster) with no
apparent quality drop. Applied as the default and re-tested on the real
20-item batch, back-to-back against `think` unset to control for cloud
time-of-day drift: `think="low"` took 125.5s, `think` unset took 70.0s —
worse, not better, reversing the isolated benchmark's own signal.
Conclusion: a single fixed easy prompt is not a reliable proxy for a
varied real workload when the underlying effect size is this sensitive to
prompt difficulty and cloud queue conditions; the isolated benchmark
should have been validated against the real batch before being applied,
not after. Fully reverted (no `think` parameter is set).

**Investigated but declined — raise `LLM_MAX_WORKERS` for verification
specifically:** since verification prompts are much lighter than the
original multi-candidate reasoning prompt that produced the documented
429s, concurrency was re-probed rather than assumed still-unsafe: 30/30
calls succeeded cleanly at 4 concurrent workers (~1.5x faster than
sequential). Not shipped — the earlier concurrency section of this same
document already recorded that 5-6 workers looked clean in a similarly-
sized probe, then intermittently hit 429s under sustained real load
competing with the Q&A agent, and a single 30-call test can't rule that
out. Presented to the user as an option alongside a lower-risk
alternative (skip verification only for candidates whose reference_id
already matches exactly case-insensitively — the same evidence rule_tier
already auto-accepts unverified, just with a wider date window; only
genuinely-reconstructed references would still need confirmation). Both
declined: verification stays mandatory for every Tier 3.5 candidate,
`LLM_MAX_WORKERS` stays at 1, and the ~4s/call sequential cost is accepted
as the price of confirming every heuristic match.

---

## Template for new entries

```
### Phase N — short title
**Issue:** what broke or went wrong, and the observed symptom.
**Fix:** what changed to resolve it.
```
