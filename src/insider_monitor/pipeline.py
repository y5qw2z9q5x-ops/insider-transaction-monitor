from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .models import InsiderTransaction
from .reporter import Reporter
from .sec_client import SecClient, rolling_window_start
from .storage import Storage


@dataclass
class PipelineResult:
    tickers_processed: int
    filings_processed: int
    transactions_found: int
    transactions_written: int
    report_dir: Path


class InsiderMonitorPipeline:
    def __init__(self, tickers_path: Path, db_path: Path, reports_root: Path, sec_client: SecClient) -> None:
        self.tickers_path = tickers_path
        self.storage = Storage(db_path)
        self.reporter = Reporter(reports_root)
        self.sec_client = sec_client

    def run(self, days: int = 30, run_date: date | None = None) -> PipelineResult:
        run_date = run_date or date.today()
        since = rolling_window_start(days)
        self.storage.initialize()

        tickers = self._load_tickers()
        ticker_map = self.sec_client.load_ticker_map()
        transactions: list[InsiderTransaction] = []
        filings_processed = 0

        for ticker in tickers:
            company = ticker_map.get(ticker.upper())
            if not company:
                continue
            filings = self.sec_client.fetch_recent_form4_filings(ticker=ticker.upper(), cik=company["cik"], since=since)
            filings_processed += len(filings)
            for filing in filings:
                transactions.extend(self.sec_client.parse_transactions(filing, min_transaction_date=since))

        written = self.storage.upsert_transactions(transactions)
        report_dir = self.reporter.write_daily_report(run_date, tickers, transactions)
        return PipelineResult(
            tickers_processed=len(tickers),
            filings_processed=filings_processed,
            transactions_found=len(transactions),
            transactions_written=written,
            report_dir=report_dir,
        )

    def _load_tickers(self) -> list[str]:
        with self.tickers_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [row["ticker"].strip().upper() for row in reader if row.get("ticker", "").strip()]
