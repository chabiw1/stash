import time
import hmac
import hashlib
import requests
import yfinance as yf


BASE_URL = "https://api.binance.th"  # Thai exchange, not .com


def get_binance_balances(api_key, secret_key):
    """Return dict of {asset: total_qty} for non-zero balances."""
    timestamp = int(time.time() * 1000)
    params = f"timestamp={timestamp}"
    signature = hmac.new(
        secret_key.encode(), params.encode(), hashlib.sha256
    ).hexdigest()
    url = f"{BASE_URL}/api/v1/account?{params}&signature={signature}"
    headers = {"X-MBX-APIKEY": api_key}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    balances = r.json()["balances"]
    return {
        b["asset"]: float(b["free"]) + float(b["locked"])
        for b in balances
        if float(b["free"]) + float(b["locked"]) > 0
    }


def get_binance_price_thb(api_key, secret_key, symbol):
    """Get price in THB for a symbol like BTCTHB, ETHTHB, USDTTHB."""
    url = f"{BASE_URL}/api/v1/ticker/price?symbol={symbol}"
    headers = {"X-MBX-APIKEY": api_key}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])


def get_usd_thb_rate(api_key, secret_key):
    """Return USD → THB rate via USDTTHB pair."""
    return get_binance_price_thb(api_key, secret_key, "USDTTHB")


def get_crypto_price_thb(api_key, secret_key, coin, usd_thb):
    """
    Get crypto price in THB.
    Tries {COIN}THB first; falls back to {COIN}USDT × usd_thb.
    Returns None if both fail.
    """
    try:
        return get_binance_price_thb(api_key, secret_key, f"{coin}THB")
    except Exception:
        pass
    try:
        usdt_price = get_binance_price_thb(api_key, secret_key, f"{coin}USDT")
        return usdt_price * usd_thb
    except Exception:
        return None


def get_stock_prices(symbols):
    """
    Fetch latest USD prices for a list of stock/ETF tickers via yfinance.
    Returns dict {symbol: price_usd or None}.
    """
    prices = {}
    for sym in symbols:
        try:
            prices[sym] = yf.Ticker(sym).fast_info.last_price
        except Exception:
            prices[sym] = None
    return prices
