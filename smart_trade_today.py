"""
🤖 SMART TRADE TODAY - Real-time Market Analysis
Phân tích thị trường ngay lập tức để tìm cơ hội giao dịch tốt nhất
FIX: Confidence calculation corrected
"""

import asyncio
import joblib
import numpy as np
from datetime import datetime
from loguru import logger
from binance_client import BinanceFuturesClient
from technical_analysis import TechnicalAnalyzer
from train_ai_improved import prepare_advanced_features

# User settings
LEVERAGE_SETTINGS = {
    'BTCUSDT': 100,
    'ETHUSDT': 100,
    'SOLUSDT': 50
}

POSITION_SIZE_PERCENT = 30  # 30% of balance per trade
SL_PERCENT = 1  # 1% stop loss
TP_PERCENT = 2  # 2% take profit (R:R = 1:2)
MIN_CONFIDENCE = 60  # Minimum 60% confidence to trade

def analyze_market():
    """Phân tích thị trường với AI models"""
    
    print("="*80)
    print(f"🤖 SMART TRADE ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    client = BinanceFuturesClient()
    analyzer = TechnicalAnalyzer()
    
    # Load models
    models = {}
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    for symbol in symbols:
        try:
            model_path = f'models/gradient_boost_{symbol}.pkl'
            model_data = joblib.load(model_path)
            models[symbol] = model_data
            logger.info(f"✅ Loaded model for {symbol} (accuracy: {model_data['accuracy']:.1f}%)")
        except Exception as e:
            logger.error(f"❌ Failed to load model for {symbol}: {e}")
    
    # Get account info
    try:
        account_info = client.get_account_info()
        balance = float(account_info['totalWalletBalance'])
        available = float(account_info['availableBalance'])
        print(f"\n💰 ACCOUNT STATUS:")
        print(f"   Balance: ${balance:.2f} USDT")
        print(f"   Available: ${available:.2f} USDT")
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        return
    
    # Get current positions
    try:
        positions = client.get_open_positions()
        if positions:
            print(f"\n📊 CURRENT POSITIONS: {len(positions)}")
            total_pnl = 0
            for pos in positions:
                pnl = pos.get('unrealized_pnl', 0)
                total_pnl += pnl
                emoji = '🟢' if pnl >= 0 else '🔴'
                print(f"   {emoji} {pos['symbol']} {pos['side']}: Entry ${pos['entry_price']:.2f} → ${pos.get('mark_price', 0):.2f}, PnL: ${pnl:+.2f}")
            print(f"   💵 Total Unrealized PnL: ${total_pnl:+.2f}")
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
    
    print("\n" + "="*80)
    print("📈 MARKET ANALYSIS - Finding Best Entry")
    print("="*80)
    
    analysis_results = []
    
    for symbol in symbols:
        print(f"\n🔍 Analyzing {symbol}...")
        
        try:
            # Get klines
            klines = client.get_klines(symbol, "5m", 100)
            if not klines:
                continue
            
            # Prepare dataframe
            df = analyzer.prepare_dataframe(klines)
            df = analyzer.add_basic_indicators(df)
            df = analyzer.add_advanced_indicators(df)
            
            # Get current price
            current_price = float(df['close'].iloc[-1])
            
            # Calculate price changes
            price_5m_ago = float(df['close'].iloc[-2])
            price_1h_ago = float(df['close'].iloc[-12]) if len(df) >= 12 else price_5m_ago
            price_4h_ago = float(df['close'].iloc[-48]) if len(df) >= 48 else price_1h_ago
            
            change_5m = ((current_price - price_5m_ago) / price_5m_ago) * 100
            change_1h = ((current_price - price_1h_ago) / price_1h_ago) * 100
            change_4h = ((current_price - price_4h_ago) / price_4h_ago) * 100
            
            print(f"   💵 Price: ${current_price:.2f}")
            print(f"   📊 Change 5m: {change_5m:+.2f}%")
            print(f"   📊 Change 1h: {change_1h:+.2f}%")
            print(f"   📊 Change 4h: {change_4h:+.2f}%")
            
            # AI Prediction
            if symbol in models:
                model_data = models[symbol]
                model = model_data['model']
                
                # Prepare features
                X, _ = prepare_advanced_features(df)
                latest_features = X[-1].reshape(1, -1)
                
                # Predict
                prediction = model.predict(latest_features)[0]  # -1, 0, 1
                probabilities = model.predict_proba(latest_features)[0]  # [prob_-1, prob_0, prob_1]
                
                # Get confidence - find index of predicted class
                classes = model.classes_  # [-1, 0, 1]
                class_idx = np.where(classes == prediction)[0][0]
                confidence = probabilities[class_idx] * 100
                
                # Map prediction to signal
                signal_map = {-1: 'SHORT', 0: 'HOLD', 1: 'LONG'}
                signal = signal_map[prediction]
                
                print(f"   🤖 AI Signal: {signal}")
                print(f"   📈 Confidence: {confidence:.1f}%")
                print(f"   📊 Probabilities: SHORT={probabilities[0]*100:.1f}%, HOLD={probabilities[1]*100:.1f}%, LONG={probabilities[2]*100:.1f}%")
                
                # Technical indicators
                rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else 50
                macd = df['macd'].iloc[-1] if 'macd' in df.columns else 0
                macd_signal = df['macd_signal'].iloc[-1] if 'macd_signal' in df.columns else 0
                
                print(f"   📉 RSI: {rsi:.1f}")
                print(f"   📊 MACD: {macd:.2f} (Signal: {macd_signal:.2f})")
                
                # Determine trend
                if 'ema_50' in df.columns and 'ema_200' in df.columns:
                    ema50 = df['ema_50'].iloc[-1]
                    ema200 = df['ema_200'].iloc[-1]
                    if ema50 > ema200:
                        trend = "BULLISH"
                    elif ema50 < ema200:
                        trend = "BEARISH"
                    else:
                        trend = "NEUTRAL"
                else:
                    trend = "NEUTRAL"
                
                # Calculate opportunity score
                opportunity_score = 0
                
                # High confidence = better score
                if confidence >= 70:
                    opportunity_score += 3
                elif confidence >= 60:
                    opportunity_score += 2
                elif confidence >= 50:
                    opportunity_score += 1
                
                # Signal clarity (not HOLD)
                if signal != 'HOLD':
                    opportunity_score += 3
                
                # RSI extremes = better opportunity
                if (signal == 'LONG' and rsi < 30) or (signal == 'SHORT' and rsi > 70):
                    opportunity_score += 2
                elif (signal == 'LONG' and rsi < 40) or (signal == 'SHORT' and rsi > 60):
                    opportunity_score += 1
                
                # Trend alignment
                if (signal == 'LONG' and trend == 'BULLISH') or (signal == 'SHORT' and trend == 'BEARISH'):
                    opportunity_score += 2
                
                # MACD confirmation
                if (signal == 'LONG' and macd > macd_signal) or (signal == 'SHORT' and macd < macd_signal):
                    opportunity_score += 1
                
                # 4h momentum alignment
                if (signal == 'LONG' and change_4h > 0) or (signal == 'SHORT' and change_4h < 0):
                    opportunity_score += 1
                
                analysis_results.append({
                    'symbol': symbol,
                    'price': current_price,
                    'signal': signal,
                    'confidence': confidence,
                    'trend': trend,
                    'rsi': rsi,
                    'macd': macd,
                    'macd_signal': macd_signal,
                    'change_1h': change_1h,
                    'change_4h': change_4h,
                    'opportunity_score': opportunity_score,
                    'leverage': LEVERAGE_SETTINGS[symbol],
                    'probabilities': probabilities
                })
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            import traceback
            traceback.print_exc()
    
    # Sort by opportunity score
    analysis_results.sort(key=lambda x: x['opportunity_score'], reverse=True)
    
    # Display recommendations
    print("\n" + "="*80)
    print("🎯 TRADE RECOMMENDATIONS (Sorted by Opportunity)")
    print("="*80)
    
    for i, result in enumerate(analysis_results, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"#{i}"
        
        position_value = available * (POSITION_SIZE_PERCENT / 100)
        potential_profit = position_value * result['leverage'] * (TP_PERCENT / 100)
        potential_loss = position_value * result['leverage'] * (SL_PERCENT / 100)
        
        print(f"\n{medal} #{i} {result['symbol']}:")
        print(f"   💵 Price: ${result['price']:.2f}")
        print(f"   📊 Trend: {result['trend']}")
        print(f"   📉 RSI: {result['rsi']:.1f}")
        print(f"   📈 Change 1h/4h: {result['change_1h']:+.2f}% / {result['change_4h']:+.2f}%")
        print(f"   🤖 AI Signal: {result['signal']} ({result['confidence']:.1f}%)")
        print(f"   ⭐ Opportunity Score: {result['opportunity_score']}/13")
        print(f"   💰 Potential Profit ({TP_PERCENT}% move): ${potential_profit:.2f}")
        print(f"   💸 Potential Loss ({SL_PERCENT}% move): ${potential_loss:.2f}")
        print(f"   ⚙️ Leverage: {result['leverage']}x")
    
    # Find best trade
    print("\n" + "="*80)
    print("🚀 BEST TRADE OPPORTUNITY")
    print("="*80)
    
    # Filter actionable signals
    actionable_signals = [r for r in analysis_results if r['signal'] != 'HOLD' and r['confidence'] >= MIN_CONFIDENCE]
    
    if actionable_signals:
        best = actionable_signals[0]
        print(f"\n✅ RECOMMENDED TRADE:")
        print(f"   Symbol: {best['symbol']}")
        print(f"   Direction: {best['signal']}")
        print(f"   Entry Price: ${best['price']:.2f}")
        
        if best['signal'] == 'LONG':
            sl_price = best['price'] * (1 - SL_PERCENT / 100)
            tp_price = best['price'] * (1 + TP_PERCENT / 100)
        else:
            sl_price = best['price'] * (1 + SL_PERCENT / 100)
            tp_price = best['price'] * (1 - TP_PERCENT / 100)
        
        print(f"   Stop Loss: ${sl_price:.2f} ({SL_PERCENT}%)")
        print(f"   Take Profit: ${tp_price:.2f} ({TP_PERCENT}%)")
        print(f"   Leverage: {best['leverage']}x")
        print(f"   Confidence: {best['confidence']:.1f}%")
        print(f"   Opportunity Score: {best['opportunity_score']}/13")
        
        # Calculate position size
        position_value = available * (POSITION_SIZE_PERCENT / 100)
        quantity = position_value / best['price']
        
        print(f"\n💰 Position Size:")
        print(f"   Value: ${position_value:.2f} USDT ({POSITION_SIZE_PERCENT}% of available)")
        print(f"   Quantity: {quantity:.4f}")
        
        # Return best trade for execution
        return {
            'symbol': best['symbol'],
            'signal': best['signal'],
            'price': best['price'],
            'sl': sl_price,
            'tp': tp_price,
            'leverage': best['leverage'],
            'confidence': best['confidence'],
            'quantity': quantity,
            'execute': True
        }
    else:
        print(f"\n⚠️ NO CLEAR OPPORTUNITY")
        print(f"   All signals are HOLD or below {MIN_CONFIDENCE}% confidence")
        print(f"   Best option: {analysis_results[0]['symbol']} with score {analysis_results[0]['opportunity_score']}/13")
        print(f"   Signal: {analysis_results[0]['signal']} ({analysis_results[0]['confidence']:.1f}%)")
        print(f"   Recommendation: WAIT for better setup")
        
        return {'execute': False, 'reason': 'No clear opportunity'}

def execute_recommended_trade(trade_info):
    """Thực hiện giao dịch được đề xuất"""
    if not trade_info or not trade_info.get('execute'):
        print("\n⏭️ Không có lệnh nào được thực hiện")
        return
    
    print("\n" + "="*80)
    print("🚀 EXECUTING TRADE")
    print("="*80)
    
    client = BinanceFuturesClient()
    symbol = trade_info['symbol']
    signal = trade_info['signal']
    leverage = trade_info['leverage']
    quantity = trade_info['quantity']
    
    try:
        # Set leverage
        print(f"\n⚙️ Setting leverage to {leverage}x...")
        client.client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"   ✅ Leverage set to {leverage}x")
        
        # Get precision
        exchange_info = client.client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
        
        qty_precision = 3
        if symbol_info:
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    qty_precision = max(0, -int(np.floor(np.log10(step_size))))
                    break
        
        quantity = round(quantity, qty_precision)
        
        # Ensure minimum quantity
        if quantity <= 0:
            print(f"   ❌ Quantity too small: {quantity}")
            return
        
        # Place order
        side = 'BUY' if signal == 'LONG' else 'SELL'
        position_side = 'LONG' if signal == 'LONG' else 'SHORT'  # For Hedge Mode
        print(f"\n📝 Placing {signal} order...")
        print(f"   Symbol: {symbol}")
        print(f"   Side: {side}")
        print(f"   Quantity: {quantity}")
        
        order = client.client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity,
            positionSide=position_side  # Required for Hedge Mode
        )
        
        print(f"\n✅ ORDER EXECUTED!")
        print(f"   Order ID: {order['orderId']}")
        print(f"   Status: {order['status']}")
        print(f"   Symbol: {order['symbol']}")
        print(f"   Side: {order['side']}")
        print(f"   Quantity: {order['origQty']}")
        
        # Place SL/TP
        print(f"\n🛡️ Setting Stop Loss & Take Profit...")
        
        # Stop Loss
        try:
            sl_side = 'SELL' if signal == 'LONG' else 'BUY'
            sl_order = client.client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type='STOP_MARKET',
                stopPrice=round(trade_info['sl'], 2),
                quantity=quantity,
                positionSide=position_side  # Required for Hedge Mode
            )
            print(f"   ✅ Stop Loss set @ ${trade_info['sl']:.2f}")
        except Exception as e:
            print(f"   ⚠️ SL Error: {e}")
        
        # Take Profit
        try:
            tp_side = 'SELL' if signal == 'LONG' else 'BUY'
            tp_order = client.client.futures_create_order(
                symbol=symbol,
                side=tp_side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=round(trade_info['tp'], 2),
                quantity=quantity,
                positionSide=position_side  # Required for Hedge Mode
            )
            print(f"   ✅ Take Profit set @ ${trade_info['tp']:.2f}")
        except Exception as e:
            print(f"   ⚠️ TP Error: {e}")
        
        return order
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("\n" + "🌟"*40)
    print("    SMART TRADING BOT - MARKET ANALYSIS")
    print("    Thứ 3, ngày 02/12/2025")
    print("🌟"*40 + "\n")
    
    # Analyze market
    trade_info = analyze_market()
    
    # Ask for confirmation
    if trade_info and trade_info.get('execute'):
        print("\n" + "⚠️"*20)
        user_input = input("\n❓ Bạn có muốn thực hiện lệnh này không? (y/n): ")
        
        if user_input.lower() == 'y':
            execute_recommended_trade(trade_info)
        else:
            print("⏭️ Đã hủy lệnh")
    
    print("\n" + "="*80)
    print("📊 Analysis complete!")
    print("="*80)
