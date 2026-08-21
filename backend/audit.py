"""Audit trail storage: every reconciliation run, every source record, and
every match/exception decision, in SQLite — queryable by record ID.

This is what makes a decision explainable: get_trace(record_id) returns the
decision plus the exact input row(s) it was based on, not just an ID.
"""

import json
import sqlite3
from datetime import datetime, timezone
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
    # check_same_thread=False: FastAPI's threadpool doesn't guarantee a
    # generator dependency's yield and the route handler's body run on the
    # same OS thread. Safe here because each connection is only ever used
    # by one request's own logical flow at a time (create -> use -> close
    # within a single get_conn() dependency lifecycle) — never shared
    # concurrently between two different requests.
    conn = sqlite3.connect(db_path, check_same_thread=False)
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
    """Current exceptions only — excludes any exception row that a later
    row (by id) has superseded for the same identity (settlement_ref or
    bank_ref), whether superseded by a human "confirmed no-match" row or a
    human "resolved to match" row. audit_log itself is never mutated; this
    is a read-time view over its full, immutable history."""
    rows = conn.execute(
        """
        SELECT * FROM audit_log a
        WHERE a.run_id = ? AND a.match_status = 'exception'
        AND NOT EXISTS (
            SELECT 1 FROM audit_log b
            WHERE b.run_id = a.run_id AND b.id > a.id
            AND (
                (a.settlement_ref IS NOT NULL AND b.settlement_ref = a.settlement_ref)
                OR (a.bank_ref IS NOT NULL AND b.bank_ref = a.bank_ref)
            )
        )
        ORDER BY a.id
        """,
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_unmatched_bank_entries_over_amount(conn, run_id, min_amount):
    """Bank-side exceptions (no settlement match) above a Rupee threshold.
    Built on list_exceptions() (not a raw audit_log query) so a resolved
    exception can never show up here as if it were still unresolved."""
    bank_only_refs = [e for e in list_exceptions(conn, run_id) if e["bank_ref"] and not e["settlement_ref"]]
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


def _latest_row_for(conn, run_id, record_id):
    """Most recent audit_log row touching record_id as either identity, or
    None if it has no decision at all in this run."""
    row = conn.execute(
        "SELECT * FROM audit_log WHERE run_id = ? AND (settlement_ref = ? OR bank_ref = ?) "
        "ORDER BY id DESC LIMIT 1",
        (run_id, record_id, record_id),
    ).fetchone()
    return dict(row) if row else None


def resolve_exception(conn, run_id, record_id, resolution, note, matched_record_id=None):
    """Human resolution of a currently-open exception. `resolution` is
    "match" (link record_id to matched_record_id) or "no_match" (confirm
    the exception stands, with a note explaining why).

    Never mutates the original audit_log row — inserts a new one instead
    (tier="human"), so the audit trail stays a fully immutable history:
    the original algorithmic verdict and the human's later decision are
    both visible via get_trace(), in order. "Current status" queries
    (list_exceptions, list_matches) derive from the latest row per
    identity at read time.

    Raises ValueError for any invalid resolution attempt — unknown
    record, a record that isn't currently an exception, an unknown or
    already-resolved counterpart, or linking two records on the same side.

    The "is this still an exception" check and the insert happen inside a
    single BEGIN IMMEDIATE transaction, so two near-simultaneous resolve
    attempts for the same record (a double-click, two browser tabs) can't
    both read "still open" before either commits — SQLite serializes them,
    and the second sees the first's result and is correctly rejected,
    rather than both silently succeeding and leaving two competing rows.
    """
    if not note or not note.strip():
        raise ValueError("a note explaining the resolution is required")

    conn.execute("BEGIN IMMEDIATE")
    try:
        current = _latest_row_for(conn, run_id, record_id)
        if current is None:
            raise ValueError(f"no record found for id '{record_id}' in this run")
        if current["match_status"] != "exception":
            raise ValueError(f"'{record_id}' is not currently an exception (status: {current['match_status']})")

        is_settlement = current["settlement_ref"] == record_id
        timestamp = datetime.now(timezone.utc).isoformat()

        if resolution == "no_match":
            entry = {
                "timestamp": timestamp,
                "settlement_ref": record_id if is_settlement else None,
                "bank_ref": None if is_settlement else record_id,
                "match_status": "exception",
                "confidence": None,
                "reason": note,
                "tier": "human",
            }
        elif resolution == "match":
            if not matched_record_id:
                raise ValueError("matched_record_id is required when resolution is 'match'")
            counterpart = _latest_row_for(conn, run_id, matched_record_id)
            if counterpart is None:
                raise ValueError(f"no record found for counterpart id '{matched_record_id}' in this run")
            if counterpart["match_status"] != "exception":
                raise ValueError(
                    f"counterpart '{matched_record_id}' is not currently an exception "
                    f"(status: {counterpart['match_status']})"
                )
            counterpart_is_settlement = counterpart["settlement_ref"] == matched_record_id
            if counterpart_is_settlement == is_settlement:
                raise ValueError("a match must link a settlement to a bank entry, not two of the same side")

            entry = {
                "timestamp": timestamp,
                "settlement_ref": record_id if is_settlement else matched_record_id,
                "bank_ref": matched_record_id if is_settlement else record_id,
                "match_status": "matched",
                "confidence": "human-resolved",
                "reason": note,
                "tier": "human",
            }
        else:
            raise ValueError("resolution must be 'match' or 'no_match'")

        save_audit_entries(conn, run_id, [entry])
    except Exception:
        conn.rollback()
        raise
    return _latest_row_for(conn, run_id, record_id)
