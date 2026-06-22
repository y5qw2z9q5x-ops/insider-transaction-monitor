from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class FilingMetadata:
    ticker: str
    issuer_name: str
    issuer_cik: str
    accession_number: str
    filing_date: date
    form: str
    archive_index_url: str
    filing_detail_url: str
    xml_url: str


@dataclass(frozen=True)
class InsiderTransaction:
    transaction_id: str
    ticker: str
    issuer_name: str
    issuer_cik: str
    filing_accession: str
    filing_date: date
    transaction_date: date
    filing_form: str
    security_type: str
    security_title: str
    insider_name: str
    insider_cik: Optional[str]
    relationship_is_director: bool
    relationship_is_officer: bool
    relationship_is_ten_percent_owner: bool
    relationship_is_other: bool
    officer_title: Optional[str]
    transaction_code: Optional[str]
    acquired_disposed_code: Optional[str]
    share_count: Optional[float]
    share_price_usd: Optional[float]
    shares_owned_after: Optional[float]
    shares_owned_before: Optional[float]
    ownership_change_pct: Optional[float]
    direct_or_indirect: Optional[str]
    nature_of_ownership: Optional[str]
    source_xml_url: str
