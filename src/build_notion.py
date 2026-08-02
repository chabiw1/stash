import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_prices import (
    get_binance_balances,
    get_crypto_price_thb,
    get_stock_prices,
    get_usd_thb_rate,
)
from fetch_btc_onchain import get_btc_balance

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(BASE_DIR, "data", "portfolio.json")
HISTORY_PATH = os.path.join(BASE_DIR, "data", "history.json")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
DB_HISTORY = os.environ.get("NOTION_DB_HISTORY", "")
DB_HOLDINGS = os.environ.get("NOTION_DB_HOLDINGS", "")
DB_CRYPTO = os.environ.get("NOTION_DB_CRYPTO", "")
STATS_PAGE = os.environ.get("NOTION_STATS_PAGE", "3b06e648-e512-8174-9a14-ebc9ec99a0ae")

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY", "")
BTC_ADDRESS = os.environ.get("BTC_ADDRESS", "")


def headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def notion_post(path, data):
    r = requests.post(f"https://api.notion.com/v1/{path}", headers=headers(), json=data, timeout=15)
    return r.json()


def notion_query(db_id):
    r = requests.post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        headers=headers(), json={}, timeout=15
    )
    return r.json().get("results", [])


def notion_patch(path, data):
    r = requests.patch(f"https://api.notion.com/v1/{path}", headers=headers(), json=data, timeout=15)
    return r.json()


def archive_all(db_id):
    pages = notion_query(db_id)
    for p in pages:
        requests.patch(
            f"https://api.notion.com/v1/pages/{p['id']}",
            headers=headers(), json={"archived": True}, timeout=15
        )


def clear_page_blocks(page_id):
    r = requests.get(f"https://api.notion.com/v1/blocks/{page_id}/children", headers=headers(), timeout=15)
    for b in r.json().get("results", []):
        requests.delete(f"https://api.notion.com/v1/blocks/{b['id']}", headers=headers(), timeout=15)


def push_stats_page(latest, usd_thb):
    clear_page_blocks(STATS_PAGE)
    total = latest["total_thb"]
    cash = latest["cash_thb"]
    stocks_etf = latest["stocks_thb"] + latest["etf_thb"]
    crypto = latest["crypto_thb"]
    total_usd = total / usd_thb if usd_thb else 0
    ts = latest["ts"]

    def callout(emoji, title, value_thb, color):
        return {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"{title}\n"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"฿{value_thb:,}"}},
                ],
                "icon": {"type": "emoji", "emoji": emoji},
                "color": color,
            },
        }

    blocks = [
        {
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Portfolio Overview"}}]},
        },
        {
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": "NET WORTH\n"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"฿{total:,}"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"  (~${total_usd:,.0f} USD)"}, "annotations": {"color": "gray"}},
                ],
                "icon": {"type": "emoji", "emoji": "💰"},
                "color": "green_background",
            },
        },
        {"object": "block", "type": "divider", "divider": {}},
        callout("📈", "Stocks & ETF", stocks_etf, "blue_background"),
        callout("🪙", "Crypto", crypto, "purple_background"),
        callout("💵", "Cash", cash, "gray_background"),
        {"object": "block", "type": "divider", "divider": {}},
        {
            "object": "block", "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": f"Last updated: {ts}"}, "annotations": {"color": "gray", "italic": True}}]
            },
        },
    ]

    requests.patch(
        f"https://api.notion.com/v1/blocks/{STATS_PAGE}/children",
        headers=headers(), json={"children": blocks}, timeout=15
    )


def push_history_entry(entry):
    notion_post("pages", {
        "parent": {"database_id": DB_HISTORY},
        "properties": {
            "Timestamp":    {"title": [{"text": {"content": entry["ts"]}}]},
            "Total (THB)":  {"number": entry["total_thb"]},
            "Cash (THB)":   {"number": entry["cash_thb"]},
            "Stocks (THB)": {"number": entry["stocks_thb"]},
            "ETF (THB)":    {"number": entry["etf_thb"]},
            "Crypto (THB)": {"number": entry["crypto_thb"]},
            "USD/THB Rate": {"number": entry["usd_thb_rate"]},
        },
    })


def push_holdings(holdings, stock_prices):
    archive_all(DB_HOLDINGS)
    for symbol, h in holdings.items():
        price = stock_prices.get(symbol) or 0
        value_usd = h["shares"] * price
        cost = h.get("avg_cost_usd") or 0
        pnl_pct = (price - cost) / cost if cost else 0
        notion_post("pages", {
            "parent": {"database_id": DB_HOLDINGS},
            "properties": {
                "Symbol":        {"title": [{"text": {"content": symbol}}]},
                "Asset Type":    {"select": {"name": h.get("asset_type", "stock")}},
                "Shares":        {"number": h["shares"]},
                "Avg Cost (USD)":{"number": cost},
                "Price (USD)":   {"number": price},
                "Value (USD)":   {"number": value_usd},
                "P&L %":         {"number": pnl_pct},
            },
        })


def push_crypto(balances, crypto_prices_thb):
    archive_all(DB_CRYPTO)
    for coin, qty in balances.items():
        price_thb = crypto_prices_thb.get(coin) or 0
        notion_post("pages", {
            "parent": {"database_id": DB_CRYPTO},
            "properties": {
                "Coin":        {"title": [{"text": {"content": coin}}]},
                "Total Qty":   {"number": qty},
                "Price (THB)": {"number": price_thb},
                "Value (THB)": {"number": qty * price_thb},
            },
        })


def build():
    if not NOTION_TOKEN:
        print("[notion] NOTION_TOKEN not set, skipping")
        return

    with open(PORTFOLIO_PATH) as f:
        portfolio = json.load(f)
    with open(HISTORY_PATH) as f:
        history = json.load(f)

    holdings = portfolio.get("holdings", {})
    latest = history[-1] if history else None

    # Stock prices
    stock_prices = {}
    if holdings:
        try:
            stock_prices = get_stock_prices(list(holdings.keys()))
            print(f"[notion] fetched {len(stock_prices)} stock prices")
        except Exception as e:
            print(f"[notion] stock prices error: {e}")

    # Binance balances
    binance_balances = {}
    if BINANCE_API_KEY:
        try:
            binance_balances = get_binance_balances(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        except Exception as e:
            print(f"[notion] binance error: {e}")

    # BTC on-chain
    btc_hw = 0.0
    if BTC_ADDRESS:
        try:
            btc_hw = get_btc_balance(BTC_ADDRESS) or 0.0
        except Exception as e:
            print(f"[notion] btc error: {e}")

    # Merge crypto balances
    all_balances = dict(binance_balances)
    if btc_hw > 0:
        all_balances["BTC"] = all_balances.get("BTC", 0) + btc_hw

    # Crypto prices
    crypto_prices_thb = {}
    if all_balances and BINANCE_API_KEY:
        try:
            usd_thb = get_usd_thb_rate(BINANCE_API_KEY, BINANCE_SECRET_KEY)
            for coin in all_balances:
                price = get_crypto_price_thb(BINANCE_API_KEY, BINANCE_SECRET_KEY, coin, usd_thb)
                if price:
                    crypto_prices_thb[coin] = price
        except Exception as e:
            print(f"[notion] crypto prices error: {e}")

    usd_thb = latest["usd_thb_rate"] if latest else 33.0

    # Push to Notion
    if latest:
        push_history_entry(latest)
        print(f"[notion] pushed history entry {latest['ts']}")
        push_stats_page(latest, usd_thb)
        print("[notion] updated live stats page")

    push_holdings(holdings, stock_prices)
    print(f"[notion] pushed {len(holdings)} holdings")

    if all_balances:
        push_crypto(all_balances, crypto_prices_thb)
        print(f"[notion] pushed {len(all_balances)} crypto")

    print("[notion] done")


if __name__ == "__main__":
    build()
