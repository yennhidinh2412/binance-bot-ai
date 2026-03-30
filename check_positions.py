"""Quick check positions"""
from binance_client import BinanceFuturesClient

client = BinanceFuturesClient()

print("\n" + "="*80)
print("📊 CURRENT POSITIONS")
print("="*80)

account = client.get_account_info()
print(f"\n💰 Balance: ${float(account['totalWalletBalance']):.2f} USDT")
print(f"💵 Available: ${float(account['availableBalance']):.2f} USDT")
print(f"📈 Unrealized PnL: ${float(account['totalUnrealizedProfit']):+.2f} USDT\n")

positions = client.get_open_positions()

open_positions = [p for p in positions if float(p['positionAmt']) != 0]

print(f"Open Positions: {len(open_positions)}\n")

if open_positions:
    for pos in open_positions:
        symbol = pos['symbol']
        amt = float(pos['positionAmt'])
        side = 'LONG' if amt > 0 else 'SHORT'
        entry = float(pos['entryPrice'])
        mark = float(pos['markPrice'])
        pnl = float(pos['unRealizedProfit'])
        pnl_pct = (pnl / (abs(amt) * entry)) * 100 if amt * entry != 0 else 0
        
        pnl_symbol = "🟢" if pnl >= 0 else "🔴"
        
        print(f"{pnl_symbol} {symbol} {side}:")
        print(f"   Amount: {abs(amt)}")
        print(f"   Entry: ${entry:.2f}")
        print(f"   Mark: ${mark:.2f}")
        print(f"   PnL: ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        print()
else:
    print("No open positions")

print("="*80)
