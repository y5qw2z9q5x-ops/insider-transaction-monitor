from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from .models import FilingMetadata, InsiderTransaction


SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


class SecClient:
    def __init__(self, user_agent: Optional[str] = None, pause_seconds: float = 0.2) -> None:
        self.user_agent = user_agent or os.getenv(
            "SEC_USER_AGENT",
            "InsiderTransactionMonitor/1.0 contact=case-study@example.com",
        )
        self.pause_seconds = pause_seconds

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            time.sleep(self.pause_seconds)
            return json.loads(response.read().decode("utf-8"))

    def _get_text(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=30) as response:
            time.sleep(self.pause_seconds)
            return response.read().decode("utf-8")

    def load_ticker_map(self) -> dict[str, dict]:
        data = self._get_json(SEC_TICKER_URL)
        mapping: dict[str, dict] = {}
        for item in data.values():
            ticker = item["ticker"].upper()
            mapping[ticker] = {
                "ticker": ticker,
                "title": item["title"],
                "cik": str(item["cik_str"]).zfill(10),
            }
        return mapping

    def fetch_recent_form4_filings(self, ticker: str, cik: str, since: date) -> list[FilingMetadata]:
        submission = self._get_json(SEC_SUBMISSIONS_URL.format(cik=cik))
        issuer_name = submission.get("name", ticker)
        filings = submission.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        accession_numbers = filings.get("accessionNumber", [])
        filing_dates = filings.get("filingDate", [])
        primary_documents = filings.get("primaryDocument", [])

        results: list[FilingMetadata] = []
        for idx, form in enumerate(forms):
            if form not in {"4", "4/A"}:
                continue
            filing_date = datetime.strptime(filing_dates[idx], "%Y-%m-%d").date()
            if filing_date < since:
                continue
            accession_number = accession_numbers[idx]
            accession_nodash = accession_number.replace("-", "")
            cik_nozero = str(int(cik))
            archive_dir = f"{SEC_ARCHIVES_BASE}/{cik_nozero}/{accession_nodash}"
            index_url = f"{archive_dir}/index.json"
            filing_detail_url = f"{archive_dir}/{primary_documents[idx]}"
            xml_url = self._discover_ownership_xml(index_url)
            if not xml_url:
                continue
            results.append(
                FilingMetadata(
                    ticker=ticker,
                    issuer_name=issuer_name,
                    issuer_cik=cik,
                    accession_number=accession_number,
                    filing_date=filing_date,
                    form=form,
                    archive_index_url=index_url,
                    filing_detail_url=filing_detail_url,
                    xml_url=xml_url,
                )
            )
        return results

    def _discover_ownership_xml(self, index_url: str) -> Optional[str]:
        try:
            index_data = self._get_json(index_url)
        except urllib.error.HTTPError:
            return None

        items = index_data.get("directory", {}).get("item", [])
        for item in items:
            name = item.get("name", "")
            if not name.lower().endswith(".xml"):
                continue
            file_url = index_url.rsplit("/", 1)[0] + "/" + name
            try:
                text = self._get_text(file_url)
            except urllib.error.HTTPError:
                continue
            if "<ownershipDocument>" in text:
                return file_url
        return None

    def parse_transactions(self, filing: FilingMetadata, min_transaction_date: date) -> list[InsiderTransaction]:
        xml_text = self._get_text(filing.xml_url)
        root = ET.fromstring(xml_text)

        reporting_owner = root.find("reportingOwner")
        owner_id = self._text(reporting_owner, "reportingOwnerId/rptOwnerName")
        owner_cik = self._text(reporting_owner, "reportingOwnerId/rptOwnerCik")
        relationship = reporting_owner.find("reportingOwnerRelationship") if reporting_owner is not None else None

        transactions: list[InsiderTransaction] = []
        row_index = 0

        for security_type, container_tag, row_tag in (
            ("non-derivative", "nonDerivativeTable", "nonDerivativeTransaction"),
            ("derivative", "derivativeTable", "derivativeTransaction"),
        ):
            container = root.find(container_tag)
            if container is None:
                continue
            for row in container.findall(row_tag):
                transaction_date_str = self._text(row, "transactionDate/value")
                if not transaction_date_str:
                    continue
                transaction_date = datetime.strptime(transaction_date_str, "%Y-%m-%d").date()
                if transaction_date < min_transaction_date:
                    continue

                share_count = self._float(row, "transactionAmounts/transactionShares/value")
                share_price = self._float(row, "transactionAmounts/transactionPricePerShare/value")
                shares_after = self._float(row, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
                acquired_disposed = self._text(row, "transactionAmounts/transactionAcquiredDisposedCode/value")
                signed_shares = self._signed_shares(share_count, acquired_disposed)
                shares_before = None
                ownership_change_pct = None
                if signed_shares is not None and shares_after is not None:
                    shares_before = shares_after - signed_shares
                    if shares_before not in (None, 0):
                        ownership_change_pct = (signed_shares / shares_before) * 100

                transaction_code = self._text(row, "transactionCoding/transactionCode")
                security_title = self._text(row, "securityTitle/value") or ""
                direct_indirect = self._text(row, "ownershipNature/directOrIndirectOwnership/value")
                nature = self._text(row, "ownershipNature/natureOfOwnership/value")

                transaction_id = "|".join(
                    [
                        filing.accession_number,
                        security_type,
                        transaction_date.isoformat(),
                        transaction_code or "",
                        str(row_index),
                    ]
                )

                transactions.append(
                    InsiderTransaction(
                        transaction_id=transaction_id,
                        ticker=filing.ticker,
                        issuer_name=filing.issuer_name,
                        issuer_cik=filing.issuer_cik,
                        filing_accession=filing.accession_number,
                        filing_date=filing.filing_date,
                        transaction_date=transaction_date,
                        filing_form=filing.form,
                        security_type=security_type,
                        security_title=security_title,
                        insider_name=owner_id or "Unknown",
                        insider_cik=owner_cik,
                        relationship_is_director=self._bool_flag(relationship, "isDirector"),
                        relationship_is_officer=self._bool_flag(relationship, "isOfficer"),
                        relationship_is_ten_percent_owner=self._bool_flag(relationship, "isTenPercentOwner"),
                        relationship_is_other=self._bool_flag(relationship, "isOther"),
                        officer_title=self._text(relationship, "officerTitle"),
                        transaction_code=transaction_code,
                        acquired_disposed_code=acquired_disposed,
                        share_count=share_count,
                        share_price_usd=share_price,
                        shares_owned_after=shares_after,
                        shares_owned_before=shares_before,
                        ownership_change_pct=ownership_change_pct,
                        direct_or_indirect=direct_indirect,
                        nature_of_ownership=nature,
                        source_xml_url=filing.xml_url,
                    )
                )
                row_index += 1

        return transactions

    @staticmethod
    def _text(node: Optional[ET.Element], path: str) -> Optional[str]:
        if node is None:
            return None
        found = node.find(path)
        if found is None or found.text is None:
            return None
        value = found.text.strip()
        return value or None

    @staticmethod
    def _float(node: Optional[ET.Element], path: str) -> Optional[float]:
        value = SecClient._text(node, path)
        if value is None:
            return None
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _bool_flag(node: Optional[ET.Element], path: str) -> bool:
        value = SecClient._text(node, path)
        return value == "1" or (value or "").lower() == "true"

    @staticmethod
    def _signed_shares(share_count: Optional[float], acquired_disposed: Optional[str]) -> Optional[float]:
        if share_count is None or not acquired_disposed:
            return None
        if acquired_disposed == "A":
            return share_count
        if acquired_disposed == "D":
            return -share_count
        return None


def rolling_window_start(days: int) -> date:
    return date.today() - timedelta(days=days)
