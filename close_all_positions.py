"""
🚨 CLOSE ALL POSITIONS & ENTER NEW TRADES
Đóng tất cả vị thế và vào lệnh mới
"""

from binance_client import BinanceFuturesClient
import time
import joblib
import numpy as np
from technical_analysis import TechnicalAnalyzer
from train_ai_improved import prepare_advanced_features

client = BinanceFuturesClient()
analyzer = TechnicalAnalyzer()

print("="*80)
print("🚨 ĐÓNG TẤT CẢ VỊ THẾ")
print("="*80)

# Get current positions
positions = client.client.futures_position_information()
closed = 0
total_realized_pnl = 0

for pos in positions:
    position_amt = float(pos['positionAmt'])
    if position_amt != 0:
        symbol = pos['symbol']
        side = 'SELL' if position_amt > 0 else 'BUY'
        quantity = abs(position_amt)
        entry_price = float(pos['entryPrice'])
        mark_price = float(pos['markPrice'])
        pnl = float(pos['unRealizedProfit'])
        total_realized_pnl += pnl
        
        print(f"\n📍 {symbol}:")
        print(f"   Entry: ${entry_price:.2f} → Mark: ${mark_price:.2f}")
        print(f"   PnL: ${pnl:+.2f}")
        print(f"   Closing {quantity} @ MARKET...")
        
        try:
            # Cancel all open orders first
            client.client.futures_cancel_all_open_orders(symbol=symbol)
            print(f"   ✅ Cancelled pending orders")
            
            # Determine positionSide for Hedge Mode
            position_side = 'LONG' if position_amt > 0 else 'SHORT'
            
            # Close position
            order = client.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity,
                positionSide=position_side  # Required for Hedge Mode
            )
            print(f"   ✅ Position closed! Order ID: {order['orderId']}")
            closed += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")

print(f"\n✅ Đã đóng {closed} vị thế")
print(f"💵 Total Realized PnL: ${total_realized_pnl:+.2f}")

# Get updated account
time.sleep(1)
account = client.client.futures_account()
balance = float(account['totalWalletBalance'])
available = float(account['availableBalance'])
print(f"\n💰 Account sau khi đóng:")
print(f"   Balance: ${balance:.2f}")
print(f"   Available: ${available:.2f}")

# ==================== PHÂN TÍCH THỊ TRƯỜNG ====================
print("\n" + "="*80)
print("📊 PHÂN TÍCH THỊ TRƯỜNG HIỆN TẠI")
print("="*80)

# Load models
models = {}
symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
LEVERAGE = {'BTCUSDT': 100, 'ETHUSDT': 100, 'SOLUSDT': 50}

for symbol in symbols:
    try:
        model_data = joblib.load(f'models/gradient_boost_{symbol}.pkl')
        models[symbol] = model_data
    except:
        pass

market_data = []

for symbol in symbols:
    try:
        # Get klines
        klines = client.get_klines(symbol, "5m", 100)
        df = analyzer.prepare_dataframe(klines)
        df = analyzer.add_basic_indicators(df)
        df = analyzer.add_advanced_indicators(df)
        
        current_price = float(df['close'].iloc[-1])
        
        # Price changes
        price_1h_ago = float(df['close'].iloc[-12]) if len(df) >= 12 else current_price
        price_4h_ago = float(df['close'].iloc[-48]) if len(df) >= 48 else current_price
        change_1h = ((current_price - price_1h_ago) / price_1h_ago) * 100
        change_4h = ((current_price - price_4h_ago) / price_4h_ago) * 100
        
        # RSI
        rsi = df['rsi'].iloc[-1] if 'rsi' in df.columns else 50
        
        # AI Prediction
        if symbol in models:
            model = models[symbol]['model']
            X, _ = prepare_advanced_features(df)
            latest_features = X[-1].reshape(1, -1)
            
            prediction = model.predict(latest_features)[0]
            probabilities = model.predict_proba(latest_features)[0]
            classes = model.classes_
            class_idx = np.where(classes == prediction)[0][0]
            confidence = probabilities[class_idx] * 100
            
            signal_map = {-1: 'SHORT', 0: 'HOLD', 1: 'LONG'}
            signal = signal_map[prediction]
            
            # Get all probabilities
            prob_short = probabilities[0] * 100
            prob_hold = probabilities[1] * 100
            prob_long = probabilities[2] * 100
        else:
            signal = 'HOLD'
            confidence = 0
            prob_short = prob_hold = prob_long = 33.3
        
        print(f"\n🔍 {symbol}:")
        print(f"   💵 Price: ${current_price:.2f}")
        print(f"   📊 Change 1h: {change_1h:+.2f}% | 4h: {change_4h:+.2f}%")
        print(f"   📉 RSI: {rsi:.1f}")
        print(f"   🤖 AI Signal: {signal} ({confidence:.1f}%)")
        print(f"   📊 Probs: SHORT={prob_short:.1f}% | HOLD={prob_hold:.1f}% | LONG={prob_long:.1f}%")
        
        market_data.append({
            'symbol': symbol,
            'price': current_price,
            'signal': signal,
            'confidence': confidence,
            'rsi': rsi,
            'change_1h': change_1h,
            'change_4h': change_4h,
            'prob_long': prob_long,
            'prob_short': prob_short,
            'leverage': LEVERAGE[symbol]
        })
        
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

# ==================== VÀO LỆNH MỚI ====================
print("\n" + "="*80)
print("🚀 VÀO LỆNH MỚI")
print("="*80)

# Settings
POSITION_SIZE_PCT = 30  # 30% balance per trade
SL_PCT = 1.5  # 1.5% stop loss
TP_PCT = 3.0  # 3% take profit

# Find best trades - prefer signals with clear direction
# Even if HOLD, look at probabilities to find best opportunity
for data in market_data:
    symbol = data['symbol']
    price = data['price']
    leverage = data['leverage']
    signal = data['signal']
    
    # Determine trade direction based on probabilities and market momentum
    if data['prob_long'] > data['prob_short'] and data['change_4h'] > 0:
        trade_signal = 'LONG'
        trade_conf = data['prob_long']
    elif data['prob_short'] > data['prob_long'] and data['change_4h'] < 0:
        trade_signal = 'SHORT'
        trade_conf = data['prob_short']
    elif data['change_4h'] > 0.3:  # Bullish momentum
        trade_signal = 'LONG'
        trade_conf = max(data['prob_long'], 50)
    elif data['change_4h'] < -0.3:  # Bearish momentum
        trade_signal = 'SHORT'
        trade_conf = max(data['prob_short'], 50)
    else:
        # Default to momentum direction
        if data['change_1h'] > 0:
            trade_signal = 'LONG'
            trade_conf = 50 + data['change_1h'] * 10
        else:
            trade_signal = 'SHORT'
            trade_conf = 50 + abs(data['change_1h']) * 10
    
    print(f"\n{'='*60}")
    print(f"📈 {symbol} - Vào lệnh {trade_signal}")
    print(f"{'='*60}")
    
    try:
        # Set leverage
        client.client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"✅ Leverage set to {leverage}x")
        
        # Calculate position size
        position_value = available * (POSITION_SIZE_PCT / 100)
        quantity = position_value / price
        
        # Get precision
        exchange_info = client.client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
        
        qty_precision = 3
        price_precision = 2
        if symbol_info:
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    qty_precision = max(0, -int(np.floor(np.log10(step_size))))
                if f['filterType'] == 'PRICE_FILTER':
                    tick_size = float(f['tickSize'])
                    price_precision = max(0, -int(np.floor(np.log10(tick_size))))
        
        quantity = round(quantity, qty_precision)
        
        # Calculate SL/TP
        if trade_signal == 'LONG':
            sl_price = round(price * (1 - SL_PCT / 100), price_precision)
            tp_price = round(price * (1 + TP_PCT / 100), price_precision)
            side = 'BUY'
        else:
            sl_price = round(price * (1 + SL_PCT / 100), price_precision)
            tp_price = round(price * (1 - TP_PCT / 100), price_precision)
            side = 'SELL'
        
        print(f"📊 Entry Price: ${price:.2f}")
        print(f"🛡️ Stop Loss: ${sl_price:.2f} ({SL_PCT}%)")
        print(f"🎯 Take Profit: ${tp_price:.2f} ({TP_PCT}%)")
        print(f"📦 Quantity: {quantity}")
        print(f"💰 Position Value: ${position_value:.2f}")
        
        # Determine positionSide for Hedge Mode
        position_side = 'LONG' if trade_signal == 'LONG' else 'SHORT'
        
        # Place order with positionSide for Hedge Mode
        order = client.client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity,
            positionSide=position_side
        )
        print(f"✅ ORDER EXECUTED! ID: {order['orderId']}")
        
        # Place SL
        try:
            sl_side = 'SELL' if trade_signal == 'LONG' else 'BUY'
            sl_order = client.client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type='STOP_MARKET',
                stopPrice=sl_price,
                quantity=quantity,
                positionSide=position_side
            )
            print(f"✅ Stop Loss placed @ ${sl_price}")
        except Exception as e:
            print(f"⚠️ SL Error: {e}")
        
        # Place TP
        try:
            tp_order = client.client.futures_create_order(
                symbol=symbol,
                side=sl_side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=tp_price,
                quantity=quantity,
                positionSide=position_side
            )
            print(f"✅ Take Profit placed @ ${tp_price}")
        except Exception as e:
            print(f"⚠️ TP Error: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

# ==================== KIỂM TRA VỊ THẾ MỚI ====================
print("\n" + "="*80)
print("📊 VỊ THẾ MỚI SAU KHI VÀO LỆNH")
print("="*80)

time.sleep(2)
positions = client.client.futures_position_information()
total_pnl = 0

for pos in positions:
    position_amt = float(pos['positionAmt'])
    if position_amt != 0:
        symbol = pos['symbol']
        side = 'LONG' if position_amt > 0 else 'SHORT'
        entry_price = float(pos['entryPrice'])
        mark_price = float(pos['markPrice'])
        pnl = float(pos['unRealizedProfit'])
        leverage = pos.get('leverage', 'N/A')
        total_pnl += pnl
        
        emoji = '🟢' if pnl >= 0 else '🔴'
        print(f"\n{emoji} {symbol} {side} ({leverage}x):")
        print(f"   Entry: ${entry_price:.2f}")
        print(f"   Mark: ${mark_price:.2f}")
        print(f"   PnL: ${pnl:+.2f}")

print(f"\n💵 Total Unrealized PnL: ${total_pnl:+.2f}")

# Final account status
account = client.client.futures_account()
balance = float(account['totalWalletBalance'])
available = float(account['availableBalance'])
print(f"\n💰 Final Account:")
print(f"   Balance: ${balance:.2f}")
print(f"   Available: ${available:.2f}")

print("\n" + "="*80)
print("✅ HOÀN TẤT!")
print("="*80)
