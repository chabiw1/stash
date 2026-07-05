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


def format_last_sync(ts):
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return ts
    offset = dt.strftime("%z")  # e.g. '+0700'
    offset_short = offset[:3] if offset else ""
    return dt.strftime("%b %-d, %Y") + " · " + dt.strftime("%I:%M %p") + " " + offset_short


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
    ytd_color = "#00ff9c" if ytd_pct >= 0 else "#f87171"
    ytd_arrow = "▲" if ytd_pct >= 0 else "▼"

    # Freshness -> two-state LIVE/STALE badge per design
    try:
        last_dt = datetime.fromisoformat(ts)
        age_hours = (datetime.now(BANGKOK) - last_dt).total_seconds() / 3600
    except Exception:
        age_hours = 999
    is_live = age_hours < 6 and not stale_sources
    badge_color = "#00ff9c" if is_live else "#f87171"
    badge_label = "LIVE" if is_live else "STALE"

    last_sync = format_last_sync(ts)
    subtitle = f"Last sync {last_sync}"
    if stale_sources:
        subtitle += f" · {', '.join(stale_sources)} stale"

    # Tooltip details (native title attribute on summary cells)
    kbank_thb = snapshot.get("kbank_thb", 0) or 0
    dime_cash_usd = snapshot.get("dime_cash_usd", 0) or 0
    btc_binance = snapshot.get("btc_binance", 0) or 0
    btc_hw = snapshot.get("btc_hw", 0) or 0
    btc_price_thb = snapshot.get("btc_price_thb", 0) or 0
    binance_crypto_thb = snapshot.get("binance_crypto_thb", 0) or 0
    hw_wallet_thb = btc_hw * btc_price_thb

    cash_tooltip = f"KBank {fmt_thb(kbank_thb)}\nDime USD {fmt_usd(dime_cash_usd)}"
    stocks_tooltip = f"Dime {fmt_thb(stocks_thb)}"
    etf_tooltip = f"Dime {fmt_thb(etf_thb)}"
    if crypto_thb > 0:
        bn_pct = binance_crypto_thb / crypto_thb * 100 if crypto_thb else 0
        hw_pct = hw_wallet_thb / crypto_thb * 100 if crypto_thb else 0
        btc_total = btc_binance + btc_hw
        crypto_tooltip = (
            f"Binance TH {fmt_thb(binance_crypto_thb)} ({bn_pct:.0f}%)\n"
            f"HW Wallet {fmt_thb(hw_wallet_thb)} ({hw_pct:.0f}%)\n"
            f"BTC total: {btc_total:.6f} BTC"
        )
    else:
        crypto_tooltip = "No crypto data"

    summary_cards = [
        {"label": "Cash", "color": "#2dd4bf", "thb": cash_thb, "usd": cash_usd, "tooltip": cash_tooltip},
        {"label": "US Stocks", "color": "#a78bfa", "thb": stocks_thb, "usd": stocks_usd, "tooltip": stocks_tooltip},
        {"label": "ETF", "color": "#f472b6", "thb": etf_thb, "usd": etf_usd, "tooltip": etf_tooltip},
        {"label": "Crypto", "color": "#fbbf24", "thb": crypto_thb, "usd": crypto_usd, "tooltip": crypto_tooltip},
    ]
    summary_cards_html = "".join(f"""
      <div class="summary-cell" title="{c['tooltip']}">
        <div class="summary-label" style="color:{c['color']}">{c['label']}</div>
        <div class="summary-thb">฿{c['thb']:,.0f}</div>
        <div class="summary-usd">${c['usd']:,.0f}</div>
      </div>""" for c in summary_cards)

    # Holdings table rows (pre-sorted by value desc; JS re-sorts client-side)
    holdings_rows_html = ""
    for row in sorted(dime_holdings_rows, key=lambda x: x["value_usd"], reverse=True):
        pnl = row["pnl_pct"]
        pnl_color = "#34d399" if pnl >= 0 else "#f87171"
        pnl_sign = "+" if pnl >= 0 else ""
        is_etf = row["asset_type"] == "etf"
        badge_fg = "#f9a8d4" if is_etf else "#c4b5fd"
        type_label = "ETF" if is_etf else "Stock"
        holdings_rows_html += f"""
      <div class="row6" data-symbol="{row['symbol']}" data-type="{type_label}" data-shares="{row['shares']}" data-price="{row['price_usd']}" data-value="{row['value_usd']}" data-pnl="{pnl}">
        <div class="sym">{row['symbol']}</div>
        <div><span class="type-badge" style="border-color:{badge_fg};color:{badge_fg}">[{type_label}]</span></div>
        <div class="num muted">{row['shares']:.6f}</div>
        <div class="num muted">${row['price_usd']:,.2f}</div>
        <div class="num">${row['value_usd']:,.2f}</div>
        <div class="num pnl" style="color:{pnl_color}">{pnl_sign}{pnl:.1f}%</div>
      </div>"""

    # Crypto table rows (pre-sorted by value desc; JS re-sorts client-side)
    crypto_rows_html = ""
    for row in sorted(crypto_rows, key=lambda x: x["value_thb"], reverse=True):
        hw_qty_num = row["hw_qty"] or 0
        hw_qty_str = f"{row['hw_qty']:.6f}" if row["hw_qty"] else "—"
        price_str = f"฿{row['price_thb']:,.2f}" if row["price_thb"] else "—"
        crypto_rows_html += f"""
      <div class="row6c" data-coin="{row['coin']}" data-exch="{row['binance_qty']}" data-wallet="{hw_qty_num}" data-total="{row['total_qty']}" data-price="{row['price_thb']}" data-value="{row['value_thb']}">
        <div class="sym">{row['coin']}</div>
        <div class="num muted">{row['binance_qty']:.6f}</div>
        <div class="num muted">{hw_qty_str}</div>
        <div class="num">{row['total_qty']:.6f}</div>
        <div class="num muted">{price_str}</div>
        <div class="num">{fmt_thb(row['value_thb'])}</div>
      </div>"""

    history_json = json.dumps(history)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wealth Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #050608; font-family: 'JetBrains Mono', monospace; }}

  .wrap {{
    max-width: 1200px; margin: 0 auto; padding: 32px 20px 80px; background: #050608;
    background-image: linear-gradient(rgba(255,255,255,0.025) 1px,transparent 1px),
      linear-gradient(90deg,rgba(255,255,255,0.025) 1px,transparent 1px);
    background-size: 24px 24px; color: #d5d9e0; min-height: 100vh;
  }}

  .header-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 16px; flex-wrap: wrap; gap: 12px; }}
  .title {{ font-size: 19px; font-weight: 800; letter-spacing: 0.03em; text-transform: uppercase; color: #f2f4f7; }}
  .subtitle {{ font-size: 12px; color: #6b7280; margin-top: 4px; }}
  .status-badge {{ display: flex; align-items: center; gap: 6px; border: 1px solid; padding: 5px 12px; font-size: 12px; font-weight: 700; letter-spacing: 0.05em; }}
  .status-dot {{ width: 6px; height: 6px; display: inline-block; }}

  .hero-card {{ border: 1px solid rgba(255,255,255,0.14); padding: 28px; margin-bottom: 16px; }}
  .hero-eyebrow {{ font-size: 11px; color: #6b7280; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 10px; }}
  .hero-num-row {{ display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }}
  .hero-num {{ font-size: 46px; font-weight: 800; letter-spacing: -0.01em; color: #f2f4f7; }}
  .hero-usd {{ font-size: 18px; color: #8b93a0; }}
  .hero-meta-row {{ display: flex; align-items: center; gap: 16px; margin-top: 14px; flex-wrap: wrap; }}
  .ytd {{ font-size: 13px; font-weight: 700; }}
  .fx-note {{ font-size: 12px; color: #6b7280; }}

  .summary-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 1px; background: rgba(255,255,255,0.14); margin-bottom: 16px; }}
  .summary-cell {{ background: #050608; padding: 16px; }}
  .summary-label {{ font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 8px; }}
  .summary-thb {{ font-size: 19px; font-weight: 700; color: #f2f4f7; }}
  .summary-usd {{ font-size: 12px; color: #6b7280; margin-top: 4px; }}

  .panel {{ border: 1px solid rgba(255,255,255,0.14); padding: 20px; margin-bottom: 16px; }}
  .panel-label {{ font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: #8b93a0; margin-bottom: 12px; }}

  .headrow6, .row6 {{ display: grid; grid-template-columns: 0.8fr 1fr 0.8fr 1fr 1fr 0.8fr; }}
  .headrow6c, .row6c {{ display: grid; grid-template-columns: 0.8fr 1fr 1fr 1fr 1fr 1fr; }}
  .headrow6, .headrow6c {{ color: #6b7280; font-size: 11px; text-transform: uppercase; padding: 0 6px 6px; }}
  .headrow6 > div, .headrow6c > div {{ cursor: pointer; user-select: none; }}
  .headrow6 > div:hover, .headrow6c > div:hover {{ color: #d5d9e0; }}
  .row6, .row6c {{ align-items: center; font-size: 13px; padding: 8px 6px; border-top: 1px solid rgba(255,255,255,0.08); }}
  .row6:hover, .row6c:hover {{ background: rgba(255,255,255,0.045); }}
  .sym {{ font-weight: 700; color: #f2f4f7; }}
  .num {{ text-align: right; }}
  .muted {{ color: #9aa1ac; }}
  .pnl {{ font-weight: 700; }}
  .type-badge {{ font-size: 10px; font-weight: 700; padding: 2px 6px; border: 1px solid; }}

  .headrow6 > div:nth-child(1), .headrow6 > div:nth-child(2),
  .row6 > div:nth-child(1), .row6 > div:nth-child(2) {{ text-align: left; }}
  .headrow6 > div:nth-child(n+3) {{ text-align: right; }}
  .headrow6c > div:nth-child(1), .row6c > div:nth-child(1) {{ text-align: left; }}
  .headrow6c > div:nth-child(n+2) {{ text-align: right; }}

  .chart-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 10px; }}
  .chart-label {{ font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: #8b93a0; }}
  .seg-control {{ display: flex; gap: 1px; border: 1px solid rgba(255,255,255,0.25); }}
  .seg-btn {{ border: none; padding: 5px 12px; font-size: 11px; font-weight: 700; cursor: pointer; font-family: 'JetBrains Mono', monospace; background: transparent; color: #6b7280; }}
  .seg-btn.active {{ background: #00ff9c; color: #050608; }}
  #wealthChart {{ width: 100%; height: 180px; display: block; cursor: crosshair; }}

  @media (max-width: 720px) {{
    .summary-grid {{ grid-template-columns: repeat(2,1fr); }}
    .hero-num {{ font-size: 32px; }}
    .tablewrap {{ overflow-x: auto; }}
    .row6, .headrow6 {{ min-width: 560px; }}
    .row6c, .headrow6c {{ min-width: 520px; }}
  }}
</style>
</head>
<body>

<div class="wrap" data-screen-label="Wealth Dashboard">

  <div class="header-row">
    <div>
      <div class="title">Wealth Dashboard</div>
      <div class="subtitle">{subtitle}</div>
    </div>
    <div class="status-badge" style="border-color:{badge_color};color:{badge_color}">
      <span class="status-dot" style="background:{badge_color};box-shadow:0 0 6px {badge_color}"></span>[ {badge_label} ]
    </div>
  </div>

  <div class="hero-card">
    <div class="hero-eyebrow">Total Net Worth</div>
    <div class="hero-num-row">
      <div class="hero-num">฿{total_thb:,.0f}</div>
      <div class="hero-usd">${total_usd:,.0f} USD</div>
    </div>
    <div class="hero-meta-row">
      <div class="ytd" style="color:{ytd_color}">{ytd_arrow} {ytd_sign}{ytd_pct:.1f}% YTD</div>
      <div class="fx-note">FX 1 USD = {usd_thb:.2f} THB</div>
    </div>
  </div>

  <div class="summary-grid">{summary_cards_html}
  </div>

  <div class="panel">
    <div class="panel-label">Holdings</div>
    <div class="tablewrap">
      <div class="headrow6" id="holdHead">
        <div data-key="symbol" data-type="text">Sym<span class="arrow"></span></div>
        <div data-key="type" data-type="text">Type<span class="arrow"></span></div>
        <div data-key="shares" data-type="num">Shares<span class="arrow"></span></div>
        <div data-key="price" data-type="num">Price<span class="arrow"></span></div>
        <div data-key="value" data-type="num">Value<span class="arrow"></span></div>
        <div data-key="pnl" data-type="num">PnL<span class="arrow"></span></div>
      </div>
      <div id="holdBody">{holdings_rows_html}
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-label">Crypto</div>
    <div class="tablewrap">
      <div class="headrow6c" id="cryptoHead">
        <div data-key="coin" data-type="text">Coin<span class="arrow"></span></div>
        <div data-key="exch" data-type="num">Exch<span class="arrow"></span></div>
        <div data-key="wallet" data-type="num">HW<span class="arrow"></span></div>
        <div data-key="total" data-type="num">Total<span class="arrow"></span></div>
        <div data-key="price" data-type="num">Price<span class="arrow"></span></div>
        <div data-key="value" data-type="num">Value<span class="arrow"></span></div>
      </div>
      <div id="cryptoBody">{crypto_rows_html}
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="chart-header">
      <div class="chart-label">Wealth / Time</div>
      <div class="seg-control">
        <button class="seg-btn" data-months="1">1M</button>
        <button class="seg-btn" data-months="3">3M</button>
        <button class="seg-btn active" data-months="6">6M</button>
      </div>
    </div>
    <svg id="wealthChart" viewBox="0 0 600 180">
      <polygon id="chartArea" points="" fill="#00ff9c" opacity="0.08"></polygon>
      <polyline id="chartLine" points="" fill="none" stroke="#00ff9c" stroke-width="1.5"></polyline>
      <g id="hoverGroup" style="display:none">
        <line id="hoverLine" x1="0" y1="0" x2="0" y2="180" stroke="rgba(255,255,255,0.2)" stroke-width="1"></line>
        <circle id="hoverDot" cx="0" cy="0" r="3.5" fill="#00ff9c" stroke="#050608" stroke-width="1.5"></circle>
        <rect id="hoverBox" x="0" y="6" width="86" height="20" fill="#0b0d10" stroke="rgba(255,255,255,0.2)"></rect>
        <text id="hoverText" x="0" y="20" fill="#00ff9c" font-size="11" font-family="'JetBrains Mono',monospace"></text>
      </g>
    </svg>
  </div>

</div>

<script>
const HISTORY = {history_json};

function makeSortable(headId, bodyId, defaultKey, defaultDir) {{
  const head = document.getElementById(headId);
  const body = document.getElementById(bodyId);
  const cells = Array.from(head.children);
  const state = {{ key: defaultKey, dir: defaultDir }};

  function applyArrows() {{
    cells.forEach(c => {{
      const arrow = c.querySelector('.arrow');
      arrow.textContent = c.dataset.key === state.key ? (state.dir === 1 ? ' ▲' : ' ▼') : '';
    }});
  }}

  function sortRows() {{
    const cell = cells.find(c => c.dataset.key === state.key);
    const isText = cell.dataset.type === 'text';
    const rows = Array.from(body.children);
    rows.sort((a, b) => {{
      const av = a.dataset[state.key], bv = b.dataset[state.key];
      if (isText) return av.localeCompare(bv) * state.dir;
      return (parseFloat(av) - parseFloat(bv)) * state.dir;
    }});
    rows.forEach(r => body.appendChild(r));
  }}

  cells.forEach(c => {{
    c.addEventListener('click', () => {{
      const key = c.dataset.key;
      if (state.key === key) {{ state.dir = -state.dir; }}
      else {{ state.key = key; state.dir = c.dataset.type === 'text' ? 1 : -1; }}
      applyArrows();
      sortRows();
    }});
  }});

  applyArrows();
  sortRows();
}}

makeSortable('holdHead', 'holdBody', 'value', -1);
makeSortable('cryptoHead', 'cryptoBody', 'value', -1);

const svg = document.getElementById('wealthChart');
const lineEl = document.getElementById('chartLine');
const areaEl = document.getElementById('chartArea');
const hoverGroup = document.getElementById('hoverGroup');
const hoverLine = document.getElementById('hoverLine');
const hoverDot = document.getElementById('hoverDot');
const hoverBox = document.getElementById('hoverBox');
const hoverText = document.getElementById('hoverText');

let currentCoords = [];
let currentValues = [];

function buildPath(pts) {{
  const w = 600, h = 180, padX = 12, padY = 14;
  const min = Math.min(...pts), max = Math.max(...pts);
  const span = (max - min) || 1;
  const stepX = (w - padX * 2) / (pts.length - 1 || 1);
  const coords = pts.map((v, i) => {{
    const x = padX + i * stepX;
    const y = padY + (h - padY * 2) * (1 - (v - min) / span);
    return [x, y];
  }});
  const path = coords.map(c => c.join(',')).join(' ');
  const area = padX + ',' + (h - padY) + ' ' + path + ' ' + (padX + stepX * (pts.length - 1)) + ',' + (h - padY);
  return {{ path, area, coords }};
}}

function renderChart(months) {{
  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - months);
  const filtered = HISTORY.filter(e => new Date(e.ts) >= cutoff);
  const data = filtered.length ? filtered : HISTORY;
  const pts = data.map(e => e.total_thb);
  const built = buildPath(pts);
  lineEl.setAttribute('points', built.path);
  areaEl.setAttribute('points', built.area);
  currentCoords = built.coords;
  currentValues = pts;
  hoverGroup.style.display = 'none';
}}

svg.addEventListener('mousemove', (e) => {{
  if (!currentCoords.length) return;
  const rect = svg.getBoundingClientRect();
  const scaleX = 600 / rect.width;
  const vx = (e.clientX - rect.left) * scaleX;
  let best = 0, bestDist = Infinity;
  currentCoords.forEach((c, i) => {{
    const d = Math.abs(c[0] - vx);
    if (d < bestDist) {{ bestDist = d; best = i; }}
  }});
  const [x, y] = currentCoords[best];
  hoverGroup.style.display = '';
  hoverLine.setAttribute('x1', x); hoverLine.setAttribute('x2', x);
  hoverDot.setAttribute('cx', x); hoverDot.setAttribute('cy', y);
  let boxX, textX, anchor = 'start';
  if (x > 480) {{ boxX = x - 92; textX = x - 86; }}
  else {{ boxX = x + 6; textX = x + 12; }}
  hoverBox.setAttribute('x', boxX);
  hoverText.setAttribute('x', textX);
  hoverText.setAttribute('text-anchor', anchor);
  hoverText.textContent = '฿' + Math.round(currentValues[best]).toLocaleString('en-US');
}});

svg.addEventListener('mouseleave', () => {{ hoverGroup.style.display = 'none'; }});

document.querySelectorAll('.seg-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderChart(parseInt(btn.dataset.months, 10));
  }});
}});

renderChart(6);
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
