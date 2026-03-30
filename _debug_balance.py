import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from config import Config
from binance_client import BinanceFuturesClient

print("TESTNET:", Config._is_testnet)
print("API KEY (first 8):", (Config.BINANCE_API_KEY or '')[:8])

c = BinanceFuturesClient(Config.BINANCE_API_KEY, Config.BINANCE_SECRET_KEY, testnet=False)

# Test 1: get_account_info
print("\n--- get_account_info ---")
info = c.get_account_info()
if info:
    print("totalWalletBalance:", info.get('totalWalletBalance'))
    print("availableBalance:", info.get('availableBalance'))
    print("totalUnrealizedProfit:", info.get('totalUnrealizedProfit'))
    assets = [a for a in info.get('assets', []) if float(a.get('walletBalance', 0)) > 0]
    print("assets with balance:", assets)
else:
    print("ERROR: info is None")

# Test 2: check_balance endpoint logic
print("\n--- /api/balance raw ---")
try:
    account = c.client.futures_account()
    print("totalWalletBalance:", account.get('totalWalletBalance'))
    print("availableBalance:", account.get('availableBalance'))
    print("totalUnrealizedProfit:", account.get('totalUnrealizedProfit'))
    # Check if USDC-M
    assets = [a for a in account.get('assets', []) if float(a.get('walletBalance', 0)) > 0]
    print("Non-zero assets:", assets[:3])
except Exception as e:
    print("ERROR:", e)
