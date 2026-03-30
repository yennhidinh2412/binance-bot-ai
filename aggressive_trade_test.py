"""
AGGRESSIVE TRADE TEST - High Leverage & Max Position
Test bot với đòn bẩy cao và khối lượng lớn để xem performance
"""
import asyncio
from binance_client import BinanceFuturesClient
from smart_bot_engine import SmartBotEngine
from risk_management import RiskManager
from loguru import logger

print("="*80)
print("🚀 AGGRESSIVE TRADE TEST - HIGH LEVERAGE")
print("⚠️  ĐANG TEST VỚI ĐÒN BẨY CAO & KHỐI LƯỢNG LỚN!")
print("="*80)

async def aggressive_trade_test():
    """Test bot với đòn bẩy cao và position lớn"""
    
    # Initialize
    client = BinanceFuturesClient()
    bot = SmartBotEngine(client)
    
    # Get account info
    account = client.get_account_info()
    balance = float(account['totalWalletBalance'])
    print(f"\n💰 Account Balance: ${balance:.2f} USDT")
    print(f"✅ Available: ${float(account['availableBalance']):.2f} USDT\n")
    
    # Risk manager
    risk_mgr = RiskManager(client)
    
    # AGGRESSIVE SETTINGS
    leverage_settings = {
        'BTCUSDT': 100,  # 100x leverage
        'ETHUSDT': 100,  # 100x leverage
        'SOLUSDT': 50    # 50x leverage
    }
    
    # Use 30% of balance per trade (AGGRESSIVE!)
    position_size_percent = 0.30  # 30% of balance
    
    print("⚙️  AGGRESSIVE SETTINGS:")
    print(f"   BTC Leverage: {leverage_settings['BTCUSDT']}x")
    print(f"   ETH Leverage: {leverage_settings['ETHUSDT']}x")
    print(f"   SOL Leverage: {leverage_settings['SOLUSDT']}x")
    print(f"   Position Size: {position_size_percent*100}% of balance per trade")
    print(f"   Stop Loss: 1% (tight)")
    print(f"   Take Profit: 2% (conservative)\n")
    
    trades_executed = 0
    target_trades = 3  # Vào cả 3 lệnh
    
    print("🔍 FORCING AGGRESSIVE TRADES...\n")
    
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    for symbol in test_symbols:
        try:
            print(f"{'='*80}")
            print(f"📊 ANALYZING {symbol}...")
            print(f"{'='*80}")
            
            # Set leverage first
            leverage = leverage_settings[symbol]
            try:
                client.set_leverage(symbol, leverage)
                print(f"   ✅ Leverage set to {leverage}x")
            except Exception as e:
                print(f"   ⚠️  Leverage setting: {e}")
            
            # Get current price
            klines = client.get_klines(symbol, '5m', limit=1)
            current_price = float(klines[0][4])
            print(f"   💵 Current Price: ${current_price:.2f}")
            
            # Analyze with bot
            analysis = await bot.analyze_symbol(symbol)
            
            print(f"   🤖 AI Signal: {analysis['signal']}")
            print(f"   📈 Confidence: {analysis['confidence']:.1%}")
            
            # FORCE TRADE REGARDLESS (for testing)
            # If HOLD, pick a direction based on recent trend
            if analysis['signal'] == 'HOLD':
                # Check last 5 candles for trend
                klines_5 = client.get_klines(symbol, '5m', limit=5)
                prices = [float(k[4]) for k in klines_5]
                trend = prices[-1] - prices[0]
                
                if trend > 0:
                    signal = 'BUY'
                    print(f"   📈 Market trending UP → Forcing LONG")
                else:
                    signal = 'SELL'
                    print(f"   📉 Market trending DOWN → Forcing SHORT")
            else:
                signal = analysis['signal']
            
            print(f"\n   ✅ FORCING TRADE: {signal} {symbol} with {leverage}x leverage")
            
            # Calculate position size (30% of balance)
            position_value = balance * position_size_percent
            
            # Calculate quantity based on leverage
            # With leverage, we can control larger position
            quantity_base = position_value / current_price
            
            # Get correct precision from symbol info
            symbol_info = client.get_symbol_info(symbol)
            quantity_precision = 0
            for filter_item in symbol_info['filters']:
                if filter_item['filterType'] == 'LOT_SIZE':
                    step_size = float(filter_item['stepSize'])
                    # Calculate precision from step size
                    if step_size < 1:
                        quantity_precision = len(str(step_size).rstrip('0').split('.')[-1])
                    break
            
            # Round to correct precision
            quantity = round(quantity_base, quantity_precision)
            
            # Ensure minimum quantity
            for filter_item in symbol_info['filters']:
                if filter_item['filterType'] == 'LOT_SIZE':
                    min_qty = float(filter_item['minQty'])
                    quantity = max(quantity, min_qty)
                    break
            
            # Calculate stop loss and take profit
            side = 'BUY' if signal == 'BUY' else 'SELL'
            
            if side == 'BUY':
                stop_loss_price = current_price * 0.99  # 1% below
                take_profit_price = current_price * 1.02  # 2% above
            else:
                stop_loss_price = current_price * 1.01  # 1% above
                take_profit_price = current_price * 0.98  # 2% below
            
            print(f"   📦 Position Details:")
            print(f"      Quantity: {quantity} {symbol.replace('USDT', '')}")
            print(f"      Position Value: ${position_value:.2f}")
            print(f"      Leverage: {leverage}x")
            print(f"      Entry: ${current_price:.2f}")
            print(f"      Stop Loss: ${stop_loss_price:.2f}")
            print(f"      Take Profit: ${take_profit_price:.2f}")
            
            # Calculate potential profit/loss with leverage
            if side == 'BUY':
                potential_profit = quantity * (take_profit_price - current_price) * leverage
                potential_loss = quantity * (current_price - stop_loss_price) * leverage
            else:
                potential_profit = quantity * (current_price - take_profit_price) * leverage
                potential_loss = quantity * (stop_loss_price - current_price) * leverage
            
            print(f"      💰 Potential Profit: ${potential_profit:.2f}")
            print(f"      💸 Potential Loss: ${potential_loss:.2f}")
            print(f"      Risk/Reward: 1:{potential_profit/potential_loss:.2f}")
            
            # PLACE MARKET ORDER
            print(f"\n   🚀 PLACING MARKET ORDER...")
            try:
                order = client.place_order(
                    symbol=symbol,
                    side=side,
                    order_type='MARKET',
                    quantity=quantity
                )
                
                print(f"   ✅ ORDER EXECUTED!")
                print(f"   📝 Order ID: {order['orderId']}")
                executed_price = float(order.get('avgPrice', order.get('price', current_price)))
                print(f"   💵 Executed Price: ${executed_price:.2f}")
                print(f"   📊 Status: {order['status']}")
                
                trades_executed += 1
                
                # Wait for order to fill
                await asyncio.sleep(2)
                
                # Check position
                positions = client.get_open_positions()
                for pos in positions:
                    if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                        entry_price = float(pos['entryPrice'])
                        position_amt = float(pos['positionAmt'])
                        unrealized_pnl = float(pos['unRealizedProfit'])
                        leverage_used = int(pos.get('leverage', leverage))  # Use set leverage if not in response
                        
                        print(f"\n   📍 POSITION OPENED:")
                        print(f"      Symbol: {symbol}")
                        print(f"      Side: {'LONG' if position_amt > 0 else 'SHORT'}")
                        print(f"      Entry: ${entry_price:.2f}")
                        print(f"      Amount: {abs(position_amt)}")
                        print(f"      Leverage: {leverage_used}x")
                        print(f"      Unrealized PnL: ${unrealized_pnl:.2f}")
                
                # Place STOP LOSS
                print(f"\n   🛑 PLACING STOP LOSS at ${stop_loss_price:.2f}...")
                try:
                    sl_side = 'SELL' if side == 'BUY' else 'BUY'
                    sl_order = client.place_order(
                        symbol=symbol,
                        side=sl_side,
                        order_type='STOP_MARKET',
                        quantity=quantity,
                        stop_price=stop_loss_price,
                        close_position=True
                    )
                    print(f"   ✅ Stop Loss Set!")
                except Exception as e:
                    print(f"   ⚠️  Stop Loss error: {e}")
                
                # Place TAKE PROFIT
                print(f"   🎯 PLACING TAKE PROFIT at ${take_profit_price:.2f}...")
                try:
                    tp_side = 'SELL' if side == 'BUY' else 'BUY'
                    tp_order = client.place_order(
                        symbol=symbol,
                        side=tp_side,
                        order_type='TAKE_PROFIT_MARKET',
                        quantity=quantity,
                        stop_price=take_profit_price,
                        close_position=True
                    )
                    print(f"   ✅ Take Profit Set!")
                except Exception as e:
                    print(f"   ⚠️  Take Profit error: {e}")
                
                print(f"\n   🎉 TRADE #{trades_executed} COMPLETE!")
                
                # Wait before next trade
                if trades_executed < target_trades:
                    print(f"\n   ⏳ Waiting 5 seconds before next trade...")
                    await asyncio.sleep(5)
                
            except Exception as e:
                print(f"   ❌ Order failed: {e}")
                logger.error(f"Order error: {e}")
            
            print()
            
        except Exception as e:
            print(f"   ❌ Error with {symbol}: {e}")
            logger.error(f"Error: {e}")
    
    # FINAL SUMMARY
    print("\n" + "="*80)
    print("📊 AGGRESSIVE TRADE TEST SUMMARY")
    print("="*80)
    
    # Check final positions
    print("\n🔍 CHECKING ALL POSITIONS...\n")
    positions = client.get_open_positions()
    
    open_count = 0
    total_pnl = 0.0
    
    for pos in positions:
        if float(pos['positionAmt']) != 0:
            open_count += 1
            symbol = pos['symbol']
            entry_price = float(pos['entryPrice'])
            mark_price = float(pos['markPrice'])
            position_amt = float(pos['positionAmt'])
            side = 'LONG' if position_amt > 0 else 'SHORT'
            unrealized_pnl = float(pos['unRealizedProfit'])
            leverage = int(pos.get('leverage', 1))  # Default to 1x if not present
            
            total_pnl += unrealized_pnl
            
            pnl_symbol = "🟢" if unrealized_pnl >= 0 else "🔴"
            
            print(f"   {pnl_symbol} {symbol} {side} {leverage}x:")
            print(f"      Entry: ${entry_price:.2f}")
            print(f"      Mark: ${mark_price:.2f}")
            print(f"      Amount: {abs(position_amt)}")
            print(f"      Unrealized PnL: ${unrealized_pnl:+.2f}")
            print()
    
    # Final account status
    final_account = client.get_account_info()
    final_balance = float(final_account['totalWalletBalance'])
    available = float(final_account['availableBalance'])
    
    balance_change = final_balance - balance
    
    print(f"{'='*80}")
    print(f"💰 FINAL ACCOUNT STATUS:")
    print(f"   Initial Balance: ${balance:.2f} USDT")
    print(f"   Final Balance: ${final_balance:.2f} USDT")
    print(f"   Change: ${balance_change:+.2f} USDT")
    print(f"   Available: ${available:.2f} USDT")
    print(f"   Open Positions: {open_count}")
    print(f"   Total Unrealized PnL: ${total_pnl:+.2f} USDT")
    
    if total_pnl > 0:
        roi = (total_pnl / balance) * 100
        print(f"   📈 Current ROI: +{roi:.2f}%")
    elif total_pnl < 0:
        roi = (total_pnl / balance) * 100
        print(f"   📉 Current ROI: {roi:.2f}%")
    
    print(f"{'='*80}")
    
    print(f"\n✅ Trades Executed: {trades_executed}/{target_trades}")
    
    if trades_executed >= target_trades:
        print("\n🎉 ALL TRADES EXECUTED SUCCESSFULLY!")
        print("✅ Bot đã vào đủ 3 lệnh với đòn bẩy cao!")
        print(f"✅ Total positions: {open_count}")
        print(f"💰 Current PnL: ${total_pnl:+.2f}")
        print("\n📌 NEXT STEPS:")
        print("   1. Monitor positions với: python monitor_trading.py")
        print("   2. Check dashboard: http://localhost:8080")
        print("   3. Đợi SL/TP trigger")
        print("\n⚠️  Positions đang LIVE với đòn bẩy cao - theo dõi kỹ!")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(aggressive_trade_test())
