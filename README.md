# Insider Transaction Monitoring System

A repeatable daily pipeline that monitors **SEC insider transactions** (Form 4 / 4&#47;A)
for a dynamic watchlist of U.S. stocks and produces a clean daily report in
CSV, JSON, Markdown, and HTML.

It is designed as a monitoring *product* — useful for a hedge-fund-style workflow
to detect insider accumulation, insider selling, and unusually large ownership
changes across a custom watchlist — rather than a one-off data pull.

```
Ticker List → SEC Filings → Transaction Extraction → Ownership Change Calculation → Daily Report
```

## How it works

The SEC organizes filings by company identifier (CIK), not ticker, so each ticker
is first mapped to its CIK. The pipeline then:

1. Reads the ticker list (`config/tickers.csv`)
2. Maps each ticker to its SEC CIK
3. Retrieves recent Form 4 / 4&#47;A filings from SEC EDGAR
4. Parses each XML ownership document
5. Extracts transaction-level rows (insider, dates, code, direction, shares, price, post-transaction holdings)
6. Calculates transaction value and ownership change
7. Stores results in a local SQLite database
8. Generates CSV, JSON, Markdown, and HTML reports

## Key metrics

SEC transaction codes are preserved as filed. Common examples:

| Code | Meaning |
| --- | --- |
| `P` | Open-market purchase |
| `S` | Open-market sale |
| `M` | Option exercise or conversion |
| `A` | Grant or award |
| `F` | Tax-related withholding using shares |

`A/D` indicates whether shares were **A**cquired or **D**isposed on a transaction row.

**Transaction value:** `V = q × p` where `q` is transaction shares and `p` is price per share.

**Ownership change** (estimated from reported post-transaction holdings):

```
H_before = H_after − q_signed
Δ%       = (q_signed / H_before) × 100
```

## Requirements

- Python 3.11+
- Internet access (queries the live SEC EDGAR API)

## Usage

```bash
# SEC requires a descriptive User-Agent with contact info
export SEC_USER_AGENT="Your Name your.email@example.com"

# Run the daily pipeline
python3 -m src.insider_monitor.cli run

# Optional flags
python3 -m src.insider_monitor.cli run --days 30 \
    --tickers config/tickers.csv \
    --db data/insider_transactions.db \
    --reports-dir reports
```

Outputs land in `reports/<YYYY-MM-DD>/` as `insider_transactions.csv`,
`insider_transactions.json`, `summary.md`, and `report.html`.

Open the presentation-style HTML report:

```bash
open reports/$(date +%F)/report.html      # macOS
```

## Configuration

Change the stock universe by editing `config/tickers.csv`:

```csv
ticker
AAPL
HON
GEV
BEPC
```

## Project layout

```
config/tickers.csv            # watchlist
src/insider_monitor/
  cli.py                      # command-line entry point
  pipeline.py                 # orchestration
  sec_client.py               # SEC EDGAR fetching + XML parsing
  storage.py                  # SQLite persistence
  reporter.py                 # CSV / JSON / Markdown / HTML output
  models.py                   # data models
```

## Notes

- Ownership-change percentages are estimated from transaction shares and the
  post-transaction holdings reported on each row.
- Be a good SEC citizen: requests are rate-limited and identified via
  `SEC_USER_AGENT`. See the SEC's
  [fair-access policy](https://www.sec.gov/os/webmaster-faq#developers).
