"""
Real-Time Trading Monitor
Monitor bot performance, positions, and PnL
"""
from binance_client import BinanceFuturesClient
from datetime import datetime
import time
import os

def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def monitor_trading():
    """Real-time monitoring of trading bot"""
    
    client = BinanceFuturesClient()
    
    print("="*80)
    print("📊 REAL-TIME TRADING MONITOR - Binance Testnet")
    print("="*80)
    print("Press Ctrl+C to stop monitoring\n")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            clear_screen()
            
            print("="*80)
            print(f"📊 TRADING MONITOR - Update #{iteration}")
            print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*80)
            
            # Get account info
            try:
                account = client.get_account_info()
                balance = float(account['totalWalletBalance'])
                available = float(account['availableBalance'])
                unrealized_pnl = float(account['totalUnrealizedProfit'])
                
                print(f"\n💰 ACCOUNT STATUS:")
                print(f"   Total Balance: ${balance:.2f} USDT")
                print(f"   Available: ${available:.2f} USDT")
                print(f"   Unrealized PnL: ${unrealized_pnl:+.2f} USDT")
                
                # Calculate used margin
                used_margin = balance - available
                if used_margin > 0:
                    print(f"   Used Margin: ${used_margin:.2f} USDT")
                
            except Exception as e:
                print(f"\n❌ Error fetching account: {e}")
            
            # Get open positions
            try:
                positions = client.get_open_positions()
                open_positions = [p for p in positions if float(p['positionAmt']) != 0]
                
                print(f"\n📈 OPEN POSITIONS: {len(open_positions)}")
                
                if open_positions:
                    total_position_pnl = 0.0
                    
                    for pos in open_positions:
                        symbol = pos['symbol']
                        side = 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'
                        amount = abs(float(pos['positionAmt']))
                        entry_price = float(pos['entryPrice'])
                        mark_price = float(pos['markPrice'])
                        pnl = float(pos['unRealizedProfit'])
                        pnl_percent = (pnl / (amount * entry_price)) * 100 if amount * entry_price > 0 else 0
                        leverage = int(pos.get('leverage', 1))  # Default to 1x if not present
                        
                        total_position_pnl += pnl
                        
                        # Color code PnL
                        pnl_symbol = "🟢" if pnl >= 0 else "🔴"
                        
                        print(f"\n   {pnl_symbol} {symbol} {side} {leverage}x:")
                        print(f"      Amount: {amount}")
                        print(f"      Entry: ${entry_price:.2f}")
                        print(f"      Mark: ${mark_price:.2f}")
                        print(f"      PnL: ${pnl:+.2f} ({pnl_percent:+.2f}%)")
                    
                    print(f"\n   💵 Total Position PnL: ${total_position_pnl:+.2f}")
                else:
                    print("   No open positions")
                    
            except Exception as e:
                print(f"\n❌ Error fetching positions: {e}")
            
            # Get current prices
            try:
                print(f"\n📊 MARKET PRICES:")
                symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
                
                for symbol in symbols:
                    klines = client.get_klines(symbol, '5m', limit=2)
                    if len(klines) >= 2:
                        current_price = float(klines[-1][4])
                        previous_price = float(klines[-2][4])
                        change = ((current_price - previous_price) / previous_price) * 100
                        
                        # Color code change
                        if change > 0:
                            change_symbol = "🟢"
                        elif change < 0:
                            change_symbol = "🔴"
                        else:
                            change_symbol = "⚪"
                        
                        print(f"   {change_symbol} {symbol}: ${current_price:.2f} ({change:+.2f}%)")
                        
            except Exception as e:
                print(f"\n❌ Error fetching prices: {e}")
            
            # Performance summary
            print(f"\n" + "="*80)
            print("📈 SESSION SUMMARY")
            print("="*80)
            
            if unrealized_pnl != 0:
                roi = (unrealized_pnl / balance) * 100
                print(f"   ROI: {roi:+.2f}%")
                
                if roi > 0:
                    print(f"   Status: 🟢 PROFITABLE")
                else:
                    print(f"   Status: 🔴 LOSING")
            else:
                print(f"   Status: ⚪ NO ACTIVE TRADES")
            
            print(f"\n⏰ Next update in 10 seconds... (Ctrl+C to stop)")
            print("="*80)
            
            # Wait before next update
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n\n" + "="*80)
        print("🛑 MONITORING STOPPED")
        print("="*80)
        
        # Final summary
        try:
            account = client.get_account_info()
            balance = float(account['totalWalletBalance'])
            unrealized_pnl = float(account['totalUnrealizedProfit'])
            
            print(f"\n💰 FINAL STATUS:")
            print(f"   Balance: ${balance:.2f} USDT")
            print(f"   Unrealized PnL: ${unrealized_pnl:+.2f} USDT")
            
            if unrealized_pnl > 0:
                print(f"\n   🎉 Session was PROFITABLE!")
            elif unrealized_pnl < 0:
                print(f"\n   ⚠️  Session had losses (protected by SL)")
            else:
                print(f"\n   ✅ No active positions")
                
        except Exception as e:
            print(f"\n❌ Error fetching final status: {e}")
        
        print("\n" + "="*80)

if __name__ == "__main__":
    monitor_trading()
