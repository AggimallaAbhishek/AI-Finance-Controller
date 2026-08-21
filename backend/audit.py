"""Audit trail storage: every reconciliation run, every source record, and
every match/exception decision, in SQLite — queryable by record ID.

This is what makes a decision explainable: get_trace(record_id) returns the
decision plus the exact input row(s) it was based on, not just an ID.
"""

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    settlement_file TEXT NOT NULL,
    bank_file TEXT NOT NULL,
    model TEXT,
    stats_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
    run_id TEXT NOT NULL,
    settlement_id TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    date TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (run_id, settlement_id)
);

CREATE TABLE IF NOT EXISTS bank_entries (
    run_id TEXT NOT NULL,
    txn_id TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    date TEXT NOT NULL,
    narration TEXT NOT NULL,
    PRIMARY KEY (run_id, txn_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    settlement_ref TEXT,
    bank_ref TEXT,
    match_status TEXT NOT NULL,
    confidence TEXT,
    reason TEXT NOT NULL,
    tier TEXT NOT NULL,
    model TEXT,
    candidates_considered TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_settlement_ref ON audit_log(settlement_ref);
CREATE INDEX IF NOT EXISTS idx_audit_bank_ref ON audit_log(bank_ref);
CREATE INDEX IF NOT EXISTS idx_audit_run_id ON audit_log(run_id);
"""


def connect(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_run(conn, run_id, timestamp, settlement_file, bank_file, model, stats):
    conn.execute(
        "INSERT INTO runs (run_id, timestamp, settlement_file, bank_file, model, stats_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, timestamp, str(settlement_file), str(bank_file), model, json.dumps(stats)),
    )
    conn.commit()


def save_settlements(conn, run_id, settlements):
    conn.executemany(
        "INSERT INTO settlements (run_id, settlement_id, reference_id, amount, date, status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(run_id, s.settlement_id, s.reference_id, str(s.amount), s.date.isoformat(), s.status)
         for s in settlements],
    )
    conn.commit()


def save_bank_entries(conn, run_id, bank_entries):
    conn.executemany(
        "INSERT INTO bank_entries (run_id, txn_id, reference_id, amount, date, narration) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(run_id, b.txn_id, b.reference_id, str(b.amount), b.date.isoformat(), b.narration)
         for b in bank_entries],
    )
    conn.commit()


def save_audit_entries(conn, run_id, audit_entries):
    conn.executemany(
        "INSERT INTO audit_log (run_id, timestamp, settlement_ref, bank_ref, match_status, "
        "confidence, reason, tier, model, candidates_considered) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(
            run_id, e["timestamp"], e.get("settlement_ref"), e.get("bank_ref"),
            e["match_status"], e.get("confidence"), e["reason"], e["tier"],
            e.get("model"), json.dumps(e["candidates_considered"]) if e.get("candidates_considered") else None,
        ) for e in audit_entries],
    )
    conn.commit()


def latest_run_id(conn):
    row = conn.execute("SELECT run_id FROM runs ORDER BY timestamp DESC LIMIT 1").fetchone()
    return row["run_id"] if row else None


def get_run(conn, run_id):
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(conn):
    rows = conn.execute("SELECT * FROM runs ORDER BY timestamp DESC").fetchall()
    return [dict(r) for r in rows]


def list_audit_log(conn, run_id):
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE run_id = ? ORDER BY id", (run_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_matches(conn, run_id):
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE run_id = ? AND match_status = 'matched' ORDER BY id",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_exceptions(conn, run_id):
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE run_id = ? AND match_status = 'exception' ORDER BY id",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_unmatched_bank_entries_over_amount(conn, run_id, min_amount):
    """Bank-side exceptions (no settlement match) above a Rupee threshold."""
    bank_only_refs = conn.execute(
        "SELECT bank_ref FROM audit_log WHERE run_id = ? AND match_status = 'exception' "
        "AND bank_ref IS NOT NULL AND settlement_ref IS NULL",
        (run_id,),
    ).fetchall()
    hits = []
    for row in bank_only_refs:
        entry = conn.execute(
            "SELECT * FROM bank_entries WHERE run_id = ? AND txn_id = ?",
            (run_id, row["bank_ref"]),
        ).fetchone()
        if entry and float(entry["amount"]) > float(min_amount):
            hits.append(dict(entry))
    return hits


def get_trace(conn, record_id, run_id=None):
    """Given a settlement_id or txn_id, return the decision(s) referencing it
    plus the exact input row(s) it was based on — the full "why" behind an
    output row, traceable to source data."""
    run_id = run_id or latest_run_id(conn)

    decisions = conn.execute(
        "SELECT * FROM audit_log WHERE run_id = ? AND (settlement_ref = ? OR bank_ref = ?) ORDER BY id",
        (run_id, record_id, record_id),
    ).fetchall()

    settlement = conn.execute(
        "SELECT * FROM settlements WHERE run_id = ? AND settlement_id = ?",
        (run_id, record_id),
    ).fetchone()

    bank_entry = conn.execute(
        "SELECT * FROM bank_entries WHERE run_id = ? AND txn_id = ?",
        (run_id, record_id),
    ).fetchone()

    counterpart_settlement = None
    counterpart_bank = None
    for d in decisions:
        if d["settlement_ref"] and d["settlement_ref"] != record_id:
            counterpart_settlement = conn.execute(
                "SELECT * FROM settlements WHERE run_id = ? AND settlement_id = ?",
                (run_id, d["settlement_ref"]),
            ).fetchone()
        if d["bank_ref"] and d["bank_ref"] != record_id:
            counterpart_bank = conn.execute(
                "SELECT * FROM bank_entries WHERE run_id = ? AND txn_id = ?",
                (run_id, d["bank_ref"]),
            ).fetchone()

    decision_dicts = []
    for d in decisions:
        dd = dict(d)
        if dd.get("candidates_considered"):
            dd["candidates_considered"] = json.loads(dd["candidates_considered"])
        decision_dicts.append(dd)

    return {
        "record_id": record_id,
        "run_id": run_id,
        "decisions": decision_dicts,
        "settlement_record": dict(settlement) if settlement else None,
        "bank_record": dict(bank_entry) if bank_entry else None,
        "counterpart_settlement_record": dict(counterpart_settlement) if counterpart_settlement else None,
        "counterpart_bank_record": dict(counterpart_bank) if counterpart_bank else None,
    }
