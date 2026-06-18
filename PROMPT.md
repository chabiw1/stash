# Wealth Dashboard — Build Prompt for Claude Code

## What you need to build

A personal wealth dashboard that:
1. Pulls financial data from 4 sources automatically
2. Generates a single `index.html` dashboard
3. Deploys to GitHub Pages via GitHub Actions (free hosting)
4. Updates every 2 hours automatically

---

## Repository structure to create

```
wealth-dashboard/
├── .github/workflows/
│   ├── daily.yml        # runs 08:00 Bangkok time every day
│   └── realtime.yml     # runs every 2 hours
├── src/
│   ├── fetch_dime.py
│   ├── fetch_prices.py
│   ├── fetch_kbank.py
│   ├── fetch_btc_onchain.py
│   └── build_html.py
├── data/
│   ├── portfolio.json   # cached dime holdings (committed)
│   └── history.json     # wealth snapshots over time (committed)
├── index.html           # auto-generated, committed by Actions
└── requirements.txt
```

---

## Source 1 — Dime (US Stocks + ETF)

Reuse this exact working code. Do not rewrite the logic, just refactor into `src/fetch_dime.py`:

### Gmail + PDF helpers (keep as-is)

```python
def get_email_body(msg): ...
def fetch_gmail_by_subject(subject_keyword): ...
def decrypt_pdf(pdf_data, dob): ...
def extract_pdf_text(pdf_data, dob): ...
def get_pdf_from_msg(msg): ...
```

### Monthly Statement parser (keep as-is)

```python
def parse_statement_month(subject): ...
def parse_monthly_statement(text): ...  # returns list of {symbol, shares, avg_cost_usd}
def get_last_month_statement(): ...     # returns (holdings, cutoff_date)
```

**One change needed:** After parsing holdings, detect asset_type per symbol by looking at which section header appears before each row in the PDF text:
- Section header containing `หุ้นสามัญ` or `Common Stock` → all rows until next header = `"stock"`
- Section header containing `กองทุน ETF` or `ETF` → all rows until next header = `"etf"`

Also parse Cash Balance USD from summary: regex `r'Cash Balance\s*[\d,]+\s*USD\s*([\d,]+\.\d+)\s*USD'` or similar — check the actual PDF text.

Updated return from `get_last_month_statement()`:
```python
{
  "statement_date": "2025-08-29",        # last day of statement month
  "dime_cash_usd": 781.59,               # cash in Dime account
  "holdings": {
    "TSLA": {"shares": 0.5164601, "avg_cost_usd": 290.40, "asset_type": "stock"},
    "SPY":  {"shares": 0.2374877, "avg_cost_usd": 631.27, "asset_type": "etf"},
    "BIL":  {"shares": 3.2653812, "avg_cost_usd": 91.73,  "asset_type": "etf"},
  }
}
```

### Confirmation Note parser (keep as-is)

```python
def parse_confirmation_note(text): ...  # returns list of trades
def get_this_month_trades(cutoff_date): ...
```

### Portfolio merge (keep as-is)

```python
def merge_portfolio(holdings, new_trades): ...
# BUY → weighted average cost
# SEL → subtract shares, delete if <= 0
# Returns dict: symbol → {shares, avg_cost_usd, asset_type}
```

For symbols appearing in Confirmation Notes but not in Monthly Statement, classify asset_type via:
```python
info = yf.Ticker(symbol).fast_info
asset_type = "etf" if getattr(info, "quote_type", "").upper() == "ETF" else "stock"
```

### Daily job logic in fetch_dime.py

```python
def run_daily(portfolio_path):
    data = load_json(portfolio_path)
    current_month_end = last_day_of_current_month()

    # Check if we already have this month's statement
    if data.get("statement_date") != str(current_month_end):
        holdings_data = get_last_month_statement()
        if holdings_data:
            data.update(holdings_data)
            save_json(portfolio_path, data)

    # Always check for new confirmation notes
    cutoff = date.fromisoformat(data["statement_date"])
    new_trades = get_this_month_trades(cutoff)
    if new_trades:
        merged = merge_portfolio(
            list(data["holdings"].values()),
            new_trades
        )
        data["holdings"] = merged
        save_json(portfolio_path, data)
```

---

## Source 2 — Binance TH (Crypto quantities)

Reuse this exact working code in `src/fetch_prices.py`:

```python
import time, hmac, hashlib, requests

BASE_URL = "https://api.binance.th"  # NOTE: .th not .com

def get_binance_balances(api_key, secret_key):
    timestamp = int(time.time() * 1000)
    params = f"timestamp={timestamp}"
    signature = hmac.new(secret_key.encode(), params.encode(), hashlib.sha256).hexdigest()
    url = f"{BASE_URL}/api/v1/account?{params}&signature={signature}"
    headers = {"X-MBX-APIKEY": api_key}
    r = requests.get(url, headers=headers)
    balances = r.json()["balances"]
    return {
        b["asset"]: float(b["free"]) + float(b["locked"])
        for b in balances
        if float(b["free"]) + float(b["locked"]) > 0
    }
    # returns e.g. {"BTC": 0.030, "ETH": 1.82, "USDT": 3600}
```

Also use Binance TH to get crypto prices in THB:
```python
def get_binance_price_thb(api_key, secret_key, symbol):
    # symbol e.g. "BTCTHB", "ETHTHB", "USDTTHB"
    url = f"{BASE_URL}/api/v1/ticker/price?symbol={symbol}"
    headers = {"X-MBX-APIKEY": api_key}
    r = requests.get(url, headers=headers)
    return float(r.json()["price"])

def get_usd_thb_rate(api_key, secret_key):
    return get_binance_price_thb(api_key, secret_key, "USDTTHB")
```

---

## Source 3 — HW Wallet / Trezor (BTC on-chain)

Reuse this exact working code in `src/fetch_btc_onchain.py`:

```python
import requests

def get_btc_balance(address):
    url = f"https://blockchain.info/balance?active={address}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        balance_sat = data[address]['final_balance']
        return balance_sat / 100_000_000  # satoshi → BTC
    return None
```

---

## Source 4 — KBank (Cash THB)

Reuse this exact working code in `src/fetch_kbank.py`:

```python
import imaplib, email, re

def get_kbank_balance(gmail_user, gmail_pass):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(gmail_user, gmail_pass)
    mail.select('inbox')
    _, data = mail.search(None, 'FROM "KPLUS@kasikornbank.com"')
    ids = data[0].split()
    if not ids:
        return None
    _, msg_data = mail.fetch(ids[-1], '(RFC822)')
    msg = email.message_from_bytes(msg_data[0][1])
    body = get_body(msg)
    mail.logout()

    match = re.search(r'Available Balance\s*\(THB\)\s*:\s*([\d,]+\.\d{2})', body)
    if match:
        return float(match.group(1).replace(',', ''))
    return None
```

---

## Prices

In `src/fetch_prices.py`, fetch prices for Dime holdings via yfinance:

```python
import yfinance as yf

def get_stock_prices(symbols):
    # symbols = list of stock/ETF tickers e.g. ["TSLA", "SPY", "BIL"]
    prices = {}
    for sym in symbols:
        try:
            prices[sym] = yf.Ticker(sym).fast_info.last_price
        except Exception:
            prices[sym] = None
    return prices  # USD prices
```

For crypto prices, use Binance TH API (not yfinance).
USD → THB conversion: use `get_usd_thb_rate()` from Binance TH.

---

## data/portfolio.json schema

```json
{
  "statement_date": "2025-08-29",
  "dime_cash_usd": 781.59,
  "last_updated_dime": "2025-09-03T08:00:00+07:00",
  "holdings": {
    "TSLA": {"shares": 0.5164601, "avg_cost_usd": 290.40, "asset_type": "stock"},
    "SPY":  {"shares": 0.2374877, "avg_cost_usd": 631.27, "asset_type": "etf"},
    "BIL":  {"shares": 3.2653812, "avg_cost_usd": 91.73,  "asset_type": "etf"}
  }
}
```

---

## data/history.json schema

Append one entry every time `build_html.py` runs:

```json
[
  {
    "ts": "2025-09-03T10:00:00+07:00",
    "total_thb": 3842150,
    "cash_thb": 420000,
    "stocks_thb": 900150,
    "etf_thb": 432000,
    "crypto_thb": 2090000,
    "usd_thb_rate": 35.72
  }
]
```

---

## build_html.py

Reads `portfolio.json`, fetches live prices, appends to `history.json`, then generates `index.html`.

```python
def build():
    portfolio = load_json("data/portfolio.json")
    history   = load_json("data/history.json")

    # fetch live data
    binance_balances = get_binance_balances(...)   # coin quantities
    btc_hw           = get_btc_balance(BTC_ADDRESS)
    kbank_thb        = get_kbank_balance(...)
    usd_thb          = get_usd_thb_rate(...)
    stock_prices_usd = get_stock_prices(list(portfolio["holdings"].keys()))

    # crypto prices from Binance TH
    crypto_prices_thb = {}
    for coin in binance_balances:
        try:
            crypto_prices_thb[coin] = get_binance_price_thb(..., f"{coin}THB")
        except:
            crypto_prices_thb[coin] = None

    # aggregate by asset class
    cash_thb   = kbank_thb + portfolio["dime_cash_usd"] * usd_thb
    stocks_thb = sum(
        h["shares"] * (stock_prices_usd.get(sym) or 0) * usd_thb
        for sym, h in portfolio["holdings"].items()
        if h["asset_type"] == "stock"
    )
    etf_thb = sum(
        h["shares"] * (stock_prices_usd.get(sym) or 0) * usd_thb
        for sym, h in portfolio["holdings"].items()
        if h["asset_type"] == "etf"
    )

    # crypto: combine Binance + HW wallet BTC
    btc_total = binance_balances.get("BTC", 0) + (btc_hw or 0)
    binance_balances_merged = {**binance_balances, "BTC": btc_total}
    crypto_thb = sum(
        qty * (crypto_prices_thb.get(coin) or 0)
        for coin, qty in binance_balances_merged.items()
    )

    total_thb = cash_thb + stocks_thb + etf_thb + crypto_thb

    # append to history
    history.append({
        "ts": now_bangkok_iso(),
        "total_thb": round(total_thb),
        "cash_thb":   round(cash_thb),
        "stocks_thb": round(stocks_thb),
        "etf_thb":    round(etf_thb),
        "crypto_thb": round(crypto_thb),
        "usd_thb_rate": round(usd_thb, 4),
    })
    save_json("data/history.json", history)

    # generate index.html (see Dashboard UI section below)
    html = generate_html(...)
    with open("index.html", "w") as f:
        f.write(html)
```

---

## Dashboard UI (index.html)

Single-file HTML. No frameworks. Embedded CSS + JS. Must work without a server.

### Layout top to bottom:

**1. Header**
- Title "Wealth dashboard"
- Last updated timestamp
- Green badge if updated < 6 hours ago, red "stale" if older

**2. Total wealth card**
- Large: `฿3,842,150`
- Beside it: `$107,560`
- YTD % badge with up/down icon (green/red)
- Note: `1 USD = 35.72 THB`

**3. Asset class cards — 4 columns**

| Card | Color dot | Shows |
|---|---|---|
| Cash | #1D9E75 teal | THB amount + USD amount |
| US Stocks | #534AB7 purple | THB amount + USD amount |
| ETF | #D4537E pink | THB amount + USD amount |
| Crypto | #EF9F27 amber | THB amount + USD amount |

No source label on card face.

**Hover tooltip on each card:**
- Cash → `KBank ฿X` + `Dime USD $Y`
- US Stocks → `Dime ฿X`
- ETF → `Dime ฿X`
- Crypto → `Binance TH ฿X (XX%)` / `HW Wallet ฿Y (YY%)` / `BTC total: Z BTC`

**4. Dime holdings table**

Columns: Symbol | Class badge (Stock/ETF) | Shares | Price USD | Value USD | PnL %

- PnL % = `(current_price - avg_cost) / avg_cost * 100`
- Green if positive, red if negative
- Sort by value descending

**5. Crypto table**

Columns: Coin | Binance qty | HW qty | Total qty | Price THB | Value THB

- BTC row shows both sources
- Other coins show `—` in HW column

**6. Wealth history chart**

Use Chart.js from CDN. Line chart:
- Left y-axis: total THB
- Right y-axis: growth % (relative to first data point in range)
- Toggle buttons: 1M / 3M / 6M
- Data comes from `history.json` embedded as JS variable in HTML

---

## GitHub Actions

### .github/workflows/daily.yml

```yaml
name: Daily fetch
on:
  schedule:
    - cron: '0 1 * * *'   # 08:00 Bangkok (UTC+7)
  workflow_dispatch:

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python src/fetch_dime.py
        env:
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_PASS: ${{ secrets.GMAIL_PASS }}
          DOB: ${{ secrets.DOB }}
      - name: Commit portfolio.json if changed
        run: |
          git config user.email "actions@github.com"
          git config user.name "GitHub Actions"
          git add data/portfolio.json
          git diff --staged --quiet || git commit -m "update portfolio.json"
          git push
```

### .github/workflows/realtime.yml

```yaml
name: Realtime update
on:
  schedule:
    - cron: '0 */2 * * *'
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python src/build_html.py
        env:
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_PASS: ${{ secrets.GMAIL_PASS }}
          BINANCE_API_KEY: ${{ secrets.BINANCE_API_KEY }}
          BINANCE_SECRET_KEY: ${{ secrets.BINANCE_SECRET_KEY }}
          BTC_ADDRESS: ${{ secrets.BTC_ADDRESS }}
      - name: Commit index.html and history.json
        run: |
          git config user.email "actions@github.com"
          git config user.name "GitHub Actions"
          git add index.html data/history.json
          git diff --staged --quiet || git commit -m "update dashboard $(date -u)"
          git push
```

---

## GitHub Secrets to configure

| Secret | Value |
|---|---|
| `GMAIL_USER` | Gmail address |
| `GMAIL_PASS` | Gmail App Password (16 chars) |
| `DOB` | Dime PDF password (DDMMYYYY) |
| `BINANCE_API_KEY` | Binance TH API key |
| `BINANCE_SECRET_KEY` | Binance TH secret key |
| `BTC_ADDRESS` | Trezor BTC address (bc1q...) |

---

## requirements.txt

```
requests
PyPDF2
pdfplumber
yfinance
python-dateutil
```

---

## Important notes

1. **Binance endpoint is `api.binance.th` not `api.binance.com`** — different domain for Thai exchange
2. **PDF has Thai + English mixed text** — pdfplumber handles this better than PyPDF2 for text extraction; PyPDF2 is only for decryption
3. **BTC from two sources** — add `btc_binance + btc_hw` before multiplying by price, never show them separately in the total
4. **Crypto prices from Binance TH** — use `{COIN}THB` pairs e.g. `BTCTHB`, `ETHTHB`; for coins without a THB pair, use `{COIN}USDT` × USD/THB rate
5. **Error handling** — if any source fails, use last known value from `portfolio.json` or `history.json` and mark that source as stale in the header with a red badge
6. **GitHub Pages** — enable in repo Settings → Pages → Source: Deploy from branch `main`, folder `/` (root). `index.html` at root will serve automatically
7. **Empty commits** — always check `git diff --staged --quiet` before committing to avoid empty commit errors