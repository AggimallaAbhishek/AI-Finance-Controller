"""Run one reconciliation and print a digest comparing it to the previous
run — meant to be invoked by whatever scheduler the host already has
(cron, launchd, a GitHub Actions cron trigger). This process itself does
not loop, sleep, or manage its own schedule; see docs/ADR-002 for why an
in-process scheduler was rejected in favor of this.

    python3 scheduled_reconcile.py [--source csv|razorpay] [--settlement ...] [--bank ...]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import audit
import reconcile

DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_SETTLEMENT = DATA_DIR / "settlement.csv"
DEFAULT_BANK = DATA_DIR / "bank_statement.csv"
DEFAULT_OUTDIR = DATA_DIR / "output"
DEFAULT_DB = DEFAULT_OUTDIR / "audit.db"
MATCH_RATE_DROP_WARNING_THRESHOLD = 0.05


def build_digest(new_run_id, new_stats, previous_run_id, previous_stats):
    """Pure function, no I/O — easy to unit test directly. delta is None
    when there's no previous run to compare against (the very first run
    against a given audit.db)."""
    delta = None
    if previous_stats is not None:
        delta = round(new_stats["match_rate"] - previous_stats["match_rate"], 4)
    return {
        "run_id": new_run_id,
        "match_rate": new_stats["match_rate"],
        "match_rate_delta": delta,
        "exception_count": new_stats["settlement_exceptions"] + new_stats["bank_exceptions"],
        "previous_run_id": previous_run_id,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settlement", type=Path, default=DEFAULT_SETTLEMENT)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM tier (rules only)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--source", choices=["csv", "razorpay"], default="csv")
    args = parser.parse_args()

    conn = audit.connect(args.db)
    previous_run_id = audit.latest_run_id(conn)
    previous_stats = json.loads(audit.get_run(conn, previous_run_id)["stats_json"]) if previous_run_id else None
    conn.close()

    if args.source == "razorpay":
        result = reconcile.run_and_persist(
            bank_path=args.bank, outdir=args.outdir, db_path=args.db,
            use_llm=not args.no_llm, model=args.model,
            settlement_source="razorpay",
            razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID"),
            razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET"),
        )
    else:
        result = reconcile.run_and_persist(
            args.settlement, args.bank, outdir=args.outdir, db_path=args.db,
            use_llm=not args.no_llm, model=args.model,
        )

    digest = build_digest(result["run_id"], result["stats"], previous_run_id, previous_stats)
    print(json.dumps(digest, indent=2))

    if digest["match_rate_delta"] is not None and digest["match_rate_delta"] < -MATCH_RATE_DROP_WARNING_THRESHOLD:
        print(
            f"WARNING: match rate dropped {abs(digest['match_rate_delta']) * 100:.1f} points "
            f"since run {previous_run_id}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
