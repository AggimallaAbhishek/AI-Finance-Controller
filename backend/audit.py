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

    return {
        "record_id": record_id,
        "run_id": run_id,
        "decisions": [dict(d) for d in decisions],
        "settlement_record": dict(settlement) if settlement else None,
        "bank_record": dict(bank_entry) if bank_entry else None,
        "counterpart_settlement_record": dict(counterpart_settlement) if counterpart_settlement else None,
        "counterpart_bank_record": dict(counterpart_bank) if counterpart_bank else None,
    }


def _print_trace(trace):
    print(f"record_id: {trace['record_id']}  (run: {trace['run_id']})")
    if not trace["decisions"]:
        print("  no audit_log entry found for this record_id")
        return
    for d in trace["decisions"]:
        print(f"  decision: {d['match_status']}  confidence={d['confidence']}  tier={d['tier']}")
        print(f"    reason: {d['reason']}")
    for label in ["settlement_record", "bank_record", "counterpart_settlement_record", "counterpart_bank_record"]:
        if trace[label]:
            print(f"  {label}: {trace[label]}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="../data/output/audit.db")
    sub = parser.add_subparsers(dest="command", required=True)

    trace_p = sub.add_parser("trace", help="trace a settlement_id or txn_id to its decision + source rows")
    trace_p.add_argument("record_id")
    trace_p.add_argument("--run-id", default=None)

    sub.add_parser("runs", help="list all reconciliation runs")

    exc_p = sub.add_parser("exceptions", help="list exceptions for a run")
    exc_p.add_argument("--run-id", default=None)

    m_p = sub.add_parser("matches", help="list matches for a run")
    m_p.add_argument("--run-id", default=None)

    args = parser.parse_args()
    conn = connect(args.db)

    if args.command == "trace":
        _print_trace(get_trace(conn, args.record_id, args.run_id))
    elif args.command == "runs":
        for row in list_runs(conn):
            print(row)
    elif args.command == "exceptions":
        run_id = args.run_id or latest_run_id(conn)
        for row in list_exceptions(conn, run_id):
            print(row)
    elif args.command == "matches":
        run_id = args.run_id or latest_run_id(conn)
        for row in list_matches(conn, run_id):
            print(row)


if __name__ == "__main__":
    main()
