"""
cleanup_sltp.py — Purge all accumulated stale SL/TP algo orders, then place fresh ones.
Run: .venv/bin/python3 cleanup_sltp.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

from binance_client import BinanceFuturesClient

bc = BinanceFuturesClient()
client = bc.client

# ── 1. List all algo orders ──────────────────────────────────────────────────
print("\n=== STEP 1: List all conditional algo orders ===")
all_orders = client.futures_get_open_orders(conditional=True)
print(f"  Found {len(all_orders)} algo orders total")

# Show count by symbol
from collections import Counter
counts = Counter(o['symbol'] for o in all_orders)
for sym, cnt in sorted(counts.items()):
    print(f"    {sym}: {cnt} orders")

# ── 2. Cancel ALL of them ────────────────────────────────────────────────────
print("\n=== STEP 2: Cancel ALL algo orders ===")
cancelled = 0
errors = 0
for o in all_orders:
    try:
        client.futures_cancel_order(symbol=o['symbol'], algoId=o['algoId'])
        cancelled += 1
    except Exception as e:
        print(f"  ⚠️  Failed to cancel algoId={o['algoId']} {o['symbol']}: {e}")
        errors += 1

print(f"  ✅ Cancelled: {cancelled}  ❌ Errors: {errors}")

# ── 3. Verify clean ──────────────────────────────────────────────────────────
remaining = client.futures_get_open_orders(conditional=True)
print(f"  Remaining algo orders: {len(remaining)}")

# ── 4. Fetch active positions ────────────────────────────────────────────────
print("\n=== STEP 3: Active positions ===")
account = client.futures_account()
positions = [
    p for p in account.get('positions', [])
    if abs(float(p.get('positionAmt', 0))) > 0
]

if not positions:
    print("  No active positions — nothing to protect.")
    sys.exit(0)

for p in positions:
    sym = p['symbol']
    amt = float(p['positionAmt'])
    entry = float(p['entryPrice'])
    side = 'LONG' if amt > 0 else 'SHORT'
    print(f"  {sym} {side}: entry=${entry:.4f} qty={abs(amt)}")

# ── 5. Get exchange info for precision ──────────────────────────────────────
print("\n=== STEP 4: Placing fresh SL/TP ===")
exchange_info = client.futures_exchange_info()
sym_info = {s['symbol']: s for s in exchange_info['symbols']}

import math

def get_price_precision(symbol):
    filters = sym_info.get(symbol, {}).get('filters', [])
    for f in filters:
        if f['filterType'] == 'PRICE_FILTER':
            tick = float(f['tickSize'])
            return max(0, -int(math.log10(tick)))
    return 2

def get_qty_precision(symbol):
    filters = sym_info.get(symbol, {}).get('filters', [])
    for f in filters:
        if f['filterType'] == 'LOT_SIZE':
            step = float(f['stepSize'])
            return max(0, -int(math.log10(step)))
    return 3

# SL/TP percentages (same as smart_bot_engine defaults)
SL_PCT = 0.02   # 2% stop loss
TP_PCT = 0.05   # 5% take profit

placed = 0
failed = 0

for p in positions:
    sym = p['symbol']
    amt = float(p['positionAmt'])
    entry = float(p['entryPrice'])
    qty = abs(amt)
    side = 'LONG' if amt > 0 else 'SHORT'
    pos_side = side  # LONG or SHORT

    price_prec = get_price_precision(sym)
    qty_prec = get_qty_precision(sym)
    qty_str = str(round(qty, qty_prec))

    if side == 'LONG':
        sl_price = round(entry * (1 - SL_PCT), price_prec)
        tp_price = round(entry * (1 + TP_PCT), price_prec)
        order_side = 'SELL'
    else:
        sl_price = round(entry * (1 + SL_PCT), price_prec)
        tp_price = round(entry * (1 - TP_PCT), price_prec)
        order_side = 'BUY'

    # Place SL
    try:
        r = client.futures_create_order(
            symbol=sym,
            side=order_side,
            type='STOP_MARKET',
            stopPrice=sl_price,
            quantity=qty_str,
            positionSide=pos_side,
        )
        sl_id = r.get('algoId') or r.get('orderId')
        print(f"  ✅ {sym} {side} SL placed: trigger=${sl_price} algoId={sl_id}")
        placed += 1
    except Exception as e:
        print(f"  ❌ {sym} {side} SL FAILED: {e}")
        failed += 1

    # Place TP
    try:
        r = client.futures_create_order(
            symbol=sym,
            side=order_side,
            type='TAKE_PROFIT_MARKET',
            stopPrice=tp_price,
            quantity=qty_str,
            positionSide=pos_side,
        )
        tp_id = r.get('algoId') or r.get('orderId')
        print(f"  ✅ {sym} {side} TP placed: trigger=${tp_price} algoId={tp_id}")
        placed += 1
    except Exception as e:
        print(f"  ❌ {sym} {side} TP FAILED: {e}")
        failed += 1

print(f"\n  Placed: {placed}  Failed: {failed}")

# ── 6. Verify via web API ────────────────────────────────────────────────────
print("\n=== STEP 5: Verify via /api/positions ===")
import urllib.request, json, time
time.sleep(1)
try:
    url = 'http://localhost:8080/api/positions'
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read())
    for p in data.get('positions', []):
        sl = p.get('stopLoss', 0)
        tp = p.get('takeProfit', 0)
        sl_str = f"${sl:.2f}" if sl else "—"
        tp_str = f"${tp:.2f}" if tp else "—"
        print(f"  {p['symbol']} {p['side']}: SL={sl_str}  TP={tp_str}")
    if not data.get('positions'):
        print(f"  (none) error={data.get('error','')}")
except Exception as e:
    print(f"  Web API check failed: {e}\n  (server may be restarting)")

print("\n=== Done. Refresh your dashboard. ===")
