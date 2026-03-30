"""
Start Smart Bot Engine - Auto Trading
Bot tự động với AI độ chính xác cao
"""
import asyncio
import signal
import sys
from datetime import datetime
from loguru import logger
from smart_bot_engine import SmartBotEngine
from binance_client import BinanceFuturesClient

# Global bot instance
bot = None
client = None

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info("\n🛑 Stopping bot...")
    sys.exit(0)

async def main():
    global bot, client
    
    print("\n" + "="*70)
    print("🤖 SMART BOT ENGINE - AUTO TRADING")
    print("="*70)
    
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Initialize
        logger.info("🔧 Initializing Smart Bot Engine...")
        bot = SmartBotEngine()
        client = BinanceFuturesClient()
        
        # Check balance
        account = client.get_account_info()
        balance = float(account['availableBalance'])
        logger.info(f"💰 Available Balance: ${balance:,.2f} USDT")
        
        # Check open positions
        positions = client.get_open_positions()
        logger.info(f"📊 Open Positions: {len(positions)}")
        
        print("\n" + "="*70)
        print("✅ BOT STARTED - Monitoring market...")
        print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
        # Trading symbols
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        # Main loop
        cycle = 0
        while True:
            cycle += 1
            print(f"\n{'='*70}")
            print(f"🔄 Cycle #{cycle} - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*70}")
            
            for symbol in symbols:
                try:
                    print(f"\n📊 Analyzing {symbol}...")
                    
                    # Get market data
                    candles = client.get_klines(symbol, '5m', 100)
                    if not candles:
                        logger.warning(f"  ⚠️ No candles for {symbol}")
                        continue
                    
                    current_price = float(candles[-1][4])  # Close price
                    
                    # AI Analysis
                    analysis = await bot.analyze_symbol(symbol)
                    
                    if not analysis:
                        logger.warning(f"  ⚠️ No analysis for {symbol}")
                        continue
                    
                    signal_type = analysis.get('signal', 'HOLD')
                    confidence = analysis.get('confidence', 0)
                    
                    print(f"  💲 Price: ${current_price:,.2f}")
                    print(f"  🎯 Signal: {signal_type}")
                    print(f"  📊 Confidence: {confidence:.1f}%")
                    
                    # Check if should trade
                    if confidence >= 75 and signal_type in ['LONG', 'SHORT']:
                        # Check if already have position
                        has_position = False
                        for pos in positions:
                            if pos['symbol'] == symbol:
                                has_position = True
                                break
                        
                        if not has_position:
                            print(f"  ✅ GOOD OPPORTUNITY!")
                            print(f"  📍 Entry: ${current_price:,.2f}")
                            
                            # Calculate TP/SL
                            if signal_type == 'LONG':
                                tp_price = current_price * 1.04  # +4%
                                sl_price = current_price * 0.98  # -2%
                            else:  # SHORT
                                tp_price = current_price * 0.96  # -4%
                                sl_price = current_price * 1.02  # +2%
                            
                            print(f"  🎯 TP: ${tp_price:,.2f}")
                            print(f"  🛡️ SL: ${sl_price:,.2f}")
                            
                            # Calculate position size (2% risk)
                            risk_amount = balance * 0.02
                            position_size = risk_amount / abs(current_price - sl_price)
                            
                            print(f"  💵 Position Size: {position_size:.4f} {symbol.replace('USDT', '')}")
                            print(f"  ⚠️ Risk: ${risk_amount:.2f} (2% of balance)")
                            
                            # Ask for confirmation
                            print(f"\n  🤔 Execute {signal_type} trade for {symbol}?")
                            print(f"     Set MANUAL_TRADING=True to auto-execute")
                            
                        else:
                            print(f"  ⏸️ Already have position in {symbol}")
                    else:
                        if signal_type == 'HOLD':
                            print(f"  ⏸️ HOLD - Waiting for better opportunity")
                        else:
                            print(f"  ⏸️ Confidence too low ({confidence:.1f}% < 75%)")
                    
                except Exception as e:
                    logger.error(f"  ❌ Error analyzing {symbol}: {e}")
            
            # Update positions
            positions = client.get_open_positions()
            if positions:
                print(f"\n📌 Current Positions: {len(positions)}")
                for pos in positions:
                    pnl = float(pos.get('unRealizedProfit', 0))
                    pnl_color = '🟢' if pnl >= 0 else '🔴'
                    print(f"   {pnl_color} {pos['symbol']}: {pos['positionSide']} | PnL: ${pnl:,.2f}")
            
            # Wait before next cycle
            print(f"\n⏳ Waiting 60 seconds before next cycle...")
            await asyncio.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("\n🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n" + "="*70)
        print("👋 Bot stopped")
        print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
