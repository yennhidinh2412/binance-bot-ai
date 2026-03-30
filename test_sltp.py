#!/usr/bin/env python3
"""
Quick test: check open orders and positions on testnet
"""
import sys
sys.path.insert(0, '/Users/vuthanhtrung/Downloads/Bot AI/Bot AI')
from binance_client import BinanceFuturesClient

c = BinanceFuturesClient()
cli = c.client

print("=== POSITIONS ===")
positions = cli.futures_position_information()
active = [p for p in positions if float(p['positionAmt']) != 0]
for p in active:
    sym = p['symbol']
    amt = float(p['positionAmt'])
    entry = float(p['entryPrice'])
    mark = float(p['markPrice'])
    side = 'LONG' if amt > 0 else 'SHORT'
    pnl = float(p.get('unrealizedProfit', p.get('unRealizedProfit', 0)))
    print(f"  {sym} {side}: entry=${entry:.4f} mark=${mark:.4f} pnl=${pnl:.2f}")

print("\n=== ALL OPEN ORDERS ===")
orders = cli.futures_get_open_orders()
if not orders:
    print("  [NONE]")
for o in orders:
    print(f"  {o['symbol']} {o['type']} side={o['side']} "
          f"stop=${o.get('stopPrice','--')} qty={o['origQty']} "
          f"status={o['status']}")

print(f"\nTotal orders: {len(orders)}")
print("\n=== ACTUALLY PLACING TEST ORDERS (will try SL for SOLUSDT) ===")
for p in active:
    sym = p['symbol']
    amt = float(p['positionAmt'])
    entry = float(p['entryPrice'])
    mark = float(p.get('markPrice', entry))
    is_long = amt > 0
    qty = abs(amt)
    side = 'LONG' if is_long else 'SHORT'
    pos_side = 'LONG' if is_long else 'SHORT'
    order_side = 'SELL' if is_long else 'BUY'
    if is_long:
        sl = round(entry * (1 - 0.015), 2)
        tp = round(mark * 1.03, 2)
    else:
        sl = round(entry * 1.015, 2)
        tp = round(mark * 0.97, 2)

    print(f"\n  Placing SL for {sym} {side}:")
    print(f"    side={order_side} stopPrice={sl} qty={qty} positionSide={pos_side}")
    try:
        result = cli.futures_create_order(
            symbol=sym,
            side=order_side,
            type='STOP_MARKET',
            stopPrice=sl,
            quantity=qty,
            positionSide=pos_side
        )
        oid = result.get('orderId') or result.get('clientOrderId') or result.get('orderID')
        status = result.get('status')
        print(f"    ✅ SL response keys: {list(result.keys())}")
        print(f"    ✅ SL orderId={oid} status={status}")
        if not oid:
            print(f"    ⚠️  FULL RESULT: {result}")
    except Exception as e:
        print(f"    ❌ SL ERROR: {e}")

    print(f"\n  Placing TP for {sym} {side}:")
    print(f"    side={order_side} stopPrice={tp} qty={qty} positionSide={pos_side}")
    try:
        result = cli.futures_create_order(
            symbol=sym,
            side=order_side,
            type='TAKE_PROFIT_MARKET',
            stopPrice=tp,
            quantity=qty,
            positionSide=pos_side
        )
        oid = result.get('orderId') or result.get('clientOrderId')
        status = result.get('status')
        print(f"    ✅ TP response keys: {list(result.keys())}")
        print(f"    ✅ TP orderId={oid} status={status}")
        if not oid:
            print(f"    ⚠️  FULL RESULT: {result}")
    except Exception as e:
        print(f"    ❌ TP ERROR: {e}")

print("\n=== CHECKING ALGO ORDERS (correct API) ===")
try:
    algo_orders = cli.futures_get_open_orders(conditional=True)
    if not algo_orders:
        print("  [NONE]")
    else:
        for o in algo_orders:
            print(
                f"  algoId={o['algoId']} {o['symbol']} "
                f"{o['orderType']} side={o['side']} "
                f"trigger={o['triggerPrice']} "
                f"qty={o['quantity']} status={o['algoStatus']}"
            )
    print(f"  Total algo orders: {len(algo_orders)}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== SOLUSDT ALGO ORDERS (read-only, không cancel) ===")
try:
    sol_orders = cli.futures_get_open_orders(
        conditional=True, symbol='SOLUSDT'
    )
    if sol_orders:
        for o in sol_orders:
            print(
                f"  algoId={o['algoId']} {o['orderType']} "
                f"trigger={o['triggerPrice']} positionSide={o.get('positionSide','?')} "
                f"status={o['algoStatus']}"
            )
    else:
        print("  (none)")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== OPEN ORDERS AFTER PLACING (conditional=True) ===")
orders2 = cli.futures_get_open_orders(conditional=True)
if not orders2:
    print("  [NONE - all orders cancelled or error]")
for o in orders2[:10]:  # show first 10
    print(f"  algoId={o['algoId']} {o['symbol']} {o['orderType']} "
          f"trigger={o['triggerPrice']} status={o['algoStatus']}")
print(f"  Total: {len(orders2)} open algo orders")

import urllib.request
import json as _json
print("\n=== WEB API /api/positions (SL/TP should now show) ===")
try:
    url = 'http://localhost:8080/api/positions'
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = _json.loads(resp.read())
    for p in data.get('positions', []):
        print(
            f"  {p['symbol']} {p['side']}: "
            f"SL={'${:.2f}'.format(p['stopLoss']) if p['stopLoss'] else '—'} "
            f"TP={'${:.2f}'.format(p['takeProfit']) if p['takeProfit'] else '—'}"
        )
    if not data.get('positions'):
        print(f"  (none) error={data.get('error','')}")
except Exception as e:
    print(f"  ERROR: {e}")
