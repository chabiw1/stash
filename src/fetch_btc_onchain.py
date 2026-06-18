import requests


def get_btc_balance(address):
    """
    Fetch BTC balance for a given on-chain address via blockchain.info.
    Returns balance in BTC (float) or None on error.
    """
    url = f"https://blockchain.info/balance?active={address}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        data = response.json()
        balance_sat = data[address]["final_balance"]
        return balance_sat / 100_000_000  # satoshi → BTC
    return None
