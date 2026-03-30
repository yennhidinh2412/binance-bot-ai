"""
SMART TRADE ANALYSIS - Thứ 3, 02/12/2025 13:34
Phân tích thị trường và đưa ra quyết định vào lệnh thông minh nhất
"""
import asyncio
from binance_client import BinanceFuturesClient
from smart_bot_engine import SmartBotEngine
from technical_analysis import TechnicalAnalyzer
from datetime import datetime

print("="*80)
print(f"🤖 SMART TRADE ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*80)

async def analyze_and_recommend():
    """Phân tích thị trường và đưa ra khuyến nghị trade tốt nhất"""
    
    # Initialize
    client = BinanceFuturesClient()
    bot = SmartBotEngine(client)
    analyzer = TechnicalAnalyzer()
    
    # Get account info
    account = client.get_account_info()
    balance = float(account['totalWalletBalance'])
    available = float(account['availableBalance'])
    
    print(f"\n💰 ACCOUNT STATUS:")
    print(f"   Balance: ${balance:.2f} USDT")
    print(f"   Available: ${available:.2f} USDT")
    
    # Check current positions
    positions = client.get_open_positions()
    open_positions = [p for p in positions if float(p['positionAmt']) != 0]
    
    if open_positions:
        print(f"\n📊 CURRENT POSITIONS: {len(open_positions)}")
        total_pnl = 0
        for pos in open_positions:
            pnl = float(pos['unRealizedProfit'])
            total_pnl += pnl
            symbol = pos['symbol']
            amt = float(pos['positionAmt'])
            side = 'LONG' if amt > 0 else 'SHORT'
            entry = float(pos['entryPrice'])
            mark = float(pos['markPrice'])
            
            pnl_icon = "🟢" if pnl >= 0 else "🔴"
            print(f"   {pnl_icon} {symbol} {side}: Entry ${entry:.2f} → ${mark:.2f}, PnL: ${pnl:+.2f}")
        
        print(f"   💵 Total Unrealized PnL: ${total_pnl:+.2f}")
    else:
        print(f"\n📊 No open positions")
    
    # Analyze all symbols
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    print(f"\n" + "="*80)
    print("📈 MARKET ANALYSIS - Finding Best Entry")
    print("="*80)
    
    recommendations = []
    
    for symbol in symbols:
        print(f"\n🔍 Analyzing {symbol}...")
        
        # Get current price and klines
        klines = client.get_klines(symbol, '5m', limit=100)
        current_price = float(klines[-1][4])
        
        # Calculate price change
        price_5m_ago = float(klines[-2][4])
        price_1h_ago = float(klines[-12][4]) if len(klines) >= 12 else price_5m_ago
        price_4h_ago = float(klines[-48][4]) if len(klines) >= 48 else price_5m_ago
        
        change_5m = ((current_price - price_5m_ago) / price_5m_ago) * 100
        change_1h = ((current_price - price_1h_ago) / price_1h_ago) * 100
        change_4h = ((current_price - price_4h_ago) / price_4h_ago) * 100
        
        print(f"   💵 Price: ${current_price:.2f}")
        print(f"   📊 Change 5m: {change_5m:+.2f}%")
        print(f"   📊 Change 1h: {change_1h:+.2f}%")
        print(f"   📊 Change 4h: {change_4h:+.2f}%")
        
        # Get AI prediction
        analysis = await bot.analyze_symbol(symbol)
        signal = analysis['signal']
        confidence = analysis['confidence']
        
        print(f"   🤖 AI Signal: {signal}")
        print(f"   📈 Confidence: {confidence:.1%}")
        
        # Calculate technical indicators
        df = analyzer.prepare_dataframe(klines)
        df = analyzer.add_basic_indicators(df)
        
        rsi = df['rsi'].iloc[-1] if 'rsi' in df else 50
        macd = df['macd'].iloc[-1] if 'macd' in df else 0
        macd_signal = df['macd_signal'].iloc[-1] if 'macd_signal' in df else 0
        
        print(f"   📉 RSI: {rsi:.1f}")
        print(f"   📊 MACD: {macd:.2f} (Signal: {macd_signal:.2f})")
        
        # Determine trend strength
        trend_score = 0
        trend_direction = 'NEUTRAL'
        
        # Check momentum
        if change_1h > 0.5 and change_4h > 1:
            trend_score += 2
            trend_direction = 'BULLISH'
        elif change_1h < -0.5 and change_4h < -1:
            trend_score += 2
            trend_direction = 'BEARISH'
        
        # Check RSI
        if rsi < 30:
            trend_score += 1
            if trend_direction != 'BEARISH':
                trend_direction = 'OVERSOLD'
        elif rsi > 70:
            trend_score += 1
            if trend_direction != 'BULLISH':
                trend_direction = 'OVERBOUGHT'
        elif 40 < rsi < 60:
            trend_score += 0.5
        
        # Check MACD
        if macd > macd_signal and macd > 0:
            trend_score += 1
        elif macd < macd_signal and macd < 0:
            trend_score += 1
        
        # Calculate opportunity score (0-10)
        opportunity_score = min(10, trend_score * 2 + confidence * 3)
        
        # Determine recommended action
        if signal == 'BUY' and confidence > 0.6:
            action = 'LONG'
            potential = "HIGH" if confidence > 0.75 else "MEDIUM"
        elif signal == 'SELL' and confidence > 0.6:
            action = 'SHORT'
            potential = "HIGH" if confidence > 0.75 else "MEDIUM"
        else:
            action = 'HOLD'
            potential = "LOW"
        
        # Calculate potential profit (with leverage)
        if symbol == 'BTCUSDT':
            leverage = 100
        elif symbol == 'ETHUSDT':
            leverage = 100
        else:
            leverage = 50
        
        # Position size (30% of available balance)
        position_value = available * 0.30
        quantity = position_value / current_price
        
        # Potential profit with 2% move
        potential_profit_2pct = quantity * current_price * 0.02 * leverage
        potential_loss_1pct = quantity * current_price * 0.01 * leverage
        
        recommendations.append({
            'symbol': symbol,
            'price': current_price,
            'signal': signal,
            'confidence': confidence,
            'action': action,
            'potential': potential,
            'trend': trend_direction,
            'rsi': rsi,
            'change_1h': change_1h,
            'change_4h': change_4h,
            'leverage': leverage,
            'opportunity_score': opportunity_score,
            'potential_profit': potential_profit_2pct,
            'potential_loss': potential_loss_1pct
        })
    
    # Sort by opportunity score
    recommendations.sort(key=lambda x: x['opportunity_score'], reverse=True)
    
    # Display recommendations
    print("\n" + "="*80)
    print("🎯 TRADE RECOMMENDATIONS (Sorted by Opportunity)")
    print("="*80)
    
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{'🥇' if i == 1 else '🥈' if i == 2 else '🥉'} #{i} {rec['symbol']}:")
        print(f"   💵 Price: ${rec['price']:.2f}")
        print(f"   📊 Trend: {rec['trend']}")
        print(f"   📉 RSI: {rec['rsi']:.1f}")
        print(f"   📈 Change 1h/4h: {rec['change_1h']:+.2f}% / {rec['change_4h']:+.2f}%")
        print(f"   🤖 AI Signal: {rec['signal']} ({rec['confidence']:.1%})")
        print(f"   🎯 Recommendation: {rec['action']}")
        print(f"   ⭐ Opportunity Score: {rec['opportunity_score']:.1f}/10")
        print(f"   💰 Potential Profit (2% move): ${rec['potential_profit']:.2f}")
        print(f"   💸 Potential Loss (1% move): ${rec['potential_loss']:.2f}")
        print(f"   ⚙️ Leverage: {rec['leverage']}x")
    
    # Best recommendation
    best = recommendations[0]
    
    print("\n" + "="*80)
    print("🚀 BEST TRADE OPPORTUNITY")
    print("="*80)
    
    if best['action'] != 'HOLD' and best['opportunity_score'] >= 5:
        print(f"\n✅ RECOMMENDED: {best['action']} {best['symbol']}")
        print(f"   Entry: ${best['price']:.2f}")
        print(f"   Leverage: {best['leverage']}x")
        print(f"   Stop Loss: ${best['price'] * (0.99 if best['action'] == 'LONG' else 1.01):.2f}")
        print(f"   Take Profit: ${best['price'] * (1.02 if best['action'] == 'LONG' else 0.98):.2f}")
        print(f"   Potential Profit: ${best['potential_profit']:.2f}")
        print(f"   Risk/Reward: 1:2")
        
        return best
    else:
        print(f"\n⚠️ NO CLEAR OPPORTUNITY")
        print(f"   Market conditions are not favorable for high-confidence trades")
        print(f"   Best option: {best['symbol']} with score {best['opportunity_score']:.1f}/10")
        print(f"   Recommendation: WAIT for better setup")
        
        return None

if __name__ == "__main__":
    result = asyncio.run(analyze_and_recommend())
    
    if result:
        print(f"\n" + "="*80)
        print("💡 READY TO EXECUTE?")
        print("="*80)
        print(f"\nRun: python aggressive_trade_test.py")
        print("Or manually enter the trade on Binance Testnet")
