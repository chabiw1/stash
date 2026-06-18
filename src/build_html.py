import sys
import os
import json
from datetime import datetime, timezone, timedelta

# Allow sibling module imports when run as python src/build_html.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_prices import (
    get_binance_balances,
    get_binance_price_thb,
    get_usd_thb_rate,
    get_crypto_price_thb,
    get_stock_prices,
)
from fetch_btc_onchain import get_btc_balance
from fetch_kbank import get_kbank_balance

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(BASE_DIR, "data", "portfolio.json")
HISTORY_PATH = os.path.join(BASE_DIR, "data", "history.json")
HTML_PATH = os.path.join(BASE_DIR, "index.html")

BANGKOK = timezone(timedelta(hours=7))


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def now_bangkok_iso():
    return datetime.now(BANGKOK).isoformat(timespec="seconds")


def fmt_thb(v):
    return f"฿{v:,.0f}"


def fmt_usd(v):
    return f"${v:,.0f}"


def generate_html(
    snapshot,
    history,
    dime_holdings_rows,
    crypto_rows,
    stale_sources,
):
    ts = snapshot["ts"]
    total_thb = snapshot["total_thb"]
    cash_thb = snapshot["cash_thb"]
    stocks_thb = snapshot["stocks_thb"]
    etf_thb = snapshot["etf_thb"]
    crypto_thb = snapshot["crypto_thb"]
    usd_thb = snapshot["usd_thb_rate"]

    total_usd = total_thb / usd_thb if usd_thb else 0
    cash_usd = cash_thb / usd_thb if usd_thb else 0
    stocks_usd = stocks_thb / usd_thb if usd_thb else 0
    etf_usd = etf_thb / usd_thb if usd_thb else 0
    crypto_usd = crypto_thb / usd_thb if usd_thb else 0

    # YTD from history
    current_year = datetime.now(BANGKOK).year
    ytd_entries = [e for e in history if e["ts"].startswith(str(current_year))]
    if len(ytd_entries) >= 2:
        ytd_start = ytd_entries[0]["total_thb"]
        ytd_pct = (total_thb - ytd_start) / ytd_start * 100 if ytd_start else 0
    else:
        ytd_pct = 0

    ytd_sign = "+" if ytd_pct >= 0 else ""
    ytd_color = "#22c55e" if ytd_pct >= 0 else "#ef4444"
    ytd_arrow = "▲" if ytd_pct >= 0 else "▼"

    # Freshness
    try:
        last_dt = datetime.fromisoformat(ts)
        age_hours = (datetime.now(BANGKOK) - last_dt).total_seconds() / 3600
    except Exception:
        age_hours = 999
    fresh = age_hours < 6
    badge_color = "#22c55e" if fresh else "#ef4444"
    badge_text = f"Updated {int(age_hours)}h ago" if not fresh else "Live"
    if stale_sources:
        badge_text = "Partial: " + ", ".join(stale_sources) + " stale"
        badge_color = "#f59e0b"

    # Tooltip details
    kbank_thb = snapshot.get("kbank_thb", 0) or 0
    dime_cash_usd = snapshot.get("dime_cash_usd", 0) or 0
    dime_cash_thb = dime_cash_usd * usd_thb
    btc_binance = snapshot.get("btc_binance", 0) or 0
    btc_hw = snapshot.get("btc_hw", 0) or 0
    btc_price_thb = snapshot.get("btc_price_thb", 0) or 0
    binance_crypto_thb = snapshot.get("binance_crypto_thb", 0) or 0
    hw_wallet_thb = btc_hw * btc_price_thb

    # Cash tooltip
    cash_tooltip = f"KBank {fmt_thb(kbank_thb)}<br>Dime USD {fmt_usd(dime_cash_usd)}"
    stocks_tooltip = f"Dime {fmt_thb(stocks_thb)}"
    etf_tooltip = f"Dime {fmt_thb(etf_thb)}"
    if crypto_thb > 0:
        bn_pct = binance_crypto_thb / crypto_thb * 100 if crypto_thb else 0
        hw_pct = hw_wallet_thb / crypto_thb * 100 if crypto_thb else 0
        btc_total = btc_binance + btc_hw
        crypto_tooltip = (
            f"Binance TH {fmt_thb(binance_crypto_thb)} ({bn_pct:.0f}%)<br>"
            f"HW Wallet {fmt_thb(hw_wallet_thb)} ({hw_pct:.0f}%)<br>"
            f"BTC total: {btc_total:.6f} BTC"
        )
    else:
        crypto_tooltip = "No crypto data"

    # Holdings table rows
    holdings_rows_html = ""
    for row in sorted(dime_holdings_rows, key=lambda x: x["value_usd"], reverse=True):
        pnl = row["pnl_pct"]
        pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
        pnl_sign = "+" if pnl >= 0 else ""
        badge_cls = "badge-stock" if row["asset_type"] == "stock" else "badge-etf"
        badge_label = "Stock" if row["asset_type"] == "stock" else "ETF"
        holdings_rows_html += f"""
        <tr>
          <td class="sym">{row['symbol']}</td>
          <td><span class="badge {badge_cls}">{badge_label}</span></td>
          <td>{row['shares']:.6f}</td>
          <td>${row['price_usd']:,.2f}</td>
          <td>${row['value_usd']:,.2f}</td>
          <td style="color:{pnl_color};font-weight:600">{pnl_sign}{pnl:.1f}%</td>
        </tr>"""

    # Crypto table rows
    crypto_rows_html = ""
    for row in sorted(crypto_rows, key=lambda x: x["value_thb"], reverse=True):
        hw_qty = f"{row['hw_qty']:.6f}" if row["hw_qty"] else "—"
        price_str = f"฿{row['price_thb']:,.2f}" if row["price_thb"] else "—"
        crypto_rows_html += f"""
        <tr>
          <td class="sym">{row['coin']}</td>
          <td>{row['binance_qty']:.6f}</td>
          <td>{hw_qty}</td>
          <td>{row['total_qty']:.6f}</td>
          <td>{price_str}</td>
          <td>{fmt_thb(row['value_thb'])}</td>
        </tr>"""

    history_json = json.dumps(history)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wealth Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2a2d3a;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --teal: #1D9E75;
    --purple: #534AB7;
    --pink: #D4537E;
    --amber: #EF9F27;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; max-width: 1200px; margin: 0 auto; }}
  h2 {{ font-size: 1rem; color: var(--muted); font-weight: 500; margin-bottom: 16px; }}

  /* Header */
  .header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }}
  .header h1 {{ font-size: 1.4rem; font-weight: 700; letter-spacing: -0.5px; }}
  .header-meta {{ margin-left: auto; display: flex; align-items: center; gap: 10px; font-size: 0.82rem; color: var(--muted); }}
  .badge-live {{ padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }}

  /* Total card */
  .total-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px 32px; margin-bottom: 24px; display: flex; align-items: center; gap: 32px; flex-wrap: wrap; }}
  .total-thb {{ font-size: 2.6rem; font-weight: 800; letter-spacing: -1px; }}
  .total-usd {{ font-size: 1.4rem; color: var(--muted); font-weight: 500; }}
  .ytd-badge {{ padding: 6px 14px; border-radius: 20px; font-size: 0.9rem; font-weight: 700; }}
  .rate-note {{ margin-left: auto; font-size: 0.82rem; color: var(--muted); }}

  /* Asset cards */
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
  @media (max-width: 900px) {{ .cards {{ grid-template-columns: repeat(2, 1fr); }} }}
  @media (max-width: 500px) {{ .cards {{ grid-template-columns: 1fr; }} }}

  .card {{ position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 20px 22px; cursor: default; }}
  .card-dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-bottom: 10px; }}
  .card-label {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 6px; font-weight: 500; }}
  .card-thb {{ font-size: 1.3rem; font-weight: 700; }}
  .card-usd {{ font-size: 0.82rem; color: var(--muted); margin-top: 4px; }}

  /* Tooltip */
  .tooltip-content {{
    display: none; position: absolute; z-index: 100; bottom: calc(100% + 8px); left: 0;
    background: #252836; border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 16px; min-width: 220px; font-size: 0.82rem; line-height: 1.7;
    color: var(--text); white-space: nowrap; pointer-events: none;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  }}
  .card:hover .tooltip-content {{ display: block; }}

  /* Tables */
  .table-section {{ margin-bottom: 36px; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  thead th {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--muted); font-weight: 500; white-space: nowrap; }}
  tbody tr {{ border-bottom: 1px solid var(--border); }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody td {{ padding: 10px 12px; white-space: nowrap; }}
  .sym {{ font-weight: 700; font-family: monospace; font-size: 0.95rem; }}

  /* Badges */
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; }}
  .badge-stock {{ background: rgba(83,74,183,0.2); color: #8b80f0; }}
  .badge-etf {{ background: rgba(212,83,126,0.2); color: #f07aaa; }}

  /* Chart */
  .chart-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 24px; margin-bottom: 32px; }}
  .chart-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }}
  .chart-toggles {{ display: flex; gap: 8px; }}
  .toggle-btn {{ background: transparent; border: 1px solid var(--border); color: var(--muted); border-radius: 6px; padding: 5px 14px; cursor: pointer; font-size: 0.82rem; transition: all 0.15s; }}
  .toggle-btn.active, .toggle-btn:hover {{ background: var(--teal); border-color: var(--teal); color: #fff; }}
  canvas {{ max-height: 320px; }}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <h1>Wealth Dashboard</h1>
  <div class="header-meta">
    <span>{ts}</span>
    <span class="badge-live" style="background:{badge_color}22;color:{badge_color};border:1px solid {badge_color}44">
      {badge_text}
    </span>
  </div>
</div>

<!-- Total wealth card -->
<div class="total-card">
  <div>
    <div class="total-thb">{fmt_thb(total_thb)}</div>
    <div class="total-usd">{fmt_usd(total_usd)}</div>
  </div>
  <div class="ytd-badge" style="background:{ytd_color}22;color:{ytd_color}">
    {ytd_arrow} YTD {ytd_sign}{ytd_pct:.1f}%
  </div>
  <div class="rate-note">1 USD = {usd_thb:.2f} THB</div>
</div>

<!-- Asset class cards -->
<div class="cards">
  <div class="card">
    <span class="card-dot" style="background:#1D9E75"></span>
    <div class="card-label">Cash</div>
    <div class="card-thb">{fmt_thb(cash_thb)}</div>
    <div class="card-usd">{fmt_usd(cash_usd)}</div>
    <div class="tooltip-content">{cash_tooltip}</div>
  </div>
  <div class="card">
    <span class="card-dot" style="background:#534AB7"></span>
    <div class="card-label">US Stocks</div>
    <div class="card-thb">{fmt_thb(stocks_thb)}</div>
    <div class="card-usd">{fmt_usd(stocks_usd)}</div>
    <div class="tooltip-content">{stocks_tooltip}</div>
  </div>
  <div class="card">
    <span class="card-dot" style="background:#D4537E"></span>
    <div class="card-label">ETF</div>
    <div class="card-thb">{fmt_thb(etf_thb)}</div>
    <div class="card-usd">{fmt_usd(etf_usd)}</div>
    <div class="tooltip-content">{etf_tooltip}</div>
  </div>
  <div class="card">
    <span class="card-dot" style="background:#EF9F27"></span>
    <div class="card-label">Crypto</div>
    <div class="card-thb">{fmt_thb(crypto_thb)}</div>
    <div class="card-usd">{fmt_usd(crypto_usd)}</div>
    <div class="tooltip-content">{crypto_tooltip}</div>
  </div>
</div>

<!-- Dime Holdings Table -->
<div class="table-section">
  <h2>Dime Holdings</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Symbol</th><th>Class</th><th>Shares</th>
          <th>Price USD</th><th>Value USD</th><th>PnL %</th>
        </tr>
      </thead>
      <tbody>{holdings_rows_html}</tbody>
    </table>
  </div>
</div>

<!-- Crypto Table -->
<div class="table-section">
  <h2>Crypto</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Coin</th><th>Binance qty</th><th>HW qty</th>
          <th>Total qty</th><th>Price THB</th><th>Value THB</th>
        </tr>
      </thead>
      <tbody>{crypto_rows_html}</tbody>
    </table>
  </div>
</div>

<!-- Wealth History Chart -->
<div class="chart-section">
  <div class="chart-header">
    <h2 style="margin:0">Wealth History</h2>
    <div class="chart-toggles">
      <button class="toggle-btn" data-months="1">1M</button>
      <button class="toggle-btn active" data-months="3">3M</button>
      <button class="toggle-btn" data-months="6">6M</button>
    </div>
  </div>
  <canvas id="wealthChart"></canvas>
</div>

<script>
const HISTORY = {history_json};

const ctx = document.getElementById('wealthChart').getContext('2d');
const chart = new Chart(ctx, {{
  type: 'line',
  data: {{ labels: [], datasets: [
    {{
      label: 'Total (THB)',
      data: [],
      borderColor: '#1D9E75',
      backgroundColor: 'rgba(29,158,117,0.08)',
      yAxisID: 'y',
      tension: 0.4,
      pointRadius: 3,
      fill: true,
    }},
    {{
      label: 'Growth %',
      data: [],
      borderColor: '#EF9F27',
      backgroundColor: 'transparent',
      yAxisID: 'y1',
      tension: 0.4,
      pointRadius: 3,
      borderDash: [4, 3],
    }},
  ]}},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ labels: {{ color: '#94a3b8' }} }},
      tooltip: {{
        callbacks: {{
          label: (ctx) => {{
            if (ctx.datasetIndex === 0) return ' ฿' + ctx.raw.toLocaleString();
            return ' ' + (ctx.raw >= 0 ? '+' : '') + ctx.raw.toFixed(2) + '%';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 8 }}, grid: {{ color: '#1e2233' }} }},
      y: {{
        type: 'linear', position: 'left',
        ticks: {{ color: '#1D9E75', callback: (v) => '฿' + v.toLocaleString() }},
        grid: {{ color: '#1e2233' }},
      }},
      y1: {{
        type: 'linear', position: 'right',
        ticks: {{ color: '#EF9F27', callback: (v) => (v >= 0 ? '+' : '') + v.toFixed(1) + '%' }},
        grid: {{ drawOnChartArea: false }},
      }},
    }},
  }},
}});

function updateChart(months) {{
  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - months);
  const data = HISTORY.filter(e => new Date(e.ts) >= cutoff);
  const labels = data.map(e => {{
    const d = new Date(e.ts);
    return d.toLocaleDateString('en-GB', {{ month: 'short', day: 'numeric' }});
  }});
  const totals = data.map(e => e.total_thb);
  const first = totals[0] || 1;
  const growth = totals.map(v => parseFloat(((v - first) / first * 100).toFixed(2)));
  chart.data.labels = labels;
  chart.data.datasets[0].data = totals;
  chart.data.datasets[1].data = growth;
  chart.update();
}}

document.querySelectorAll('.toggle-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    updateChart(parseInt(btn.dataset.months));
  }});
}});

updateChart(3);
</script>
</body>
</html>"""


def build():
    portfolio = load_json(PORTFOLIO_PATH)
    history = load_json(HISTORY_PATH)

    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_PASS", "")
    api_key = os.environ.get("BINANCE_API_KEY", "")
    secret_key = os.environ.get("BINANCE_SECRET_KEY", "")
    btc_address = os.environ.get("BTC_ADDRESS", "")

    stale_sources = []

    # Fetch USD/THB rate
    try:
        usd_thb = get_usd_thb_rate(api_key, secret_key)
    except Exception:
        stale_sources.append("Binance TH")
        usd_thb = (history[-1]["usd_thb_rate"] if history else 35.0)

    # Fetch Binance TH balances
    try:
        binance_balances = get_binance_balances(api_key, secret_key)
    except Exception:
        stale_sources.append("Binance")
        binance_balances = {}

    # Fetch BTC on-chain
    try:
        btc_hw = get_btc_balance(btc_address) if btc_address else 0.0
    except Exception:
        stale_sources.append("HW Wallet")
        btc_hw = 0.0

    # Fetch KBank
    try:
        kbank_thb = get_kbank_balance(gmail_user, gmail_pass) or 0.0
    except Exception:
        stale_sources.append("KBank")
        kbank_thb = 0.0

    # Fetch stock prices
    symbols = list(portfolio.get("holdings", {}).keys())
    try:
        stock_prices_usd = get_stock_prices(symbols)
    except Exception:
        stale_sources.append("Stock prices")
        stock_prices_usd = {s: None for s in symbols}

    # Fetch crypto prices in THB
    crypto_prices_thb = {}
    for coin in binance_balances:
        try:
            crypto_prices_thb[coin] = get_crypto_price_thb(api_key, secret_key, coin, usd_thb)
        except Exception:
            crypto_prices_thb[coin] = None

    btc_price_thb = crypto_prices_thb.get("BTC")

    # Aggregate by asset class
    dime_cash_usd = portfolio.get("dime_cash_usd", 0) or 0
    cash_thb = kbank_thb + dime_cash_usd * usd_thb

    holdings = portfolio.get("holdings", {})
    stocks_thb = sum(
        h["shares"] * (stock_prices_usd.get(sym) or 0) * usd_thb
        for sym, h in holdings.items()
        if h["asset_type"] == "stock"
    )
    etf_thb = sum(
        h["shares"] * (stock_prices_usd.get(sym) or 0) * usd_thb
        for sym, h in holdings.items()
        if h["asset_type"] == "etf"
    )

    # Merge BTC from Binance + HW wallet
    btc_binance = binance_balances.get("BTC", 0)
    btc_total = btc_binance + (btc_hw or 0)
    balances_merged = {**binance_balances, "BTC": btc_total}

    binance_crypto_thb = sum(
        qty * (crypto_prices_thb.get(coin) or 0)
        for coin, qty in binance_balances.items()
    )
    hw_wallet_thb = (btc_hw or 0) * (btc_price_thb or 0)
    crypto_thb = sum(
        qty * (crypto_prices_thb.get(coin) or 0)
        for coin, qty in balances_merged.items()
    )

    total_thb = cash_thb + stocks_thb + etf_thb + crypto_thb

    ts = now_bangkok_iso()

    # Append to history
    history.append({
        "ts": ts,
        "total_thb": round(total_thb),
        "cash_thb": round(cash_thb),
        "stocks_thb": round(stocks_thb),
        "etf_thb": round(etf_thb),
        "crypto_thb": round(crypto_thb),
        "usd_thb_rate": round(usd_thb, 4),
    })
    save_json(HISTORY_PATH, history)

    # Build dime holdings rows
    dime_holdings_rows = []
    for sym, h in holdings.items():
        price = stock_prices_usd.get(sym) or 0
        value_usd = h["shares"] * price
        cost = h.get("avg_cost_usd") or 0
        pnl_pct = (price - cost) / cost * 100 if cost else 0
        dime_holdings_rows.append({
            "symbol": sym,
            "asset_type": h["asset_type"],
            "shares": h["shares"],
            "price_usd": price,
            "value_usd": value_usd,
            "pnl_pct": pnl_pct,
        })

    # Build crypto rows
    crypto_rows = []
    for coin, total_qty in balances_merged.items():
        b_qty = binance_balances.get(coin, 0)
        hw_qty = (btc_hw or 0) if coin == "BTC" else 0
        price_thb = crypto_prices_thb.get(coin) or 0
        value_thb = total_qty * price_thb
        crypto_rows.append({
            "coin": coin,
            "binance_qty": b_qty,
            "hw_qty": hw_qty if hw_qty else None,
            "total_qty": total_qty,
            "price_thb": price_thb,
            "value_thb": value_thb,
        })

    snapshot = {
        "ts": ts,
        "total_thb": round(total_thb),
        "cash_thb": round(cash_thb),
        "stocks_thb": round(stocks_thb),
        "etf_thb": round(etf_thb),
        "crypto_thb": round(crypto_thb),
        "usd_thb_rate": round(usd_thb, 4),
        "kbank_thb": kbank_thb,
        "dime_cash_usd": dime_cash_usd,
        "btc_binance": btc_binance,
        "btc_hw": btc_hw,
        "btc_price_thb": btc_price_thb,
        "binance_crypto_thb": binance_crypto_thb,
    }

    html = generate_html(
        snapshot=snapshot,
        history=history,
        dime_holdings_rows=dime_holdings_rows,
        crypto_rows=crypto_rows,
        stale_sources=stale_sources,
    )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard written to {HTML_PATH}")
    print(f"Total: {fmt_thb(total_thb)} (${total_thb / usd_thb:,.0f})")
    if stale_sources:
        print(f"Stale sources: {', '.join(stale_sources)}")


def fmt_thb(v):
    return f"฿{v:,.0f}"


if __name__ == "__main__":
    build()
