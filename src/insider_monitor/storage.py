from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .models import InsiderTransaction


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS insider_transactions (
    transaction_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    issuer_cik TEXT NOT NULL,
    filing_accession TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    filing_form TEXT NOT NULL,
    security_type TEXT NOT NULL,
    security_title TEXT NOT NULL,
    insider_name TEXT NOT NULL,
    insider_cik TEXT,
    relationship_is_director INTEGER NOT NULL,
    relationship_is_officer INTEGER NOT NULL,
    relationship_is_ten_percent_owner INTEGER NOT NULL,
    relationship_is_other INTEGER NOT NULL,
    officer_title TEXT,
    transaction_code TEXT,
    acquired_disposed_code TEXT,
    share_count REAL,
    share_price_usd REAL,
    shares_owned_after REAL,
    shares_owned_before REAL,
    ownership_change_pct REAL,
    direct_or_indirect TEXT,
    nature_of_ownership TEXT,
    source_xml_url TEXT NOT NULL,
    inserted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    def upsert_transactions(self, transactions: Iterable[InsiderTransaction]) -> int:
        rows = [self._as_row(txn) for txn in transactions]
        if not rows:
            return 0
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO insider_transactions (
                    transaction_id, ticker, issuer_name, issuer_cik, filing_accession, filing_date,
                    transaction_date, filing_form, security_type, security_title, insider_name,
                    insider_cik, relationship_is_director, relationship_is_officer,
                    relationship_is_ten_percent_owner, relationship_is_other, officer_title,
                    transaction_code, acquired_disposed_code, share_count, share_price_usd,
                    shares_owned_after, shares_owned_before, ownership_change_pct,
                    direct_or_indirect, nature_of_ownership, source_xml_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    @staticmethod
    def _as_row(txn: InsiderTransaction) -> tuple:
        return (
            txn.transaction_id,
            txn.ticker,
            txn.issuer_name,
            txn.issuer_cik,
            txn.filing_accession,
            txn.filing_date.isoformat(),
            txn.transaction_date.isoformat(),
            txn.filing_form,
            txn.security_type,
            txn.security_title,
            txn.insider_name,
            txn.insider_cik,
            int(txn.relationship_is_director),
            int(txn.relationship_is_officer),
            int(txn.relationship_is_ten_percent_owner),
            int(txn.relationship_is_other),
            txn.officer_title,
            txn.transaction_code,
            txn.acquired_disposed_code,
            txn.share_count,
            txn.share_price_usd,
            txn.shares_owned_after,
            txn.shares_owned_before,
            txn.ownership_change_pct,
            txn.direct_or_indirect,
            txn.nature_of_ownership,
            txn.source_xml_url,
        )
