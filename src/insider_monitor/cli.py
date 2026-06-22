from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import InsiderMonitorPipeline
from .sec_client import SecClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch recent SEC insider transactions and build a daily report.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the pipeline.")
    run_parser.add_argument("--days", type=int, default=30, help="Rolling lookback window in days.")
    run_parser.add_argument("--tickers", type=Path, default=Path("config/tickers.csv"), help="Ticker CSV path.")
    run_parser.add_argument("--db", type=Path, default=Path("data/insider_transactions.db"), help="SQLite path.")
    run_parser.add_argument("--reports-dir", type=Path, default=Path("reports"), help="Report output directory.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        pipeline = InsiderMonitorPipeline(
            tickers_path=args.tickers,
            db_path=args.db,
            reports_root=args.reports_dir,
            sec_client=SecClient(),
        )
        result = pipeline.run(days=args.days)
        print(f"Tickers processed: {result.tickers_processed}")
        print(f"Form 4 filings processed: {result.filings_processed}")
        print(f"Transactions found: {result.transactions_found}")
        print(f"Transactions written: {result.transactions_written}")
        print(f"Report directory: {result.report_dir}")


if __name__ == "__main__":
    main()
