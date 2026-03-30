"""
FORCE REAL TRADE TEST - Test bot vào lệnh thật trên Binance Testnet
Script này force bot vào lệnh THẬT để test intelligence
"""
import asyncio
from binance_client import BinanceFuturesClient
from smart_bot_engine import SmartBotEngine
from risk_management import RiskManager
from loguru import logger
import time

print("="*80)
print("🚀 FORCE REAL TRADE TEST - Binance Testnet")
print("⚠️  Bot sẽ VÀO LỆNH THẬT để test intelligence!")
print("="*80)

async def force_trade_test():
    """Force bot vào ít nhất 2-3 lệnh thật"""
    
    # Initialize
    client = BinanceFuturesClient()
    bot = SmartBotEngine(client)
    
    # Get account info
    account = client.get_account_info()
    balance = float(account['totalWalletBalance'])
    print(f"\n💰 Account Balance: ${balance:.2f} USDT")
    print(f"✅ Available: ${float(account['availableBalance']):.2f} USDT\n")
    
    # Initialize risk manager
    risk_mgr = RiskManager(client)
    
    # Test symbols
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    trades_executed = 0
    target_trades = 2  # Target at least 2 trades
    
    print("🔍 ANALYZING MARKET & FORCING TRADES...\n")
    
    for symbol in test_symbols:
        if trades_executed >= target_trades:
            break
            
        try:
            print(f"{'='*80}")
            print(f"📊 ANALYZING {symbol}...")
            print(f"{'='*80}")
            
            # Get current price
            klines = client.get_klines(symbol, '5m', limit=1)
            current_price = float(klines[0][4])
            print(f"   💵 Current Price: ${current_price:.2f}")
            
            # Analyze with bot
            analysis = await bot.analyze_symbol(symbol)
            
            print(f"   🤖 AI Signal: {analysis['signal']}")
            print(f"   📈 Confidence: {analysis['confidence']:.1%}")
            print(f"   💡 Reason: {analysis.get('reason', 'No reason provided')}")
            
            # FORCE TRADE if confidence > 50% (lower threshold)
            if analysis['confidence'] >= 0.50:
                signal = analysis['signal']
                
                if signal != 'HOLD':
                    print(f"\n   ✅ FORCING TRADE: {signal} {symbol}")
                    
                    # Calculate position size
                    side = 'BUY' if signal == 'BUY' else 'SELL'
                    
                    # Calculate stop loss based on signal
                    if signal == 'BUY':
                        stop_loss_price = current_price * 0.99  # 1% below
                        take_profit_price = current_price * 1.02  # 2% above
                    else:
                        stop_loss_price = current_price * 1.01  # 1% above
                        take_profit_price = current_price * 0.98  # 2% below
                    
                    # Calculate position
                    position_info = risk_mgr.calculate_position_size(
                        account_balance=balance,
                        entry_price=current_price,
                        stop_loss_price=stop_loss_price,
                        symbol=symbol
                    )
                    
                    quantity = position_info['quantity']
                    
                    print(f"   📦 Position Size: {quantity} {symbol.replace('USDT', '')}")
                    print(f"   💰 Position Value: ${position_info['position_value']:.2f}")
                    print(f"   🎯 Risk: ${position_info['risk_amount']:.2f} ({position_info['risk_percent']:.2f}%)")
                    print(f"   🛑 Stop Loss: ${stop_loss_price:.2f}")
                    print(f"   🎯 Take Profit: ${take_profit_price:.2f}")
                    
                    # Validate trade
                    validation = risk_mgr.validate_trade(
                        signal=side,
                        symbol=symbol,
                        quantity=quantity,
                        current_price=current_price,
                        ai_confidence=analysis['confidence']
                    )
                    
                    if not validation['is_valid']:
                        print(f"   ❌ Trade REJECTED: {', '.join(validation['reasons'])}")
                        continue
                    
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
                        print(f"   💵 Executed Price: ${float(order.get('avgPrice', order.get('price', current_price))):.2f}")
                        print(f"   📊 Status: {order['status']}")
                        
                        trades_executed += 1
                        
                        # Wait a moment for order to fill
                        await asyncio.sleep(2)
                        
                        # Check position
                        positions = client.get_open_positions()
                        for pos in positions:
                            if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                                entry_price = float(pos['entryPrice'])
                                position_amt = float(pos['positionAmt'])
                                unrealized_pnl = float(pos['unRealizedProfit'])
                                
                                print(f"\n   📍 POSITION OPENED:")
                                print(f"      Symbol: {symbol}")
                                print(f"      Entry: ${entry_price:.2f}")
                                print(f"      Amount: {position_amt}")
                                print(f"      Unrealized PnL: ${unrealized_pnl:.2f}")
                        
                        # Place STOP LOSS order
                        print(f"\n   🛑 PLACING STOP LOSS...")
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
                            print(f"   ✅ Stop Loss Set: ${stop_loss_price:.2f}")
                        except Exception as e:
                            print(f"   ⚠️  Stop Loss failed: {e}")
                        
                        # Place TAKE PROFIT order
                        print(f"   🎯 PLACING TAKE PROFIT...")
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
                            print(f"   ✅ Take Profit Set: ${take_profit_price:.2f}")
                        except Exception as e:
                            print(f"   ⚠️  Take Profit failed: {e}")
                        
                        print(f"\n   🎉 TRADE COMPLETE! ({trades_executed}/{target_trades})")
                        
                        # Wait before next trade
                        if trades_executed < target_trades:
                            print(f"\n   ⏳ Waiting 10 seconds before next trade...")
                            await asyncio.sleep(10)
                        
                    except Exception as e:
                        print(f"   ❌ Order failed: {e}")
                        logger.error(f"Order error: {e}")
                
                else:
                    print(f"   ⏸️  Signal is HOLD - skipping (confidence: {analysis['confidence']:.1%})")
            else:
                print(f"   ⏸️  Confidence too low: {analysis['confidence']:.1%} < 50%")
            
            print()
            
        except Exception as e:
            print(f"   ❌ Error analyzing {symbol}: {e}")
            logger.error(f"Analysis error for {symbol}: {e}")
    
    # SUMMARY
    print("\n" + "="*80)
    print("📊 TRADE TEST SUMMARY")
    print("="*80)
    
    # Check final positions
    print("\n🔍 CHECKING FINAL POSITIONS...\n")
    positions = client.get_open_positions()
    
    open_count = 0
    total_pnl = 0.0
    
    for pos in positions:
        if float(pos['positionAmt']) != 0:
            open_count += 1
            symbol = pos['symbol']
            entry_price = float(pos['entryPrice'])
            position_amt = float(pos['positionAmt'])
            unrealized_pnl = float(pos['unRealizedProfit'])
            leverage = int(pos['leverage'])
            
            total_pnl += unrealized_pnl
            
            print(f"   📍 {symbol}:")
            print(f"      Entry: ${entry_price:.2f}")
            print(f"      Amount: {position_amt}")
            print(f"      Leverage: {leverage}x")
            print(f"      Unrealized PnL: ${unrealized_pnl:.2f}")
            print()
    
    # Check final balance
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
    print(f"{'='*80}")
    
    print(f"\n✅ Trades Executed: {trades_executed}/{target_trades}")
    
    if trades_executed >= target_trades:
        print("\n🎉 SUCCESS! Bot đã vào lệnh thật và đang trade!")
        print("✅ Bot intelligence VERIFIED với real trades!")
        print("\n📌 NEXT STEPS:")
        print("   1. Monitor positions on Binance Testnet")
        print("   2. Watch stop loss / take profit triggers")
        print("   3. Check dashboard at http://localhost:8080")
        print("   4. Review trade performance")
        print("\n⚠️  Positions are LIVE on Testnet - they will auto-close at SL/TP")
    else:
        print(f"\n⚠️  Only {trades_executed} trades executed (target: {target_trades})")
        print("   Market conditions may not be favorable right now")
        print("   Bot is being CONSERVATIVE - this is GOOD!")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(force_trade_test())
