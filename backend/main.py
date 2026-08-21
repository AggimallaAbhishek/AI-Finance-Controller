import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import audit
import qa_agent
import reconcile

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_SETTLEMENT = DATA_DIR / "settlement.csv"
DEFAULT_BANK = DATA_DIR / "bank_statement.csv"
DEFAULT_OUTDIR = DATA_DIR / "output"
DEFAULT_DB = DEFAULT_OUTDIR / "audit.db"

app = FastAPI(title="AI Finance Controller")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return audit.connect(DEFAULT_DB)


def resolve_run_id(conn, run_id):
    run_id = run_id or audit.latest_run_id(conn)
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


class QARequest(BaseModel):
    question: str
    run_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-finance-controller-backend"}


@app.post("/reconcile")
def run_reconcile(req: ReconcileRequest = ReconcileRequest()):
    result = reconcile.run_and_persist(
        settlement_path=req.settlement_path or DEFAULT_SETTLEMENT,
        bank_path=req.bank_path or DEFAULT_BANK,
        outdir=DEFAULT_OUTDIR,
        db_path=DEFAULT_DB,
        use_llm=req.use_llm,
        model=req.model,
    )
    return {"run_id": result["run_id"], "stats": result["stats"]}


@app.get("/runs")
def get_runs():
    conn = get_conn()
    try:
        runs = audit.list_runs(conn)
        for r in runs:
            r["stats"] = json.loads(r.pop("stats_json"))
        return {"count": len(runs), "runs": runs}
    finally:
        conn.close()


@app.get("/matches")
def get_matches(run_id: Optional[str] = None):
    conn = get_conn()
    try:
        run_id = resolve_run_id(conn, run_id)
        matches = [_with_parsed_candidates(m) for m in audit.list_matches(conn, run_id)]
        return {"run_id": run_id, "count": len(matches), "matches": matches}
    finally:
        conn.close()


@app.get("/exceptions")
def get_exceptions(run_id: Optional[str] = None):
    conn = get_conn()
    try:
        run_id = resolve_run_id(conn, run_id)
        exceptions = [_with_parsed_candidates(e) for e in audit.list_exceptions(conn, run_id)]
        return {"run_id": run_id, "count": len(exceptions), "exceptions": exceptions}
    finally:
        conn.close()


@app.get("/audit")
def get_audit_log(run_id: Optional[str] = None):
    conn = get_conn()
    try:
        run_id = resolve_run_id(conn, run_id)
        entries = [_with_parsed_candidates(e) for e in audit.list_audit_log(conn, run_id)]
        return {"run_id": run_id, "count": len(entries), "audit_log": entries}
    finally:
        conn.close()


@app.get("/audit/{record_id}")
def get_audit_trace(record_id: str, run_id: Optional[str] = None):
    conn = get_conn()
    try:
        run_id = resolve_run_id(conn, run_id)
        trace = audit.get_trace(conn, record_id, run_id)
        trace["decisions"] = [_with_parsed_candidates(d) for d in trace["decisions"]]
        if not trace["decisions"] and not trace["settlement_record"] and not trace["bank_record"]:
            raise HTTPException(status_code=404, detail=f"No record found for id '{record_id}' in run {run_id}")
        return trace
    finally:
        conn.close()


@app.post("/qa")
def ask_question(req: QARequest):
    conn = get_conn()
    try:
        return qa_agent.answer(req.question, conn, req.run_id)
    finally:
        conn.close()
