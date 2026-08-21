"""Command-line inspector for the audit trail — thin presentation layer over
audit.py's query functions. audit.py owns the schema and queries; this file
only formats and prints.

Usage:
  python3 audit_cli.py --db ../data/output/audit.db trace <record_id>
  python3 audit_cli.py --db ../data/output/audit.db runs
  python3 audit_cli.py --db ../data/output/audit.db matches [--run-id ...]
  python3 audit_cli.py --db ../data/output/audit.db exceptions [--run-id ...]
"""

import argparse

import audit


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
    conn = audit.connect(args.db)

    if args.command == "trace":
        _print_trace(audit.get_trace(conn, args.record_id, args.run_id))
    elif args.command == "runs":
        for row in audit.list_runs(conn):
            print(row)
    elif args.command == "exceptions":
        run_id = args.run_id or audit.latest_run_id(conn)
        for row in audit.list_exceptions(conn, run_id):
            print(row)
    elif args.command == "matches":
        run_id = args.run_id or audit.latest_run_id(conn)
        for row in audit.list_matches(conn, run_id):
            print(row)


if __name__ == "__main__":
    main()
