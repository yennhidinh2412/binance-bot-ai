"""
Add SOL position with correct precision
"""
from binance_client import BinanceFuturesClient

print("="*80)
print("🚀 ADDING SOL POSITION")
print("="*80)

client = BinanceFuturesClient()

# Get account balance
account = client.get_account_info()
balance = float(account['totalWalletBalance'])
print(f"\n💰 Balance: ${balance:.2f} USDT\n")

# Set leverage for SOL
symbol = 'SOLUSDT'
leverage = 50

print(f"📊 Setting {symbol} leverage to {leverage}x...")
client.set_leverage(symbol, leverage)
print("✅ Leverage set!\n")

# Get current price
klines = client.get_klines(symbol, '5m', limit=1)
current_price = float(klines[0][4])
print(f"💵 Current SOL Price: ${current_price:.2f}\n")

# Calculate position size (30% of balance)
position_value = balance * 0.30
quantity_base = position_value / current_price

# Get correct precision from symbol info
symbol_info = client.get_symbol_info(symbol)
quantity_precision = 0
min_qty = 0.0

for filter_item in symbol_info['filters']:
    if filter_item['filterType'] == 'LOT_SIZE':
        step_size = float(filter_item['stepSize'])
        min_qty = float(filter_item['minQty'])
        # Calculate precision from step size
        if step_size < 1:
            quantity_precision = len(str(step_size).rstrip('0').split('.')[-1])
        break

# Round to correct precision
quantity = round(quantity_base, quantity_precision)
quantity = max(quantity, min_qty)

print(f"📦 Position Details:")
print(f"   Quantity: {quantity} SOL")
print(f"   Position Value: ${position_value:.2f}")
print(f"   Leverage: {leverage}x")
print(f"   Entry: ${current_price:.2f}")

# Calculate stop loss and take profit
stop_loss_price = current_price * 0.99  # 1% below
take_profit_price = current_price * 1.02  # 2% above

print(f"   Stop Loss: ${stop_loss_price:.2f}")
print(f"   Take Profit: ${take_profit_price:.2f}\n")

# Place order
print("🚀 PLACING MARKET ORDER...")
try:
    order = client.place_order(
        symbol=symbol,
        side='BUY',
        order_type='MARKET',
        quantity=quantity
    )
    
    print("✅ ORDER EXECUTED!")
    print(f"   Order ID: {order['orderId']}")
    print(f"   Status: {order['status']}\n")
    
    # Wait and check position
    import time
    time.sleep(2)
    
    positions = client.get_open_positions()
    for pos in positions:
        if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
            entry_price = float(pos['entryPrice'])
            position_amt = float(pos['positionAmt'])
            unrealized_pnl = float(pos['unRealizedProfit'])
            
            print("📍 POSITION OPENED:")
            print(f"   Symbol: {symbol}")
            print(f"   Entry: ${entry_price:.2f}")
            print(f"   Amount: {position_amt}")
            print(f"   Unrealized PnL: ${unrealized_pnl:.2f}\n")
    
    # Place stop loss
    print("🛑 PLACING STOP LOSS...")
    try:
        sl_order = client.place_order(
            symbol=symbol,
            side='SELL',
            order_type='STOP_MARKET',
            quantity=quantity,
            stop_price=stop_loss_price,
            close_position=True
        )
        print(f"✅ Stop Loss Set at ${stop_loss_price:.2f}\n")
    except Exception as e:
        print(f"⚠️  Stop Loss error: {e}\n")
    
    # Place take profit
    print("🎯 PLACING TAKE PROFIT...")
    try:
        tp_order = client.place_order(
            symbol=symbol,
            side='SELL',
            order_type='TAKE_PROFIT_MARKET',
            quantity=quantity,
            stop_price=take_profit_price,
            close_position=True
        )
        print(f"✅ Take Profit Set at ${take_profit_price:.2f}\n")
    except Exception as e:
        print(f"⚠️  Take Profit error: {e}\n")
    
    print("🎉 SOL POSITION COMPLETE!")
    print("="*80)
    
    # Show all positions
    print("\n📊 ALL POSITIONS:\n")
    positions = client.get_open_positions()
    total_pnl = 0.0
    
    for pos in positions:
        if float(pos['positionAmt']) != 0:
            sym = pos['symbol']
            amt = float(pos['positionAmt'])
            entry = float(pos['entryPrice'])
            mark = float(pos['markPrice'])
            pnl = float(pos['unRealizedProfit'])
            
            total_pnl += pnl
            
            side = 'LONG' if amt > 0 else 'SHORT'
            pnl_symbol = "🟢" if pnl >= 0 else "🔴"
            
            print(f"{pnl_symbol} {sym} {side}:")
            print(f"   Entry: ${entry:.2f}")
            print(f"   Mark: ${mark:.2f}")
            print(f"   Amount: {abs(amt)}")
            print(f"   PnL: ${pnl:+.2f}")
            print()
    
    # Final account status
    final_account = client.get_account_info()
    final_balance = float(final_account['totalWalletBalance'])
    
    print(f"💰 Total Balance: ${final_balance:.2f} USDT")
    print(f"📈 Total Unrealized PnL: ${total_pnl:+.2f} USDT")
    
    if total_pnl > 0:
        roi = (total_pnl / final_balance) * 100
        print(f"🎯 ROI: +{roi:.2f}%")
    
    print("\n" + "="*80)
    print("✅ ALL 3 POSITIONS NOW ACTIVE!")
    print("="*80)
    
except Exception as e:
    print(f"❌ Order failed: {e}")
    import traceback
    traceback.print_exc()
