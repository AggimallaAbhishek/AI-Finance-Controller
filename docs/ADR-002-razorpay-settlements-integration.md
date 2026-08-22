# ADR-002: Razorpay Settlements API loader, scheduled reconciliation, and dashboard file upload

**Status:** Implemented — Razorpay loader and scheduled-reconciliation script are code-complete
and unit-tested but unverified against a real Razorpay account (see honesty note below);
dashboard file upload is implemented, tested, and verified live end-to-end in a real browser.
**Builds on:** ADR-001 (hybrid rules + LLM reconciliation), project_plan_v2.md Phase 12

## Context

Phase 12 is the most provisional phase in v2.0: it depends on Razorpay
sandbox access that isn't currently available. No `.env`, no credentials,
no existing Razorpay client code exist in this repo as of this writing.
This ADR proceeds with the two planned capabilities anyway, built so
they're ready to point at real credentials the moment they exist,
verified as far as possible without them — plus a third, user-requested
capability that shares the same underlying idea (a new way to get
settlement/bank data into a run without touching server-side files):

1. A Razorpay Settlements API loader, as an alternative to the existing
   CSV loader — mapped into the same `Settlement` dataclass so
   `run_reconciliation()` never needs to know which source produced its
   input.
2. Scheduled/recurring reconciliation with a match-rate-delta digest.
3. Dashboard file upload — a user can upload their own settlement/bank
   CSVs from the browser and trigger a run against them, instead of only
   the server's bundled default files.

**Honesty note on the exit check:** project_plan_v2.md's stated Phase 12
exit check — "the engine produces the same honestly-reported match rate /
exception list / audit trail against real Razorpay data as it does
against synthetic data" — cannot be verified live without credentials.
This ADR does not claim that check is met. What *is* verified: the
request URL, method, and error response shape are confirmed correct
against Razorpay's live API (see below), and the loader is fully
unit-tested against that real, observed contract via dependency
injection — not against a guessed one.

### Verified against the real API (no credentials required)

```
$ curl -s -w "\nHTTP_STATUS:%{http_code}\n" "https://api.razorpay.com/v1/settlements?count=1"
{"error":{"description":"Please provide your api key for authentication purposes","code":"BAD_REQUEST_ERROR"}}
HTTP_STATUS:401
```

This confirms the endpoint, method, and Razorpay's real error envelope
shape (`{"error": {"code": ..., "description": ...}}`) — the error
handling below is built against this observed shape, not assumed.

## Decision

### 1. `backend/razorpay_client.py` (new module)

Mirrors `llm_matcher.py`'s role in the existing architecture: an I/O
client that returns validated domain objects, keeping `reconcile.py`'s
matching engine free of network/auth concerns.

```python
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"

class RazorpayAPIError(Exception):
    """Raised for a non-200 Razorpay response. Message is built from the
    real {"error": {"description": ...}} envelope when present, so a
    caller sees Razorpay's own explanation, not a generic HTTP code."""

def fetch_settlements_page(key_id, key_secret, count=100, skip=0,
                            from_ts=None, to_ts=None, http_get=httpx.get):
    """One page of GET /v1/settlements. http_get is injectable — mirrors
    llm_fn in run_reconciliation() — so tests never make a real network
    call and never need real credentials."""

def load_settlements_from_razorpay(key_id, key_secret, from_ts=None,
                                    to_ts=None, http_get=httpx.get):
    """Paginates fetch_settlements_page (count=100 per page, via `skip`)
    until a short page ends the collection. Returns list[Settlement] —
    the exact same dataclass load_settlements() (CSV) returns."""
```

Field mapping from Razorpay's documented settlement entity to the
existing `Settlement` dataclass:

| `Settlement` field | Razorpay field | Notes |
|---|---|---|
| `settlement_id` | `id` | e.g. `"setl_..."` |
| `reference_id` | `utr` or `id` | UTR is the bank-visible reference that would actually appear in a real bank statement's narration — this is what makes `rule_tier()`'s exact `reference_id` match meaningful against *real* bank data. Falls back to `id` when `utr` is unset (e.g. `status="created"`, not yet bank-settled) — an honest miss, not a fabricated match; it legitimately falls to the LLM tier or an exception like any other genuinely ambiguous record. |
| `amount` | `amount` | Razorpay reports paise as an int; converted via `Decimal(amount) / 100` to match the engine's Decimal-rupee convention everywhere else. |
| `date` | `created_at` | Unix timestamp → `date.fromtimestamp(...)`. |
| `status` | `status` | Passed through **verbatim** (e.g. `"processed"`, not `"settled"`) — deliberately not normalized to the synthetic CSV's vocabulary. The exception-reasoning text (`"settlement status is 'processed'"`) will honestly reflect what Razorpay actually reported, consistent with this project's no-paper-over-reality stance (ADR-001). |

### 2. Wiring into the existing pipeline

`reconcile.run_and_persist()` gains:
- `settlement_source="csv"` (default — existing CSV behavior is
  completely unchanged)
- `razorpay_key_id`, `razorpay_key_secret`, optional `razorpay_from_ts`/
  `razorpay_to_ts`

When `settlement_source="razorpay"`, it calls
`load_settlements_from_razorpay(...)` instead of `load_settlements(path)`.
Bank statements stay CSV-only — per the original plan, there's no single
"bank API" equivalent to target.

`main.py`'s `ReconcileRequest` gains `settlement_source: str = "csv"`.
Credentials are read **server-side only**, from `RAZORPAY_KEY_ID` /
`RAZORPAY_KEY_SECRET` env vars (via the already-present `python-dotenv`)
— never accepted from the request body. An API secret should never
round-trip through the browser. If `settlement_source="razorpay"` and
those env vars are unset, the endpoint returns 400 with a clear message
rather than a confusing downstream `RazorpayAPIError`.

`reconcile.py`'s CLI gains a matching `--source {csv,razorpay}` flag for
local/demo use, reading the same env vars.

Both `/reconcile` and `/reconcile/async` share this change automatically
since they both call `run_and_persist()` — no duplicated logic (matches
the existing pattern documented in `run_and_persist`'s own docstring:
"Shared by the CLI and the FastAPI /reconcile route, so both go through
the exact same path").

### 3. `backend/scheduled_reconcile.py` (new, standalone script)

A pure, independently-testable digest function plus a thin CLI wrapper.
Meant to be invoked by whatever scheduler the user already has (cron,
launchd, a GitHub Actions cron trigger) — it does not loop, sleep, or
manage its own schedule.

```python
def build_digest(new_run_id, new_stats, previous_run_id, previous_stats):
    """Pure function, no I/O — easy to unit test directly. Returns a
    dict: run_id, match_rate, match_rate_delta (None if no previous
    run), exception_count, previous_run_id."""

def main():
    # 1. capture audit.latest_run_id() BEFORE running (the "previous" run)
    # 2. run reconcile.run_and_persist() (CSV or --source razorpay)
    # 3. build_digest(...) and print it as JSON to stdout
    # 4. if match_rate_delta < -0.05: print a WARNING to stderr
```

No Slack/webhook push in this iteration — the plan said a digest "could"
push somewhere, but no destination was specified, and adding one now
would be speculative scope. stdout/stderr is enough for any external
scheduler to redirect into a log, email digest, or webhook of the user's
own choosing later.

### 4. Dashboard file upload (`POST /reconcile/upload` + "Upload & Run" tab)

Not part of the original Phase 12 plan text, but added here because it's
the same underlying capability (a new way to feed the pipeline data) and
reuses the exact infrastructure Phase 11 and section 2 above already
built.

**Backend.** New `POST /reconcile/upload`, multipart: `settlement_file`,
`bank_file` (both required), plus `use_llm`/`model` form fields.

```python
def _start_job(req: ReconcileRequest) -> str:
    """Factored out of start_reconcile_job so /reconcile/async and
    /reconcile/upload share one job-starting code path — no duplicated
    JOBS-dict/threading logic."""
    job_id = uuid4().hex
    JOBS[job_id] = {"status": "running", "stage": "starting", "done": 0,
                     "total": 0, "result": None, "error": None}
    threading.Thread(target=_run_reconcile_job, args=(job_id, req), daemon=True).start()
    return job_id

@app.post("/reconcile/upload", status_code=202)
async def start_upload_reconcile_job(
    settlement_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
    use_llm: bool = Form(True),
    model: Optional[str] = Form(None),
):
    """Saves both files to data/uploads/<uuid>/, then validates by
    actually calling load_settlements()/load_bank_entries() — not a
    hand-written header-checker that could drift from what the real
    loader accepts. Fails fast with a specific 400 before any job
    starts or LLM call happens. On success, delegates to _start_job()."""
```

- Each file capped at 5MB (checked after read) — cheap abuse insurance
  for a new unauthenticated upload endpoint; not full hardening (auth is
  explicitly out of scope for v2.0 per project_plan_v2.md).
- Validation error translation: `KeyError` → `"missing required column:
  <name>"`; `decimal.InvalidOperation`/`ValueError` (bad amount/date) →
  a translated parse error naming the problem. Both wrap whichever
  `load_settlements()`/`load_bank_entries()` actually raised, so the
  message can never drift from the real parsing behavior.
- Uploaded files are kept permanently at `data/uploads/<uuid>/`, same
  reasoning as every other run's data: the `runs` table already stores
  `settlement_file`/`bank_file` paths, so keeping the actual file there
  keeps that run's audit trail genuinely re-inspectable. No cleanup job
  — a 50-record CSV costs nothing to keep, and Phase 11's own
  BUILD-CHALLENGES entry already established this project's stance that
  extra real runs in `audit.db` are useful history, not clutter.

**Frontend.** A third tab, "Upload & Run", next to Exceptions/Matches.
Two file inputs (`accept=".csv"`) + a "Run reconciliation" button,
disabled until both are chosen. A new `useReconcileJob` hook is
extracted from `ReconcileRunner`'s existing 500ms-poll/stage-label/
progress-bar logic, so both `ReconcileRunner` (calls
`startReconcileAsync`) and the new `UploadRunner` (calls a new
`uploadAndReconcile(settlementFile, bankFile, opts)` in `api.js`) share
one implementation instead of two copies of the same polling code. Same
completion flow as today: `onComplete(run_id)` refreshes the run list
and switches to the new run.

`UploadRunner` is also placed in the empty state (no run yet)
alongside the existing default-data `ReconcileRunner`, since a
first-time user wanting to try the tool against their own data is a
real, likely case and the component already supports it for free.

**Validation is bundled into one call**, not a separate
"validate-then-run" round trip: `/reconcile/upload` validates
synchronously and only starts the job on success, so there's no
extra API call needed before the user can click "Run".

Note: "upload" is not a third `settlement_source` value. Once the files
are saved to disk, `/reconcile/upload` builds a plain `ReconcileRequest`
with `settlement_path`/`bank_path` pointing at those saved files and
`settlement_source` left at its default `"csv"` — from that point on
it's indistinguishable from any other CSV-sourced run.

## Alternatives considered

- **Official `razorpay` Python SDK** instead of raw `httpx` — rejected:
  adds a new dependency for a single documented GET endpoint with simple
  pagination; raw `httpx` (already a project dependency via
  FastAPI/Starlette) plus an injectable `http_get` keeps the same
  dependency-injection testing pattern already used for `llm_fn` and
  `progress_cb` in `reconcile.py`.
- **In-process background scheduler** (e.g. APScheduler running inside
  the FastAPI server) — rejected: a new dependency, only runs while the
  server process stays up, and more moving parts than this demo app
  needs. A standalone script invoked by the host's existing scheduler
  (cron/launchd/CI) needs nothing new and matches how `reconcile.py`
  already works as a standalone CLI.
- **Normalizing Razorpay's real status vocabulary** (`"processed"`) to
  the synthetic CSV's (`"settled"`) — rejected: would quietly paper over
  a real difference between synthetic and live data, which is exactly
  the kind of dishonesty ADR-001 and the project's success criteria
  explicitly reject.
- **A hand-written CSV header/type validator for uploads** — rejected:
  a second parsing implementation that could silently drift from what
  `load_settlements()`/`load_bank_entries()` actually accept, passing
  validation but still failing (or worse, parsing differently) in the
  real run. Calling the real loaders directly for validation makes that
  drift structurally impossible.
- **A separate `POST /reconcile/validate` step before upload** —
  rejected: an extra round trip for no real benefit, since validation
  is already synchronous and fast (pure CSV parsing, no LLM calls);
  bundling it into `/reconcile/upload` means one API call either 400s
  with a specific reason or starts the job.

## Consequences

- The matching engine (`run_reconciliation()`) requires zero changes —
  it only ever sees `Settlement`/`BankEntry` objects, regardless of
  source. This is the payoff of the dataclass-mapping design.
- The Razorpay loader is fully unit-testable today, with zero real
  credentials, via the same injectable-function pattern the codebase
  already uses for the LLM tier.
- Real-world verification (the actual Phase 12 exit check) remains
  blocked until Razorpay sandbox credentials exist. When they do,
  verification is a matter of running `reconcile.py --source razorpay`
  once and inspecting the resulting match rate/exceptions/audit trail —
  no code changes should be needed at that point.
- `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` become new required
  environment variables for the Razorpay path only; the CSV path (the
  default, and everything built through Phase 11) is entirely
  unaffected.
- `/reconcile/async` and `/reconcile/upload` share one job-starting
  code path (`_start_job`), so the progress-polling UX stays identical
  regardless of how the data got in — default files, Razorpay, or an
  upload.
- `data/uploads/` will grow over time as users try their own files,
  same as `audit.db` already does with runs — an accepted, documented
  tradeoff for a demo app, not an oversight.
