import json
import os
import threading
from decimal import InvalidOperation
from pathlib import Path
from typing import Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import audit
import qa_agent
import reconcile

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SETTLEMENT = DATA_DIR / "settlement.csv"
DEFAULT_BANK = DATA_DIR / "bank_statement.csv"
DEFAULT_OUTDIR = DATA_DIR / "output"
DEFAULT_DB = DEFAULT_OUTDIR / "audit.db"
UPLOADS_DIR = DATA_DIR / "uploads"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB — cheap abuse insurance for an unauthenticated endpoint

app = FastAPI(title="AI Finance Controller")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    conn = audit.connect(DEFAULT_DB)
    try:
        yield conn
    finally:
        conn.close()


def resolve_run_id(conn, run_id):
    if run_id:
        if not audit.get_run(conn, run_id):
            raise HTTPException(status_code=404, detail=f"No such run_id: '{run_id}'")
        return run_id
    run_id = audit.latest_run_id(conn)
    if not run_id:
        raise HTTPException(status_code=404, detail="No reconciliation run found. Call POST /reconcile first.")
    return run_id


def _with_parsed_candidates(row):
    if row.get("candidates_considered"):
        row["candidates_considered"] = json.loads(row["candidates_considered"])
    return row


class ReconcileRequest(BaseModel):
    settlement_path: Optional[str] = None
    bank_path: Optional[str] = None
    use_llm: bool = True
    model: Optional[str] = None
    settlement_source: str = "csv"  # "csv" or "razorpay" — see docs/ADR-002


class QARequest(BaseModel):
    question: str
    run_id: Optional[str] = None
    model: Optional[str] = None


class ResolveRequest(BaseModel):
    resolution: str  # "match" or "no_match"
    note: str
    matched_record_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-finance-controller-backend"}


def _resolve_razorpay_kwargs(req: ReconcileRequest):
    """Credentials are read server-side only, from the environment — never
    accepted from the request body, since an API secret should never
    round-trip through the browser. Raises before any job starts if
    settlement_source="razorpay" was requested but isn't configured, so
    the caller gets an immediate 400 instead of a job that fails later."""
    if req.settlement_source != "razorpay":
        return {}
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=400,
            detail="Razorpay integration not configured — set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
        )
    return {"razorpay_key_id": key_id, "razorpay_key_secret": key_secret}


@app.post("/reconcile")
def run_reconcile(req: ReconcileRequest = ReconcileRequest()):
    razorpay_kwargs = _resolve_razorpay_kwargs(req)
    result = reconcile.run_and_persist(
        settlement_path=None if req.settlement_source == "razorpay" else (req.settlement_path or DEFAULT_SETTLEMENT),
        bank_path=req.bank_path or DEFAULT_BANK,
        outdir=DEFAULT_OUTDIR,
        db_path=DEFAULT_DB,
        use_llm=req.use_llm,
        model=req.model,
        settlement_source=req.settlement_source,
        **razorpay_kwargs,
    )
    return {"run_id": result["run_id"], "stats": result["stats"]}


# In-memory job registry for the async trigger-run flow. A dashboard button
# firing a synchronous /reconcile (which can take a couple minutes across
# real LLM calls) has no way to show real progress — only a spinner that
# looks stuck. This lets the frontend poll actual stage/done/total instead.
# Deliberately process-local, not persisted: a job is a one-shot progress
# ticket for a run already durably recorded in audit.db by the time it's
# "done", not a record of its own that needs to survive a restart.
JOBS = {}
_JOBS_LOCK = threading.Lock()


def _run_reconcile_job(job_id, req, razorpay_kwargs=None):
    def on_progress(stage, done, total):
        with _JOBS_LOCK:
            JOBS[job_id].update(stage=stage, done=done, total=total)

    try:
        result = reconcile.run_and_persist(
            settlement_path=None if req.settlement_source == "razorpay" else (req.settlement_path or DEFAULT_SETTLEMENT),
            bank_path=req.bank_path or DEFAULT_BANK,
            outdir=DEFAULT_OUTDIR,
            db_path=DEFAULT_DB,
            use_llm=req.use_llm,
            model=req.model,
            settlement_source=req.settlement_source,
            progress_cb=on_progress,
            **(razorpay_kwargs or {}),
        )
        with _JOBS_LOCK:
            JOBS[job_id].update(
                status="done",
                result={"run_id": result["run_id"], "stats": result["stats"]},
            )
    except Exception as e:
        with _JOBS_LOCK:
            JOBS[job_id].update(status="error", error=str(e))


def _start_job(req: ReconcileRequest, razorpay_kwargs=None) -> str:
    """Factored out so /reconcile/async and /reconcile/upload share one
    job-starting code path — no duplicated JOBS-dict/threading logic."""
    job_id = uuid4().hex
    JOBS[job_id] = {
        "status": "running", "stage": "starting", "done": 0, "total": 0,
        "result": None, "error": None,
    }
    threading.Thread(target=_run_reconcile_job, args=(job_id, req, razorpay_kwargs), daemon=True).start()
    return job_id


@app.post("/reconcile/async", status_code=202)
def start_reconcile_job(req: ReconcileRequest = ReconcileRequest()):
    razorpay_kwargs = _resolve_razorpay_kwargs(req)
    return {"job_id": _start_job(req, razorpay_kwargs)}


@app.get("/reconcile/status/{job_id}")
def get_reconcile_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job_id: '{job_id}'")
    return job


def _translate_load_error(source_label: str, exc: Exception) -> str:
    """Wraps whichever error load_settlements()/load_bank_entries() (the
    real loaders — not a hand-written validator) actually raised into a
    specific, readable message, so it can never drift from what the real
    parsing behavior accepts."""
    if isinstance(exc, KeyError):
        return f"{source_label}: missing required column: {exc}"
    if isinstance(exc, (InvalidOperation, ValueError)):
        return f"{source_label}: could not parse a row ({exc})"
    return f"{source_label}: {exc}"


@app.post("/reconcile/upload", status_code=202)
async def start_upload_reconcile_job(
    settlement_file: UploadFile = File(...),
    bank_file: UploadFile = File(...),
    use_llm: bool = Form(True),
    model: Optional[str] = Form(None),
):
    upload_dir = UPLOADS_DIR / uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)
    settlement_path = upload_dir / "settlement.csv"
    bank_path = upload_dir / "bank_statement.csv"

    for upload, dest, label in (
        (settlement_file, settlement_path, "settlement file"),
        (bank_file, bank_path, "bank statement file"),
    ):
        content = await upload.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail=f"{label}: exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit")
        dest.write_bytes(content)

    # Validate by actually calling the real loaders (not a separate
    # hand-written header-checker) — fails fast, before any job starts
    # or LLM call happens, with a message that can't drift from what the
    # real run would do with this file.
    try:
        reconcile.load_settlements(settlement_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_translate_load_error("settlement file", e))
    try:
        reconcile.load_bank_entries(bank_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=_translate_load_error("bank statement file", e))

    # "upload" is not a third settlement_source — from here on it's a
    # plain CSV-sourced run pointed at the saved files (see docs/ADR-002).
    req = ReconcileRequest(settlement_path=str(settlement_path), bank_path=str(bank_path),
                            use_llm=use_llm, model=model)
    return {"job_id": _start_job(req)}


@app.get("/runs")
def get_runs(conn=Depends(get_conn)):
    runs = audit.list_runs(conn)
    for r in runs:
        r["stats"] = json.loads(r.pop("stats_json"))
    return {"count": len(runs), "runs": runs}


@app.get("/matches")
def get_matches(run_id: Optional[str] = None, conn=Depends(get_conn)):
    run_id = resolve_run_id(conn, run_id)
    matches = [_with_parsed_candidates(m) for m in audit.list_matches(conn, run_id)]
    return {"run_id": run_id, "count": len(matches), "matches": matches}


@app.get("/exceptions")
def get_exceptions(run_id: Optional[str] = None, conn=Depends(get_conn)):
    run_id = resolve_run_id(conn, run_id)
    exceptions = [_with_parsed_candidates(e) for e in audit.list_exceptions(conn, run_id)]
    return {"run_id": run_id, "count": len(exceptions), "exceptions": exceptions}


@app.get("/audit")
def get_audit_log(run_id: Optional[str] = None, conn=Depends(get_conn)):
    run_id = resolve_run_id(conn, run_id)
    entries = [_with_parsed_candidates(e) for e in audit.list_audit_log(conn, run_id)]
    return {"run_id": run_id, "count": len(entries), "audit_log": entries}


@app.get("/audit/{record_id}")
def get_audit_trace(record_id: str, run_id: Optional[str] = None, conn=Depends(get_conn)):
    run_id = resolve_run_id(conn, run_id)
    trace = audit.get_trace(conn, record_id, run_id)  # candidates_considered already parsed by audit.get_trace
    if not trace["decisions"] and not trace["settlement_record"] and not trace["bank_record"]:
        raise HTTPException(status_code=404, detail=f"No record found for id '{record_id}' in run {run_id}")
    return trace


@app.post("/exceptions/{record_id}/resolve")
def resolve_exception(record_id: str, req: ResolveRequest, run_id: Optional[str] = None, conn=Depends(get_conn)):
    run_id = resolve_run_id(conn, run_id)
    try:
        return audit.resolve_exception(conn, run_id, record_id, req.resolution, req.note, req.matched_record_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/qa")
def ask_question(req: QARequest, conn=Depends(get_conn)):
    return qa_agent.answer(req.question, conn, req.run_id, req.model)
