from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from html import escape
from pathlib import Path
from typing import Iterable

from .models import InsiderTransaction


class Reporter:
    def __init__(self, reports_root: Path) -> None:
        self.reports_root = reports_root

    def write_daily_report(
        self,
        run_date: date,
        configured_tickers: list[str],
        transactions: Iterable[InsiderTransaction],
    ) -> Path:
        transactions = sorted(transactions, key=lambda item: (item.ticker, item.transaction_date, item.insider_name))
        output_dir = self.reports_root / run_date.isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)

        self._write_csv(output_dir / "insider_transactions.csv", transactions)
        self._write_json(output_dir / "insider_transactions.json", transactions)
        self._write_markdown(output_dir / "summary.md", run_date, configured_tickers, transactions)
        self._write_html(output_dir / "report.html", run_date, configured_tickers, transactions)
        return output_dir

    def _write_csv(self, path: Path, transactions: list[InsiderTransaction]) -> None:
        fieldnames = list(asdict(transactions[0]).keys()) if transactions else [
            "transaction_id",
            "ticker",
            "issuer_name",
            "issuer_cik",
            "filing_accession",
            "filing_date",
            "transaction_date",
            "filing_form",
            "security_type",
            "security_title",
            "insider_name",
            "insider_cik",
            "relationship_is_director",
            "relationship_is_officer",
            "relationship_is_ten_percent_owner",
            "relationship_is_other",
            "officer_title",
            "transaction_code",
            "acquired_disposed_code",
            "share_count",
            "share_price_usd",
            "shares_owned_after",
            "shares_owned_before",
            "ownership_change_pct",
            "direct_or_indirect",
            "nature_of_ownership",
            "source_xml_url",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for transaction in transactions:
                writer.writerow(self._serialize(transaction))

    def _write_json(self, path: Path, transactions: list[InsiderTransaction]) -> None:
        payload = [self._serialize(transaction) for transaction in transactions]
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _write_markdown(
        self,
        path: Path,
        run_date: date,
        configured_tickers: list[str],
        transactions: list[InsiderTransaction],
    ) -> None:
        grouped: dict[str, list[InsiderTransaction]] = defaultdict(list)
        for transaction in transactions:
            grouped[transaction.ticker].append(transaction)

        summary_by_ticker = self._build_ticker_summary(configured_tickers, grouped)
        lines = [
            f"# Insider Transactions Summary - {run_date.isoformat()}",
            "",
            f"Transactions found in the last 30 days: {len(transactions)}",
            "",
            "## Legend",
            "",
            "- `Code` is the SEC transaction code. Common examples: `P` = open-market purchase, `S` = open-market sale, `M` = option exercise or derivative conversion, `A` = grant/award, `F` = tax withholding or payment with shares.",
            "- `A/D` means whether shares were acquired or disposed on that transaction row: `A` = acquired, `D` = disposed.",
            "- `Reported Date` is the transaction date shown in the Form 4 filing.",
            "- `Filing Date` is the date the Form 4 was filed with the SEC.",
            "",
            "## Ticker Overview",
            "",
            "| Ticker | Transactions | Insiders | Net Shares | Largest Ownership Move |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]

        for item in summary_by_ticker:
            largest_move = "" if item["largest_move_pct"] is None else f"{item['largest_move_pct']:.2f}%"
            net_shares = "" if item["net_shares"] is None else f"{item['net_shares']:,.2f}"
            lines.append(
                f"| {item['ticker']} | {item['transactions']} | {item['insiders']} | {net_shares} | {largest_move} |"
            )
        lines.append("")

        if not transactions:
            lines.append("No insider transactions were found for the configured tickers in the last 30 days.")
        else:
            for ticker in configured_tickers:
                lines.append(f"## {ticker}")
                ticker_transactions = sorted(grouped.get(ticker, []), key=lambda item: (item.transaction_date, item.insider_name))
                if not ticker_transactions:
                    lines.append("- No insider transactions found in the last 30 days.")
                    lines.append("")
                    continue

                ticker_summary = next(item for item in summary_by_ticker if item["ticker"] == ticker)
                lines.append(
                    f"Transactions: {ticker_summary['transactions']} | "
                    f"Unique insiders: {ticker_summary['insiders']} | "
                    f"Net shares: {ticker_summary['net_shares']:,.2f}"
                )
                lines.append("")
                lines.append(
                    "| Filing Date | Reported Date | Insider | Role | Code | A/D | Shares | Price | Transaction Value | Ownership Change | Security |"
                )
                lines.append("| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |")
                for txn in ticker_transactions:
                    share_count = "" if txn.share_count is None else f"{txn.share_count:,.2f}"
                    share_price = "" if txn.share_price_usd is None else f"${txn.share_price_usd:,.2f}"
                    transaction_value = self._transaction_value_label(txn)
                    pct = "" if txn.ownership_change_pct is None else f"{txn.ownership_change_pct:.2f}%"
                    lines.append(
                        f"| {txn.filing_date.isoformat()} | {txn.transaction_date.isoformat()} | {txn.insider_name} | "
                        f"{self._role_label(txn)} | {txn.transaction_code or ''} | {txn.acquired_disposed_code or ''} | "
                        f"{share_count} | {share_price} | {transaction_value} | {pct} | {txn.security_title} |"
                    )
                lines.append("")

        with path.open("w", encoding="utf-8") as handle:
            handle.write("\n".join(lines).rstrip() + "\n")

    def _write_html(
        self,
        path: Path,
        run_date: date,
        configured_tickers: list[str],
        transactions: list[InsiderTransaction],
    ) -> None:
        grouped: dict[str, list[InsiderTransaction]] = defaultdict(list)
        for transaction in transactions:
            grouped[transaction.ticker].append(transaction)

        summary_by_ticker = self._build_ticker_summary(configured_tickers, grouped)
        active_tickers = sum(1 for item in summary_by_ticker if item["transactions"] > 0)
        total_insiders = len({txn.insider_name for txn in transactions})

        cards_html = "".join(
            [
                self._metric_card("Tickers Monitored", str(len(configured_tickers))),
                self._metric_card("Active Tickers", str(active_tickers)),
                self._metric_card("Transactions", str(len(transactions))),
                self._metric_card("Unique Insiders", str(total_insiders)),
            ]
        )

        legend_html = "".join(
            [
                "<li><strong>Code</strong>: SEC transaction code. Common examples: "
                "<span class='badge'>P</span> purchase, <span class='badge'>S</span> sale, "
                "<span class='badge'>M</span> option exercise/conversion, <span class='badge'>A</span> grant/award, "
                "<span class='badge'>F</span> tax withholding or payment with shares.</li>",
                "<li><strong>A/D</strong>: <span class='badge'>A</span> acquired, <span class='badge'>D</span> disposed.</li>",
                "<li><strong>Reported Date</strong>: transaction date shown in the Form 4.</li>",
                "<li><strong>Filing Date</strong>: date the Form 4 was submitted to the SEC.</li>",
            ]
        )

        overview_rows = "".join(
            [
                "<tr>"
                f"<td>{escape(item['ticker'])}</td>"
                f"<td>{item['transactions']}</td>"
                f"<td>{item['insiders']}</td>"
                f"<td>{'' if item['net_shares'] is None else format(item['net_shares'], ',.2f')}</td>"
                f"<td>{'' if item['largest_move_pct'] is None else format(item['largest_move_pct'], '.2f') + '%'}</td>"
                "</td></tr>"
                for item in summary_by_ticker
            ]
        )

        sections_html = []
        for ticker in configured_tickers:
            ticker_transactions = sorted(grouped.get(ticker, []), key=lambda item: (item.transaction_date, item.insider_name))
            ticker_summary = next(item for item in summary_by_ticker if item["ticker"] == ticker)
            if not ticker_transactions:
                section = (
                    f"<section class='ticker-section'>"
                    f"<div class='section-header'><h2>{escape(ticker)}</h2><span class='badge quiet'>No activity</span></div>"
                    "<p class='empty'>No insider transactions found in the last 30 days.</p>"
                    "</section>"
                )
                sections_html.append(section)
                continue

            rows = []
            for txn in ticker_transactions:
                rows.append(
                    "<tr>"
                    f"<td>{txn.filing_date.isoformat()}</td>"
                    f"<td>{txn.transaction_date.isoformat()}</td>"
                    f"<td>{escape(txn.insider_name)}</td>"
                    f"<td>{escape(self._role_label(txn))}</td>"
                    f"<td><span class='badge'>{escape(txn.transaction_code or '')}</span></td>"
                    f"<td>{escape(txn.acquired_disposed_code or '')}</td>"
                    f"<td>{'' if txn.share_count is None else f'{txn.share_count:,.2f}'}</td>"
                    f"<td>{'' if txn.share_price_usd is None else f'${txn.share_price_usd:,.2f}'}</td>"
                    f"<td>{self._transaction_value_label(txn)}</td>"
                    f"<td class='{self._pct_class(txn.ownership_change_pct)}'>"
                    f"{'' if txn.ownership_change_pct is None else f'{txn.ownership_change_pct:.2f}%'}"
                    "</td>"
                    f"<td>{escape(txn.security_title)}</td>"
                    "</tr>"
                )

            section = (
                "<section class='ticker-section'>"
                f"<div class='section-header'><h2>{escape(ticker)}</h2>"
                f"<span class='badge strong'>{ticker_summary['transactions']} transactions</span></div>"
                "<div class='ticker-meta'>"
                f"<span>Unique insiders: {ticker_summary['insiders']}</span>"
                f"<span>Net shares: {ticker_summary['net_shares']:,.2f}</span>"
                f"<span>Largest move: {'' if ticker_summary['largest_move_pct'] is None else format(ticker_summary['largest_move_pct'], '.2f') + '%'}"
                "</span></div>"
                "<table><thead><tr>"
                "<th>Filing Date</th><th>Reported Date</th><th>Insider</th><th>Role</th><th>Code</th><th>A/D</th>"
                "<th>Shares</th><th>Price</th><th>Transaction Value</th><th>Ownership Change</th><th>Security</th>"
                "</tr></thead><tbody>"
                + "".join(rows)
                + "</tbody></table></section>"
            )
            sections_html.append(section)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Insider Transactions by Hadi Saade - {run_date.isoformat()}</title>
  <style>
    :root {{
      --ink: #15202b;
      --muted: #5d6b78;
      --line: #d6dee5;
      --bg: #f3f7fb;
      --card: #ffffff;
      --accent: #0f766e;
      --accent-soft: #d9f3ef;
      --warn: #a16207;
      --pos: #166534;
      --neg: #991b1b;
      --shadow: 0 18px 40px rgba(21, 32, 43, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(15, 118, 110, 0.10), transparent 30%),
        linear-gradient(180deg, #fbfdff 0%, var(--bg) 100%);
    }}
    .wrap {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0 56px;
    }}
    .hero {{
      background: linear-gradient(135deg, #fcfffe 0%, #e6f4f1 100%);
      border: 1px solid rgba(15, 118, 110, 0.16);
      border-radius: 28px;
      padding: 32px;
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font: 600 12px/1.2 "Avenir Next", "Segoe UI", sans-serif;
      color: var(--accent);
      margin-bottom: 12px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(34px, 5vw, 56px);
      line-height: 0.95;
    }}
    .hero p {{
      margin: 0;
      max-width: 760px;
      font-size: 18px;
      line-height: 1.5;
      color: var(--muted);
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin: 28px 0 22px;
    }}
    .metric {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 18px 18px 16px;
      box-shadow: var(--shadow);
    }}
    .metric-label {{
      display: block;
      font: 600 12px/1.2 "Avenir Next", "Segoe UI", sans-serif;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .metric-value {{
      font-size: 34px;
      line-height: 1;
    }}
    .panel {{
      margin-top: 24px;
      background: rgba(255, 255, 255, 0.86);
      border: 1px solid rgba(214, 222, 229, 0.9);
      border-radius: 24px;
      padding: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .panel h2 {{
      margin: 0 0 14px;
      font-size: 28px;
    }}
    .legend {{
      margin: 0;
      padding-left: 18px;
      font: 500 15px/1.6 "Avenir Next", "Segoe UI", sans-serif;
      color: var(--muted);
    }}
    .legend li {{
      margin-bottom: 10px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      font-size: 14px;
      background: var(--card);
      border-radius: 18px;
      overflow: hidden;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
    }}
    th {{
      background: #edf6f5;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    tr:last-child td {{ border-bottom: none; }}
    .ticker-section {{
      margin-top: 24px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(214, 222, 229, 0.9);
      border-radius: 24px;
      padding: 24px;
      box-shadow: var(--shadow);
    }}
    .section-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .section-header h2 {{
      margin: 0;
      font-size: 30px;
    }}
    .ticker-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 16px;
      font: 500 14px/1.4 "Avenir Next", "Segoe UI", sans-serif;
      color: var(--muted);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 34px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #eef3f7;
      font: 700 12px/1 "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
    }}
    .badge.strong {{
      background: var(--accent-soft);
      color: var(--accent);
    }}
    .badge.quiet {{
      background: #f6efe0;
      color: var(--warn);
    }}
    .empty {{
      margin: 0;
      color: var(--muted);
      font: 500 15px/1.5 "Avenir Next", "Segoe UI", sans-serif;
    }}
    .pct-pos {{ color: var(--pos); font-weight: 700; }}
    .pct-neg {{ color: var(--neg); font-weight: 700; }}
    .pct-flat {{ color: var(--muted); }}
    .footer {{
      margin-top: 20px;
      color: var(--muted);
      font: 500 13px/1.5 "Avenir Next", "Segoe UI", sans-serif;
    }}
    @media (max-width: 860px) {{
      .wrap {{ width: min(100% - 20px, 1180px); padding-top: 20px; }}
      .hero, .panel, .ticker-section {{ padding: 18px; border-radius: 18px; }}
      th, td {{ padding: 10px 8px; font-size: 13px; }}
      .section-header {{ align-items: flex-start; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="eyebrow">Daily Insider Monitor</div>
      <h1>Insider Transactions by Hadi Saade</h1>
      <p>Rolling 30-day Form 4 activity for the configured US stock watchlist, including insider roles, transaction codes, share counts, and estimated ownership change percentages.</p>
    </section>
    <section class="metrics">{cards_html}</section>
    <section class="panel">
      <h2>Legend</h2>
      <ul class="legend">{legend_html}</ul>
    </section>
    <section class="panel">
      <h2>Ticker Overview</h2>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Transactions</th>
            <th>Insiders</th>
            <th>Net Shares</th>
            <th>Largest Ownership Move</th>
          </tr>
        </thead>
        <tbody>{overview_rows}</tbody>
      </table>
    </section>
    {''.join(sections_html)}
    <p class="footer">Generated from SEC EDGAR Form 4 filings. Ownership change percentages are estimated from transaction shares and post-transaction holdings reported on each transaction row.</p>
  </main>
</body>
</html>
"""
        with path.open("w", encoding="utf-8") as handle:
            handle.write(html)

    @staticmethod
    def _serialize(transaction: InsiderTransaction) -> dict:
        payload = asdict(transaction)
        payload["filing_date"] = transaction.filing_date.isoformat()
        payload["transaction_date"] = transaction.transaction_date.isoformat()
        return payload

    @staticmethod
    def _role_label(transaction: InsiderTransaction) -> str:
        roles = []
        if transaction.relationship_is_director:
            roles.append("Director")
        if transaction.relationship_is_officer:
            roles.append("Officer")
        if transaction.relationship_is_ten_percent_owner:
            roles.append("10% Owner")
        if transaction.relationship_is_other:
            roles.append("Other")
        if not roles:
            return "Unspecified"
        return ", ".join(roles)

    def _build_ticker_summary(
        self,
        configured_tickers: list[str],
        grouped: dict[str, list[InsiderTransaction]],
    ) -> list[dict]:
        summary: list[dict] = []
        for ticker in configured_tickers:
            ticker_transactions = grouped.get(ticker, [])
            signed_shares = [
                self._signed_share_value(txn)
                for txn in ticker_transactions
                if self._signed_share_value(txn) is not None
            ]
            ownership_moves = [
                abs(txn.ownership_change_pct)
                for txn in ticker_transactions
                if txn.ownership_change_pct is not None
            ]
            summary.append(
                {
                    "ticker": ticker,
                    "transactions": len(ticker_transactions),
                    "insiders": len({txn.insider_name for txn in ticker_transactions}),
                    "net_shares": sum(signed_shares) if signed_shares else 0.0,
                    "largest_move_pct": max(ownership_moves) if ownership_moves else None,
                }
            )
        return summary

    @staticmethod
    def _signed_share_value(transaction: InsiderTransaction) -> float | None:
        if transaction.share_count is None:
            return None
        if transaction.acquired_disposed_code == "A":
            return transaction.share_count
        if transaction.acquired_disposed_code == "D":
            return -transaction.share_count
        return None

    @staticmethod
    def _metric_card(label: str, value: str) -> str:
        return (
            "<article class='metric'>"
            f"<span class='metric-label'>{escape(label)}</span>"
            f"<div class='metric-value'>{escape(value)}</div>"
            "</article>"
        )

    @staticmethod
    def _pct_class(value: float | None) -> str:
        if value is None:
            return "pct-flat"
        if value > 0:
            return "pct-pos"
        if value < 0:
            return "pct-neg"
        return "pct-flat"

    @staticmethod
    def _transaction_value_label(transaction: InsiderTransaction) -> str:
        if transaction.share_count is None or transaction.share_price_usd is None:
            return ""
        return f"${transaction.share_count * transaction.share_price_usd:,.2f}"
