"""
SMART BOT ENGINE v2.0 - Core trading logic với AI model
Xử lý luồng Start Bot thông minh, kiểm tra đầy đủ, tích hợp risk management
TÍCH HỢP CONTINUOUS LEARNING - Tự động cập nhật model với thị trường real-time
TÍCH HỢP ADVANCED AI ENGINE - Deep Learning + Ensemble Models
CẢI TIẾN: Position monitor, trailing stop, breakeven, partial TP,
         market regime filter, correlation check, funding rate, volatility spike
"""
import asyncio
import joblib
import numpy as np
import pandas as pd
import time
from datetime import datetime, timedelta
from loguru import logger
from config import Config
from binance_client import BinanceFuturesClient
from technical_analysis import TechnicalAnalyzer
from train_ai_improved import (
    prepare_advanced_features,
    detect_candlestick_patterns,
    calculate_trend_features,
    get_htf_features_for_training,
    align_features_to_model,
)
from continuous_learning_engine import ContinuousLearningEngine

# Advanced AI Engine disabled — bot uses V7 GB ensemble models
# Importing it triggers TensorFlow import (15-20s delay on servers without TF)
HAS_ADVANCED_AI = False

class SmartBotEngine:
    """
    Bot engine thông minh với:
    - Pre-flight checks đầy đủ
    - Risk management tích hợp
    - AI model prediction với confidence
    - Multi-timeframe analysis
    - Position management thông minh
    """
    
    def __init__(self, config=None):
        self.client = BinanceFuturesClient()
        self.analyzer = TechnicalAnalyzer()
        self.is_running = False
        self.is_paused = False
        self.mode = 'semi-auto'  # auto, semi-auto, manual
        
        # ADVANCED AI ENGINE (NEW!)
        if HAS_ADVANCED_AI:
            self.advanced_ai = AdvancedAIEngine(self.client, self.analyzer)
            logger.info("🧠 Advanced AI Engine initialized")
        else:
            self.advanced_ai = None
        
        # CONTINUOUS LEARNING ENGINE
        self.learning_engine = ContinuousLearningEngine()
        self.learning_task = None  # Background learning task
        
        # Load risk config from Config
        cfg = Config.get_config()
        risk_cfg = cfg.get('risk_management', {})
        trading_cfg = cfg.get('trading', {})
        
        # Risk settings - An toàn, tối ưu R:R
        self.risk_settings = config or {
            'max_leverage': trading_cfg.get(
                'max_leverage', 40
            ),
            'max_position_size': risk_cfg.get(
                'max_position_size_percent', 30
            ),
            'daily_max_loss': risk_cfg.get(
                'max_daily_loss_percent', 5
            ),
            'max_positions': trading_cfg.get(
                'max_open_positions', 3
            ),
            'force_sl': True,
            'force_tp': True,
            'min_confidence': 60,
            'sl_percentage': risk_cfg.get('stop_loss_percent', 1.5),
            'tp_percentage': risk_cfg.get('take_profit_percent', 3),
            'trailing_stop_pct': risk_cfg.get(
                'trailing_stop_percent', 0.8
            ),
            'breakeven_trigger_pct': risk_cfg.get(
                'breakeven_trigger_percent', 1.0
            ),
            'partial_tp_enabled': risk_cfg.get(
                'partial_tp_enabled', True
            ),
            'partial_tp_levels': risk_cfg.get(
                'partial_tp_levels', [0.5, 0.3, 0.2]
            ),
            'min_adx_trend': risk_cfg.get('min_adx_trend', 10),
            'max_correlation_same_dir': risk_cfg.get(
                'max_correlation_same_direction', 2
            ),
            'max_funding_rate': risk_cfg.get(
                'max_funding_rate', 0.05
            ),
            'volatility_spike_mult': risk_cfg.get(
                'volatility_spike_multiplier', 3.0
            ),
            'max_drawdown_pct': risk_cfg.get(
                'max_drawdown_percent', 10
            ),
            'min_start_balance': risk_cfg.get(
                'min_start_balance_usd', 1.0
            ),
            'force_entry_on_signal': risk_cfg.get(
                'force_entry_on_signal', True
            ),
            # Mục tiêu lãi tối thiểu mỗi lệnh (USD)
            # $4 ≈ 100k VND — bot scale position nếu cần
            'min_profit_target_usd': risk_cfg.get(
                'min_profit_target_usd', 4.0
            ),
            # Leverage theo symbol — 35-40x tối ưu cho từng coin
            'symbol_leverage': trading_cfg.get(
                'symbol_leverage', {
                    'BTCUSDT': 40,
                    'ETHUSDT': 38,
                    'SOLUSDT': 35,
                    'ADAUSDT': 35
                }
            ),
            # === AUTO-CLOSE PROTECTIONS ===
            'max_hold_hours': risk_cfg.get(
                'max_hold_hours', 24
            ),
            'max_loss_per_position': risk_cfg.get(
                'max_loss_per_position_pct', 5.0
            ),
            'signal_reversal_close': risk_cfg.get(
                'signal_reversal_close', True
            ),
        }
        
        # Tracking
        self.positions = {}
        self.pending_signals = []
        self.today_pnl = 0
        self.today_trades = 0
        self.today_wins = 0
        self.session_start = datetime.now()
        self.peak_balance = 0  # For drawdown tracking
        self.position_monitor_task = None  # Monitor loop
        self.atr_history = {}  # ATR tracking per symbol
        self._tick_size_cache = {}  # Cache tick_size per symbol
        self._qty_precision_cache = {}  # Cache qty precision per symbol
        self._exchange_info_cache = None  # Cache exchange info
        self._exchange_info_ts = 0  # Timestamp of last fetch
        self.latest_analysis = {}  # Cache latest analysis per symbol for dashboard
        
        # Restore session state from previous run (same day only)
        self._load_session_state()
        
        # Load AI models
        self.models = {}
        self.load_models()
    
    def load_models(self):
        """Load trained AI models - Ưu tiên Advanced AI, fallback về basic models"""
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        # Try loading Advanced AI models first
        if self.advanced_ai:
            advanced_loaded = 0
            for symbol in symbols:
                try:
                    import os
                    model_path = f'models/advanced_{symbol}_ensemble.pkl'
                    if os.path.exists(model_path):
                        from advanced_ai_engine import EnsemblePredictor
                        ensemble = EnsemblePredictor()
                        if ensemble.load(f'models/advanced_{symbol}'):
                            self.advanced_ai.ensembles[symbol] = ensemble
                            advanced_loaded += 1
                            logger.info(f"🧠 Loaded Advanced AI for {symbol}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not load Advanced AI for {symbol}: {e}")
            
            if advanced_loaded > 0:
                logger.info(f"✅ Loaded {advanced_loaded} Advanced AI models")
        
        # Fallback: Load basic gradient boost models
        for symbol in symbols:
            try:
                model_path = f'models/gradient_boost_{symbol}.pkl'
                model_data = joblib.load(model_path)
                self.models[symbol] = model_data
                logger.info(f"✅ Loaded basic model for {symbol} (accuracy: {model_data['accuracy']:.1f}%)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load basic model for {symbol}: {e}")
    
    async def pre_flight_check(self):
        """
        🛫 PRE-FLIGHT CHECK - Kiểm tra trước khi start bot
        Đảm bảo mọi thứ OK trước khi trade
        BƯỚC THÊM: Kiểm tra và auto-retrain models nếu cần
        """
        logger.info("="*60)
        logger.info("🛫 PRE-FLIGHT CHECK")
        logger.info("="*60)
        
        checks = []
        
        # 0. Skip auto-retrain during startup for speed
        # (Continuous learning runs in background instead)
        logger.info(
            "0️⃣ Models: Using existing trained models"
        )
        checks.append(True)
        
        # 1. Check API connection
        logger.info("1️⃣ Checking API connection...")
        try:
            account = self.client.client.futures_account()
            logger.info("   ✅ API connected")
            checks.append(True)
        except Exception as e:
            logger.error(f"   ❌ API connection failed: {e}")
            checks.append(False)
            return False, "API connection failed"
        
        # 2. Check balance
        logger.info("2️⃣ Checking account balance...")
        try:
            balance = float(account['totalWalletBalance'])
            available = float(account['availableBalance'])

            min_balance = float(
                self.risk_settings.get('min_start_balance', 1.0)
            )
            if balance < min_balance:
                logger.error(f"   ❌ Balance too low: ${balance:.2f} < ${min_balance}")
                checks.append(False)
                return False, (
                    f"Balance too low: ${balance:.2f} "
                    f"(minimum ${min_balance:.2f})"
                )
            
            logger.info(f"   ✅ Balance: ${balance:.2f} (Available: ${available:.2f})")
            checks.append(True)
        except Exception as e:
            logger.error(f"   ❌ Balance check failed: {e}")
            checks.append(False)
            return False, "Balance check failed"
        
        # 3. Check risk settings
        logger.info("3️⃣ Validating risk settings...")
        if not self.validate_risk_settings():
            logger.error("   ❌ Invalid risk settings")
            checks.append(False)
            return False, "Invalid risk settings"
        
        logger.info(f"   ✅ Max Leverage: {self.risk_settings['max_leverage']}x")
        logger.info(f"   ✅ Max Position Size: {self.risk_settings['max_position_size']}%")
        logger.info(f"   ✅ Daily Max Loss: {self.risk_settings['daily_max_loss']}%")
        logger.info(f"   ✅ Max Positions: {self.risk_settings['max_positions']}")
        checks.append(True)
        
        # 4. Check AI models loaded
        logger.info("4️⃣ Checking AI models...")
        if len(self.models) == 0:
            logger.error("   ❌ No AI models loaded")
            checks.append(False)
            return False, "No AI models loaded"
        
        logger.info(f"   ✅ {len(self.models)} models loaded: {list(self.models.keys())}")
        checks.append(True)
        
        # 5. Check current positions
        logger.info("5️⃣ Checking current positions...")
        current_positions = await self.get_current_positions()
        logger.info(f"   ℹ️ Current positions: {len(current_positions)}")
        
        # 6. Check today's loss limit
        # today_pnl is in % units (sum of trade profits in %)
        # daily_max_loss is also in % — compare % vs %
        logger.info("6️⃣ Checking daily loss limit...")
        daily_max_loss_pct = self.risk_settings['daily_max_loss']
        if abs(self.today_pnl) >= daily_max_loss_pct:
            logger.error(f"   ❌ Daily loss limit reached: {abs(self.today_pnl):.1f}% >= {daily_max_loss_pct}%")
            checks.append(False)
            return False, "Daily loss limit reached"
        
        logger.info(f"   ✅ Today's PnL: {self.today_pnl:.1f}% / Max Loss: {daily_max_loss_pct}%")
        checks.append(True)
        
        # Summary
        logger.info("="*60)
        if all(checks):
            logger.info("✅ PRE-FLIGHT CHECK PASSED - Ready to start!")
            logger.info("="*60)
            return True, "All checks passed"
        else:
            logger.error("❌ PRE-FLIGHT CHECK FAILED")
            logger.info("="*60)
            return False, "Pre-flight check failed"
    
    def validate_risk_settings(self):
        """Validate risk settings"""
        try:
            # Check ranges
            if not (1 <= self.risk_settings['max_leverage'] <= 125):
                return False
            if not (0.1 <= self.risk_settings['max_position_size'] <= 100):
                return False
            if not (0.5 <= self.risk_settings['daily_max_loss'] <= 50):
                return False
            if not (1 <= self.risk_settings['max_positions'] <= 10):
                return False
            if not (0 <= self.risk_settings['min_start_balance'] <= 100000):
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error validating risk settings: {e}")
            return False
    
    async def get_current_positions(self):
        """Get current open positions"""
        try:
            positions = self.client.client.futures_position_information()
            active_positions = []
            
            for pos in positions:
                position_amt = float(pos['positionAmt'])
                if position_amt != 0:
                    active_positions.append({
                        'symbol': pos['symbol'],
                        'size': abs(position_amt),
                        'side': 'LONG' if position_amt > 0 else 'SHORT',
                        'entry_price': float(pos['entryPrice']),
                        'unrealized_pnl': float(pos['unRealizedProfit'])
                    })
            
            return active_positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    async def analyze_symbol(self, symbol):
        """
        🧠 Phân tích symbol với AI model
        ƯU TIÊN: Advanced AI Engine (Deep Learning + Ensemble)
        FALLBACK: Basic gradient boost model
        
        Returns: {
            'signal': 'LONG' / 'SHORT' / 'HOLD',
            'confidence': 0-100,
            'entry_price': float,
            'stop_loss': float,
            'take_profit': float,
            'reasoning': str
        }
        """
        try:
            # ========== TRY ADVANCED AI FIRST ==========
            if self.advanced_ai and symbol in self.advanced_ai.ensembles:
                logger.debug(f"🧠 Using Advanced AI for {symbol}")
                signal_data = self.advanced_ai.get_signal(symbol)
                
                if signal_data:
                    # Extract RSI from momentum data
                    _adv_rsi = 50
                    if signal_data.get('momentum'):
                        _adv_rsi = signal_data[
                            'momentum'
                        ].get('rsi', 50)
                    
                    reasoning = (
                        self
                        ._generate_advanced_reasoning(
                            signal_data
                        )
                    )
                    
                    result = {
                        'symbol': symbol,
                        'signal': signal_data['signal'],
                        'confidence': signal_data[
                            'confidence'
                        ],
                        'entry_price': signal_data[
                            'price'
                        ],
                        'stop_loss': signal_data[
                            'stop_loss'
                        ],
                        'take_profit': signal_data[
                            'take_profit'
                        ],
                        'reasoning': reasoning,
                        'rsi': _adv_rsi,
                        'timestamp': signal_data.get(
                            'timestamp'
                        ),
                        'ai_type': 'advanced',
                    }
                    self.latest_analysis[symbol] = result
                    return result
            
            # ========== FALLBACK TO BASIC MODEL ==========
            if symbol not in self.models:
                logger.warning(f"⚠️ No model for {symbol} — returning HOLD")
                klines = self.client.get_klines(symbol, "5m", 5)
                current_price = float(klines[-1][4]) if klines else 0
                return {
                    'symbol': symbol,
                    'signal': 'HOLD',
                    'confidence': 0,
                    'entry_price': current_price,
                    'stop_loss': None,
                    'take_profit': None,
                    'reasoning': 'No model loaded for this symbol',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            
            logger.debug(f"📊 Using basic model for {symbol}")
            model_data = self.models[symbol]
            
            # Get latest data
            klines = self.client.get_klines(symbol, "5m", 100)
            if not klines:
                return None
            
            # Prepare features
            df = self.analyzer.prepare_dataframe(klines)
            df = self.analyzer.add_basic_indicators(df)
            df = self.analyzer.add_advanced_indicators(df)
            
            # Fetch HTF data and merge (match training pipeline)
            try:
                htf_dfs = get_htf_features_for_training(
                    self.client, self.analyzer, symbol
                )
                if htf_dfs:
                    df['timestamp'] = pd.to_numeric(
                        df['timestamp']
                    )
                    df = df.sort_values('timestamp')
                    for label, htf_df in htf_dfs.items():
                        htf_df['timestamp'] = pd.to_numeric(
                            htf_df['timestamp']
                        )
                        htf_df = htf_df.sort_values('timestamp')
                        df = pd.merge_asof(
                            df, htf_df,
                            on='timestamp',
                            direction='backward'
                        )
            except Exception as htf_err:
                logger.debug(
                    f"HTF fetch error for {symbol}: {htf_err}"
                )
            
            # Get features for prediction
            X, feat_names = prepare_advanced_features(df)
            X = align_features_to_model(
                X, feat_names, model_data
            )
            latest_features = X[-1].reshape(1, -1)
            
            # Predict — ensemble all available models
            ensemble_models = [model_data['model']]
            for mkey in ['model_xgb', 'model_hgb']:
                if mkey in model_data:
                    ensemble_models.append(model_data[mkey])
            all_probs = [
                m.predict_proba(latest_features)[0]
                for m in ensemble_models
            ]
            probabilities = np.mean(all_probs, axis=0)
            n_classes = len(probabilities)
            
            if n_classes == 2:
                # V6 Binary model: [SHORT(0), LONG(1)]
                prob_short = probabilities[0] * 100
                prob_long = probabilities[1] * 100
                prob_hold = 0

                # ===== FIX: ALWAYS CHECK MARKET TREND FIRST =====
                # Get actual market indicators
                rsi = float(df['rsi'].iloc[-1]) if 'rsi' in df.columns else 50
                # Safe price_change calculation (prevent division by zero)
                price_5_ago = float(df['close'].iloc[-5]) if len(df) >= 5 else float(df['close'].iloc[0])
                price_now = float(df['close'].iloc[-1])
                price_change = ((price_now - price_5_ago) / price_5_ago * 100) if price_5_ago > 0 else 0

                # EMA trend check (short vs long EMA)
                ema_short = float(df['ema_9'].iloc[-1]) if 'ema_9' in df.columns else float(df['close'].iloc[-1])
                ema_long = float(df['ema_21'].iloc[-1]) if 'ema_21' in df.columns else float(df['close'].iloc[-1])
                ema_trend = 'bullish' if ema_short > ema_long else 'bearish'

                confidence = max(prob_short, prob_long)

                # RULE 1: Strong bearish trend → SHORT (price dropping, RSI low)
                if price_change < -0.5 or (price_change < -0.2 and rsi < 45):
                    signal = 'SHORT'
                    confidence = max(prob_short, 60)
                    logger.info(f"   📉 {symbol} BEARISH trend: price={price_change:.2f}%, RSI={rsi:.1f} → SHORT")

                # RULE 2: Strong bullish trend → LONG (price rising, RSI high)
                elif price_change > 0.5 or (price_change > 0.2 and rsi > 55):
                    signal = 'LONG'
                    confidence = max(prob_long, 60)
                    logger.info(f"   📈 {symbol} BULLISH trend: price={price_change:.2f}%, RSI={rsi:.1f} → LONG")

                # RULE 3: Moderate bearish (price negative + EMA bearish)
                elif price_change < 0 and ema_trend == 'bearish':
                    signal = 'SHORT'
                    confidence = max(prob_short, 55)
                    logger.info(f"   📉 {symbol} Moderate bearish: price={price_change:.2f}%, EMA={ema_trend} → SHORT")

                # RULE 4: Moderate bullish (price positive + EMA bullish)
                elif price_change > 0 and ema_trend == 'bullish':
                    signal = 'LONG'
                    confidence = max(prob_long, 55)
                    logger.info(f"   📈 {symbol} Moderate bullish: price={price_change:.2f}%, EMA={ema_trend} → LONG")

                # RULE 5: RSI extreme zones
                elif rsi < 35:
                    signal = 'SHORT'  # Oversold but momentum DOWN
                    confidence = max(prob_short, 55)
                    logger.info(f"   📉 {symbol} RSI extreme low={rsi:.1f} → SHORT")
                elif rsi > 65:
                    signal = 'LONG'  # Overbought but momentum UP
                    confidence = max(prob_long, 55)
                    logger.info(f"   📈 {symbol} RSI extreme high={rsi:.1f} → LONG")

                # RULE 6: Mixed signals - use model probability as tiebreaker
                else:
                    if prob_long >= prob_short + 10:  # Model strongly favors LONG
                        signal = 'LONG'
                    elif prob_short >= prob_long + 10:  # Model strongly favors SHORT
                        signal = 'SHORT'
                    elif rsi < 50:  # Slight bearish bias
                        signal = 'SHORT'
                    else:  # Slight bullish bias
                        signal = 'LONG'
                    logger.info(f"   ⚖️ {symbol} Mixed: price={price_change:.2f}%, RSI={rsi:.1f}, L={prob_long:.1f}%/S={prob_short:.1f}% → {signal}")
            else:
                # Legacy 3-class model: [SHORT(-1), HOLD(0), LONG(1)]
                prediction = ensemble_models[0].predict(latest_features)[0]
                prob_short = probabilities[0] * 100
                prob_hold = probabilities[1] * 100
                prob_long = probabilities[2] * 100

                signal_map = {-1: 'SHORT', 0: 'HOLD', 1: 'LONG'}
                signal = signal_map[prediction]

                class_idx = int(prediction) + 1
                confidence = probabilities[class_idx] * 100

                # Never return HOLD - always decide LONG or SHORT based on ACTUAL TREND
                if signal == 'HOLD':
                    # Use actual market trend to decide
                    rsi = float(df['rsi'].iloc[-1]) if 'rsi' in df.columns else 50
                    # Safe price_change calculation
                    price_5_ago = float(df['close'].iloc[-5]) if len(df) >= 5 else float(df['close'].iloc[0])
                    price_now = float(df['close'].iloc[-1])
                    price_change = ((price_now - price_5_ago) / price_5_ago * 100) if price_5_ago > 0 else 0

                    # Prioritize actual trend over model probability
                    if price_change < -0.3 or rsi < 45:
                        signal = 'SHORT'
                        confidence = max(prob_short, 55)
                    elif price_change > 0.3 or rsi > 55:
                        signal = 'LONG'
                        confidence = max(prob_long, 55)
                    elif rsi < 50:
                        signal = 'SHORT'
                        confidence = max(prob_short, 50)
                    else:
                        signal = 'LONG'
                        confidence = max(prob_long, 50)
            
            logger.info(
                f"   📊 {symbol} probs: "
                f"L={prob_long:.1f}% H={prob_hold:.1f}% "
                f"S={prob_short:.1f}% → {signal}"
            )
            
            # Get current price
            current_price = float(df['close'].iloc[-1])
            
            # ===== MULTI-TIMEFRAME CONFIRMATION =====
            mtf_score = 0  # -2 to +2
            mtf_reasons = []
            for htf in ['15m', '1h']:
                try:
                    htf_klines = self.client.get_klines(
                        symbol, htf, 60
                    )
                    if htf_klines:
                        htf_df = self.analyzer.prepare_dataframe(
                            htf_klines
                        )
                        htf_df = self.analyzer.add_basic_indicators(
                            htf_df
                        )
                        last = htf_df.iloc[-1]
                        # EMA trend
                        if ('ema_50' in htf_df.columns
                                and 'ema_200' in htf_df.columns):
                            if last['ema_50'] > last['ema_200']:
                                mtf_score += 1
                                mtf_reasons.append(
                                    f"{htf} uptrend"
                                )
                            else:
                                mtf_score -= 1
                                mtf_reasons.append(
                                    f"{htf} downtrend"
                                )
                except Exception:
                    pass
            
            # Adjust confidence based on MTF alignment
            # BUT: skip boost if recent momentum contradicts
            # the MTF lagging EMA direction.
            _mtf_boost_ok = True
            try:
                _cls = df['close'].values.astype(float)
                if len(_cls) >= 13:
                    _med = (_cls[-1] - _cls[-13]) / _cls[-13] * 100
                    # If signal is SHORT but price rising >1% in 1h → skip MTF boost
                    if signal == 'SHORT' and _med > 1.0:
                        _mtf_boost_ok = False
                        mtf_reasons.append("MTF boost blocked (price +" + f"{_med:.1f}%" + ")")
                    elif signal == 'LONG' and _med < -1.0:
                        _mtf_boost_ok = False
                        mtf_reasons.append("MTF boost blocked (price " + f"{_med:.1f}%" + ")")
            except Exception:
                pass

            if signal == 'LONG' and mtf_score >= 2 and _mtf_boost_ok:
                confidence = min(100, confidence * 1.1)
                mtf_reasons.append("MTF aligned +10%")
            elif signal == 'SHORT' and mtf_score <= -2 and _mtf_boost_ok:
                confidence = min(100, confidence * 1.1)
                mtf_reasons.append("MTF aligned +10%")
            elif (signal == 'LONG' and mtf_score < 0) or \
                 (signal == 'SHORT' and mtf_score > 0):
                confidence *= 0.85
                mtf_reasons.append("MTF conflict -15%")
            
            # ===== SOL CONFIDENCE GATE (disabled) =====
            # Now using same min_confidence for all symbols
            
            # Calculate SL/TP
            if signal == 'LONG':
                stop_loss = current_price * (1 - self.risk_settings['sl_percentage'] / 100)
                take_profit = current_price * (1 + self.risk_settings['tp_percentage'] / 100)
            elif signal == 'SHORT':
                stop_loss = current_price * (1 + self.risk_settings['sl_percentage'] / 100)
                take_profit = current_price * (1 - self.risk_settings['tp_percentage'] / 100)
            else:
                stop_loss = None
                take_profit = None
            
            # Generate reasoning
            reasoning = self.generate_reasoning(
                df, signal, confidence
            )
            if mtf_reasons:
                reasoning += " | 🔄 MTF: " + ", ".join(
                    mtf_reasons
                )

            # Extract RSI for dashboard cache
            _basic_rsi = (
                float(df['rsi'].iloc[-1])
                if 'rsi' in df.columns
                else 50
            )

            # ============================================
            # 🚨 REAL-TIME MOMENTUM SANITY CHECK
            # (basic model path)
            # Prevent counter-trend when price is strongly
            # moving in one direction.
            # ============================================
            signal, confidence = self._momentum_filter(
                symbol, signal, confidence, df
            )

            # Recalculate SL/TP after possible signal change
            if signal == 'LONG':
                sl_pct = self.risk_settings['sl_percentage']
                tp_pct = self.risk_settings['tp_percentage']
                stop_loss = current_price * (1 - sl_pct / 100)
                take_profit = current_price * (
                    1 + tp_pct / 100
                )
            elif signal == 'SHORT':
                sl_pct = self.risk_settings['sl_percentage']
                tp_pct = self.risk_settings['tp_percentage']
                stop_loss = current_price * (1 + sl_pct / 100)
                take_profit = current_price * (
                    1 - tp_pct / 100
                )
            else:
                stop_loss = None
                take_profit = None

            result = {
                'symbol': symbol,
                'signal': signal,
                'confidence': confidence,
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'reasoning': reasoning,
                'rsi': _basic_rsi,
                'timestamp': datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S'
                ),
            }
            self.latest_analysis[symbol] = result
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            err_result = {
                'symbol': symbol,
                'signal': 'HOLD',
                'confidence': 0,
                'entry_price': 0,
                'stop_loss': None,
                'take_profit': None,
                'reasoning': f'Analysis error: {e}',
                'timestamp': datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S'
                )
            }
            self.latest_analysis[symbol] = err_result
            return err_result

    def _generate_advanced_reasoning(self, signal_data):
        """Generate reasoning from Advanced AI signal"""
        try:
            reasoning = []
            
            # Signal type
            signal = signal_data.get('signal', 'HOLD')
            confidence = signal_data.get('confidence', 0)
            
            if signal == 'LONG':
                reasoning.append("🟢 LONG Signal")
            elif signal == 'SHORT':
                reasoning.append("🔴 SHORT Signal")
            else:
                reasoning.append("⚪ HOLD")
            
            # Pattern score
            pattern_score = signal_data.get('pattern_score', 0)
            if pattern_score > 50:
                reasoning.append(f"📊 Strong bullish patterns (+{pattern_score:.0f})")
            elif pattern_score < -50:
                reasoning.append(f"📊 Strong bearish patterns ({pattern_score:.0f})")
            
            # Model votes
            votes = signal_data.get('model_votes', {})
            if votes:
                long_votes = sum(1 for v in votes.values() if isinstance(v, dict) and v.get('pred') == 1)
                short_votes = sum(1 for v in votes.values() if isinstance(v, dict) and v.get('pred') == -1)
                total_models = len(votes)
                
                if long_votes > 0:
                    reasoning.append(f"🧠 {long_votes}/{total_models} models vote LONG")
                if short_votes > 0:
                    reasoning.append(f"🧠 {short_votes}/{total_models} models vote SHORT")
            
            # Confidence
            reasoning.append(f"🎯 Ensemble Confidence: {confidence:.1f}%")
            
            return " | ".join(reasoning)
            
        except Exception as e:
            return f"Advanced AI prediction (confidence: {signal_data.get('confidence', 0):.1f}%)"
    
    def generate_reasoning(self, df, signal, confidence):
        """Generate human-readable reasoning"""
        try:
            latest = df.iloc[-1]
            reasoning = []
            
            # Trend
            if 'ema_50' in df.columns and 'ema_200' in df.columns:
                if latest['ema_50'] > latest['ema_200']:
                    reasoning.append("📈 Uptrend (EMA50 > EMA200)")
                else:
                    reasoning.append("📉 Downtrend (EMA50 < EMA200)")
            
            # RSI
            if 'rsi' in df.columns:
                rsi = latest['rsi']
                if rsi < 30:
                    reasoning.append(f"🔵 Oversold (RSI: {rsi:.1f})")
                elif rsi > 70:
                    reasoning.append(f"🔴 Overbought (RSI: {rsi:.1f})")
            
            # ADX
            if 'adx' in df.columns:
                adx = latest['adx']
                if adx > 40:
                    reasoning.append(f"💪 Strong trend (ADX: {adx:.1f})")
                elif adx > 25:
                    reasoning.append(f"📊 Trending (ADX: {adx:.1f})")
            
            # Volume
            if 'volume' in df.columns:
                vol_ma = df['volume'].rolling(20).mean().iloc[-1]
                if latest['volume'] > vol_ma * 1.5:
                    reasoning.append("📊 High volume")
            
            reasoning.append(f"🎯 Confidence: {confidence:.1f}%")
            
            return " | ".join(reasoning)
            
        except Exception as e:
            return f"AI Model prediction (confidence: {confidence:.1f}%)"

    def _quality_gate(self, symbol, signal_data):
        """
        Extra quality checks to boost win rate.
        Returns skip reason string, or None if OK.
        """
        try:
            signal = signal_data.get('signal', 'HOLD')
            confidence = signal_data.get('confidence', 0)

            # 1. Require trending market (ADX > 20)
            klines = self.client.get_klines(symbol, '5m', 30)
            if klines:
                df = self.analyzer.prepare_dataframe(klines)
                df = self.analyzer.add_basic_indicators(df)
                last = df.iloc[-1]

                adx = last.get('adx', 0)
                if adx and adx < 20:
                    return (
                        f"Ranging market (ADX={adx:.0f}<20)"
                    )

                rsi = last.get('rsi', 50)
                # 2. Don't LONG into overbought
                if signal == 'LONG' and rsi and rsi > 75:
                    return (
                        f"Overbought RSI={rsi:.0f} for LONG"
                    )
                # 3. Don't SHORT into oversold
                if signal == 'SHORT' and rsi and rsi < 25:
                    return (
                        f"Oversold RSI={rsi:.0f} for SHORT"
                    )

                # 4. Check BB squeeze — avoid trading
                # in low-volatility compression
                bb_w = last.get('bb_width', None)
                if bb_w is not None and bb_w < 0.005:
                    return (
                        f"BB squeeze (width={bb_w:.4f})"
                    )

            # 5. Model agreement check (advanced AI)
            votes = signal_data.get('model_votes', {})
            if votes and len(votes) >= 3:
                agree_count = sum(
                    1 for v in votes.values()
                    if isinstance(v, dict)
                    and v.get('pred') == (
                        1 if signal == 'LONG' else -1
                    )
                )
                # Require at least 50% of models to agree
                if agree_count < len(votes) / 2:
                    return (
                        f"Low model agreement "
                        f"({agree_count}/{len(votes)})"
                    )

        except Exception as e:
            logger.debug(f"Quality gate error: {e}")

        return None  # All checks passed

    def _momentum_filter(
        self, symbol, signal, confidence, df
    ):
        """
        📈 Real-time momentum sanity check (basic model path).
        Prevents counter-trend trades when price is strongly
        moving in one direction.
        Returns (signal, confidence) - possibly modified.
        """
        try:
            closes = df['close'].values.astype(float)
            opens = df['open'].values.astype(float)
            if len(closes) < 15:
                return signal, confidence

            price = closes[-1]

            # Short-term change (last 3 candles ~15min)
            short_pct = (
                (price - closes[-4]) / closes[-4]
            ) * 100 if len(closes) >= 4 else 0

            # Medium-term change (last 12 candles ~1h)
            med_pct = (
                (price - closes[-13]) / closes[-13]
            ) * 100 if len(closes) >= 13 else 0

            # Consecutive green/red candles
            consec_g, consec_r = 0, 0
            for i in range(
                len(closes) - 1,
                max(0, len(closes) - 12), -1
            ):
                if closes[i] > opens[i]:
                    if consec_r == 0:
                        consec_g += 1
                    else:
                        break
                elif closes[i] < opens[i]:
                    if consec_g == 0:
                        consec_r += 1
                    else:
                        break
                else:
                    break

            # RSI
            rsi = float(df['rsi'].iloc[-1]) if 'rsi' in df.columns else 50

            # EMA distance
            ema_dist = 0
            if 'sma_20' in df.columns:
                ema20 = float(df['sma_20'].iloc[-1])
                if ema20 > 0:
                    ema_dist = (
                        (price - ema20) / ema20
                    ) * 100

            # Aggregate direction score
            dir_score = 0.0
            dir_score += (
                (1 if short_pct > 0 else -1)
                * min(abs(short_pct) * 8, 30)
            ) if short_pct != 0 else 0
            dir_score += (
                (1 if med_pct > 0 else -1)
                * min(abs(med_pct) * 5, 25)
            ) if med_pct != 0 else 0
            dir_score += consec_g * 3
            dir_score -= consec_r * 3
            dir_score += (
                (1 if ema_dist > 0 else -1)
                * min(abs(ema_dist) * 5, 10)
            ) if ema_dist != 0 else 0
            # RSI contribution
            if rsi > 55:
                dir_score += min((rsi - 50) * 0.3, 8)
            elif rsi < 45:
                dir_score -= min((50 - rsi) * 0.3, 8)

            mom_dir = (
                1 if dir_score > 0
                else (-1 if dir_score < 0 else 0)
            )
            mom_str = min(abs(dir_score), 100)

            original = signal

            # Block counter-trend on VERY strong momentum only (60+)
            # Relaxed from 25 to allow more SHORT entries
            if mom_str >= 60:
                if signal == 'SHORT' and mom_dir > 0:
                    logger.warning(
                        f"   🚫 BLOCKED SHORT {symbol}: "
                        f"very strong bullish momentum "
                        f"str={mom_str:.0f}"
                    )
                    signal, confidence = 'HOLD', 0
                elif signal == 'LONG' and mom_dir < 0:
                    logger.warning(
                        f"   🚫 BLOCKED LONG {symbol}: "
                        f"very strong bearish momentum "
                        f"str={mom_str:.0f}"
                    )
                    signal, confidence = 'HOLD', 0

            # Removed consecutive candle blocking - too restrictive

            # Confidence boost when aligned
            if signal != 'HOLD' and mom_str >= 20:
                if ((signal == 'LONG' and mom_dir > 0)
                        or (signal == 'SHORT'
                            and mom_dir < 0)):
                    boost = min(mom_str * 0.15, 12)
                    confidence = min(
                        100, confidence + boost
                    )

            if signal != original:
                logger.info(
                    f"   📊 Signal {original}→{signal} "
                    f"(momentum filter)"
                )

        except Exception as e:
            logger.warning(
                f"Momentum filter error: {e}"
            )
        return signal, confidence

    async def check_risk_before_trade(
        self, symbol, side, bypass_soft_filters=False
    ):
        """
        ⚠️ Check risk limits before opening position
        V2: Thêm market regime, correlation, funding rate,
            volatility spike, drawdown check
        """
        # Check max positions
        current_positions = await self.get_current_positions()
        if len(current_positions) >= self.risk_settings[
            'max_positions'
        ]:
            logger.warning(
                f"⚠️ Max positions reached: "
                f"{len(current_positions)}/"
                f"{self.risk_settings['max_positions']}"
            )
            return False, "Max positions reached"
        
        # Check daily loss
        # today_pnl is in % units — compare % vs %
        account = self.client.client.futures_account()
        balance = float(account['totalWalletBalance'])
        daily_max_loss_pct = self.risk_settings['daily_max_loss']
        
        if abs(self.today_pnl) >= daily_max_loss_pct:
            logger.warning(
                f"⚠️ Daily loss limit: "
                f"{abs(self.today_pnl):.1f}% >= {daily_max_loss_pct}%"
            )
            return False, "Daily loss limit reached"

        # Check duplicate position - only block SAME direction (hedge mode allows opposite)
        for pos in current_positions:
            if pos['symbol'] == symbol:
                pos_side = pos.get('positionSide', pos.get('side', '')).upper()
                # In hedge mode, can have both LONG and SHORT on same symbol
                if pos_side == side.upper():
                    logger.warning(
                        f"⚠️ Already has {side} position in {symbol}"
                    )
                    return False, f"Already has {side} {symbol}"
                else:
                    logger.info(
                        f"   ℹ️ Has {pos_side} position, allowing {side} entry (hedge mode)"
                    )

        # === NEW: Drawdown check ===
        if self.peak_balance > 0:
            dd_pct = (
                (self.peak_balance - balance)
                / self.peak_balance * 100
            )
            max_dd = self.risk_settings.get(
                'max_drawdown_pct', 10
            )
            if dd_pct >= max_dd:
                logger.warning(
                    f"🚨 Max drawdown reached: "
                    f"{dd_pct:.1f}% >= {max_dd}%"
                )
                return False, "Max drawdown reached"
            if dd_pct >= max_dd * 0.8:
                logger.warning(
                    f"⚠️ Drawdown warning: {dd_pct:.1f}% "
                    f"(80% of {max_dd}%) - reducing size"
                )
        
        if not bypass_soft_filters:
            # === NEW: Market regime filter (ADX) ===
            regime_ok, regime_msg = await self.check_market_regime(
                symbol
            )
            if not regime_ok:
                return False, regime_msg

            # === NEW: Correlation check ===
            corr_ok, corr_msg = await self.check_correlation(
                symbol, side, current_positions
            )
            if not corr_ok:
                return False, corr_msg

            # === NEW: Funding rate check ===
            fund_ok, fund_msg = await self.check_funding_rate(
                symbol, side
            )
            if not fund_ok:
                return False, fund_msg

            # === NEW: Volatility spike check ===
            vol_ok, vol_msg = await self.check_volatility_spike(
                symbol
            )
            if not vol_ok:
                return False, vol_msg
        else:
            logger.info(
                f"   ⚡ Startup priority entry for {symbol}: "
                f"bypassing soft filters"
            )
        
        return True, "OK"
    
    async def check_market_regime(self, symbol):
        """
        📊 Market regime filter - ADX based
        Chỉ trade khi thị trường trending (ADX > min_adx)
        """
        try:
            min_adx = self.risk_settings.get('min_adx_trend', 10)
            klines = self.client.get_klines(symbol, "15m", 60)
            if not klines:
                return True, "OK"  # Skip check if no data
            
            df = self.analyzer.prepare_dataframe(klines)
            df = self.analyzer.add_basic_indicators(df)
            
            if 'adx' not in df.columns:
                return True, "OK"
            
            current_adx = float(df['adx'].iloc[-1])
            
            if current_adx < min_adx:
                logger.info(
                    f"   📊 {symbol} ADX={current_adx:.1f} "
                    f"< {min_adx} (sideways) → SKIP"
                )
                return False, (
                    f"Sideways market ADX={current_adx:.1f}"
                )
            
            logger.info(
                f"   📊 {symbol} ADX={current_adx:.1f} → "
                f"Trending ✅"
            )
            return True, "OK"
        except Exception as e:
            logger.warning(f"ADX check error: {e}")
            return True, "OK"
    
    async def check_correlation(
        self, symbol, side, current_positions
    ):
        """
        🔗 Correlation check - BTC/ETH/SOL highly correlated
        Max N same-direction positions
        """
        try:
            max_same = self.risk_settings.get(
                'max_correlation_same_dir', 2
            )
            same_dir_count = sum(
                1 for p in current_positions
                if p['side'] == side
            )
            
            if same_dir_count >= max_same:
                logger.warning(
                    f"⚠️ {same_dir_count} {side} positions "
                    f"already open (max {max_same})"
                )
                return False, (
                    f"Max {max_same} same-direction positions"
                )
            
            return True, "OK"
        except Exception as e:
            logger.warning(f"Correlation check error: {e}")
            return True, "OK"
    
    async def check_funding_rate(self, symbol, side):
        """
        💰 Funding rate check
        Skip nếu funding rate quá cao ngược hướng
        """
        try:
            max_funding = self.risk_settings.get(
                'max_funding_rate', 0.05
            )
            
            funding = self.client.client.futures_funding_rate(
                symbol=symbol, limit=1
            )
            if not funding:
                return True, "OK"
            
            rate = float(funding[-1]['fundingRate']) * 100
            
            # Long mà funding dương cao → phải trả phí
            # Short mà funding âm lớn → phải trả phí
            if side == 'LONG' and rate > max_funding:
                logger.warning(
                    f"⚠️ {symbol} funding +{rate:.3f}% "
                    f"too high for LONG"
                )
                return False, (
                    f"Funding rate {rate:.3f}% too high"
                )
            elif side == 'SHORT' and rate < -max_funding:
                logger.warning(
                    f"⚠️ {symbol} funding {rate:.3f}% "
                    f"too negative for SHORT"
                )
                return False, (
                    f"Funding rate {rate:.3f}% too negative"
                )
            
            logger.info(
                f"   💰 {symbol} funding: {rate:.4f}% ✅"
            )
            return True, "OK"
        except Exception as e:
            logger.warning(f"Funding rate check error: {e}")
            return True, "OK"
    
    async def check_volatility_spike(self, symbol):
        """
        ⚡ Volatility spike detection
        Skip/giảm size nếu ATR spike > N lần bình thường
        """
        try:
            spike_mult = self.risk_settings.get(
                'volatility_spike_mult', 3.0
            )
            klines = self.client.get_klines(symbol, "15m", 100)
            if not klines:
                return True, "OK"
            
            df = self.analyzer.prepare_dataframe(klines)
            df = self.analyzer.add_basic_indicators(df)
            
            if 'atr' not in df.columns:
                return True, "OK"
            
            current_atr = float(df['atr'].iloc[-1])
            avg_atr = float(df['atr'].iloc[-50:].mean())
            
            # Store for position sizing adjustment
            self.atr_history[symbol] = {
                'current': current_atr,
                'average': avg_atr,
                'ratio': (
                    current_atr / avg_atr if avg_atr > 0
                    else 1.0
                )
            }
            
            if avg_atr > 0 and current_atr > avg_atr * spike_mult:
                ratio = current_atr / avg_atr
                logger.warning(
                    f"⚡ {symbol} ATR spike: "
                    f"{ratio:.1f}x normal → SKIP"
                )
                return False, (
                    f"Volatility spike {ratio:.1f}x"
                )
            
            return True, "OK"
        except Exception as e:
            logger.warning(f"Volatility check error: {e}")
            return True, "OK"
    
    async def execute_trade(
        self, signal_data, bypass_soft_filters=False
    ):
        """
        🚀 Execute trade v2.0
        - Leverage 20x (BTC/ETH/SOL)
        - Dynamic position size: tự scale đạt min_profit_target
        - Position size có điều chỉnh theo volatility
        - Partial TP (50% / 30% / 20%)
        - Breakeven tracking
        """
        try:
            symbol = signal_data['symbol']
            signal = signal_data['signal']
            entry_price = signal_data.get('entry_price', 0)
            stop_loss = signal_data.get('stop_loss', 0)
            take_profit = signal_data.get('take_profit', 0)

            # GET CURRENT PRICE if entry_price is 0 or invalid
            if not entry_price or entry_price <= 0:
                try:
                    ticker = self.client.client.futures_symbol_ticker(symbol=symbol)
                    entry_price = float(ticker['price'])
                    logger.info(f"   📊 Got current price for {symbol}: ${entry_price}")
                except Exception as e:
                    logger.error(f"Failed to get price for {symbol}: {e}")
                    return False, "Cannot get current price"

            # Validate entry_price to prevent division by zero
            if entry_price <= 0:
                return False, "Invalid entry price (0 or negative)"

            # Calculate SL/TP if not provided
            sl_pct = self.risk_settings.get('sl_percentage', 1.5) / 100
            tp_pct = self.risk_settings.get('tp_percentage', 3.0) / 100
            if not stop_loss or stop_loss <= 0:
                if signal == 'LONG':
                    stop_loss = entry_price * (1 - sl_pct)
                else:
                    stop_loss = entry_price * (1 + sl_pct)
            if not take_profit or take_profit <= 0:
                if signal == 'LONG':
                    take_profit = entry_price * (1 + tp_pct)
                else:
                    take_profit = entry_price * (1 - tp_pct)
            
            # Check risk (v2 - includes all filters)
            can_trade, reason = await self.check_risk_before_trade(
                symbol,
                signal,
                bypass_soft_filters=bypass_soft_filters,
            )
            if not can_trade:
                logger.warning(
                    f"⚠️ Cannot trade {symbol}: {reason}"
                )
                return False, reason
            
            # Get leverage for this symbol
            sym_lev = self.risk_settings.get(
                'symbol_leverage', {}
            )
            leverage = sym_lev.get(symbol, 35)  # Default 35x if not specified
            
            # Set leverage
            try:
                self.client.client.futures_change_leverage(
                    symbol=symbol, leverage=leverage
                )
                logger.info(
                    f"   📊 Set leverage {symbol}: "
                    f"{leverage}x"
                )
            except Exception as e:
                logger.warning(
                    f"   ⚠️ Could not set leverage: {e}"
                )
            
            # Calculate position size
            account = self.client.client.futures_account()
            balance = float(account['totalWalletBalance'])
            
            # Update peak balance for drawdown tracking
            if balance > self.peak_balance:
                self.peak_balance = balance
            
            # Base position = balance * position_size%
            pos_size_pct = self.risk_settings[
                'max_position_size'
            ] / 100
            position_value = balance * pos_size_pct

            # === MIN PROFIT TARGET: tự scale position size ===
            # Nếu base position quá nhỏ (tài khoản nhỏ), tăng lên
            # sao cho 1 lệnh thắng >= min_profit_target_usd
            min_profit_usd = float(
                self.risk_settings.get(
                    'min_profit_target_usd', 4.0
                )
            )
            tp_rate = self.risk_settings.get(
                'tp_percentage', 3.0
            ) / 100  # e.g. 0.03
            if (
                min_profit_usd > 0
                and tp_rate > 0
                and leverage > 0
            ):
                required = min_profit_usd / (
                    leverage * tp_rate
                )
                if required > position_value:
                    logger.info(
                        f"   🎯 Scale position "
                        f"${position_value:.2f}"
                        f"→${required:.2f} "
                        f"(target ≥$"
                        f"{min_profit_usd:.1f}/trade)"
                    )
                    position_value = required

            # Safety cap: không vượt 80% balance
            max_pos = balance * 0.80
            if position_value > max_pos:
                logger.warning(
                    f"   ⚠️ Position capped 80%: "
                    f"${position_value:.2f}→${max_pos:.2f}"
                )
                position_value = max_pos

            # Adjust for volatility spike
            atr_data = self.atr_history.get(symbol, {})
            atr_ratio = atr_data.get('ratio', 1.0)
            if atr_ratio > 1.5:
                # Reduce size proportionally to spike
                adj = max(0.5, 1.0 / atr_ratio)
                position_value *= adj
                logger.info(
                    f"   ⚡ Volatility adj: "
                    f"size x{adj:.2f} (ATR {atr_ratio:.1f}x)"
                )
            
            # Adjust for drawdown warning
            if self.peak_balance > 0:
                dd_pct = (
                    (self.peak_balance - balance)
                    / self.peak_balance * 100
                )
                max_dd = self.risk_settings.get(
                    'max_drawdown_pct', 10
                )
                if dd_pct >= max_dd * 0.8:
                    position_value *= 0.5
                    logger.info(
                        "   ⚠️ Drawdown warning: "
                        "position size halved"
                    )
            
            # Quantity with leverage
            quantity = (
                position_value * leverage
            ) / entry_price
            
            # Get symbol precision (cached 1h)
            if (
                self._exchange_info_cache is None
                or time.time() - self._exchange_info_ts > 3600
            ):
                self._exchange_info_cache = (
                    self.client.client
                    .futures_exchange_info()
                )
                self._exchange_info_ts = time.time()
            symbol_info = next(
                (
                    s for s in
                    self._exchange_info_cache['symbols']
                    if s['symbol'] == symbol
                ),
                None
            )
            
            qty_precision = 3
            price_precision = 2
            if symbol_info:
                for f in symbol_info['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step = float(f['stepSize'])
                        qty_precision = len(
                            str(step).rstrip('0')
                            .split('.')[-1]
                        )
                        quantity = round(
                            quantity, qty_precision
                        )
                    if f['filterType'] == 'PRICE_FILTER':
                        tick = float(f['tickSize'])
                        price_precision = len(
                            str(tick).rstrip('0')
                            .split('.')[-1]
                        )
            
            # Round SL/TP to price precision
            if stop_loss:
                stop_loss = round(stop_loss, price_precision)
            if take_profit:
                take_profit = round(take_profit, price_precision)
            
            # Place market order
            side_order = (
                'BUY' if signal == 'LONG' else 'SELL'
            )
            position_side = (
                'LONG' if signal == 'LONG' else 'SHORT'
            )

            # Check position mode (hedge vs one-way)
            try:
                position_mode = self.client.client.futures_get_position_mode()
                is_hedge_mode = position_mode.get('dualSidePosition', False)
            except:
                is_hedge_mode = False  # Default to one-way

            # Create order based on position mode
            if is_hedge_mode:
                order = self.client.client.futures_create_order(
                    symbol=symbol,
                    side=side_order,
                    type='MARKET',
                    quantity=quantity,
                    positionSide=position_side
                )
            else:
                # One-way mode: no positionSide
                order = self.client.client.futures_create_order(
                    symbol=symbol,
                    side=side_order,
                    type='MARKET',
                    quantity=quantity
                )
            
            logger.info(
                f"✅ Opened {signal} {symbol} "
                f"x{quantity} @ ${entry_price:.2f} "
                f"(Leverage: {leverage}x)"
            )
            logger.info(
                f"   SL: ${stop_loss:.2f} | "
                f"TP: ${take_profit:.2f}"
            )
            
            # === PARTIAL TP SETUP ===
            partial_tp = self.risk_settings.get(
                'partial_tp_enabled', True
            )
            tp_levels = self.risk_settings.get(
                'partial_tp_levels', [0.5, 0.3, 0.2]
            )
            
            if partial_tp and stop_loss and take_profit:
                # Calculate 3 TP levels.
                # risk_dist = full TP distance (e.g. 3%)
                # TP1 @ 1.5x risk_dist → 1:1.5 R:R (không
                #   còn 1:1 như trước)
                # TP2 @ 2x risk_dist   → 1:2 R:R (full TP)
                # TP3 @ 3x risk_dist   → 1:3 R:R (extended)
                risk_dist = abs(take_profit - entry_price)
                if signal == 'LONG':
                    tp1 = entry_price + risk_dist * 1.0
                    tp2 = entry_price + risk_dist * 2.0
                    tp3 = entry_price + risk_dist * 3.0
                else:
                    tp1 = entry_price - risk_dist * 1.0
                    tp2 = entry_price - risk_dist * 2.0
                    tp3 = entry_price - risk_dist * 3.0
                
                tp_prices = [
                    round(tp1, price_precision),
                    round(tp2, price_precision),
                    round(tp3, price_precision),
                ]
                tp_qtys = [
                    round(quantity * tp_levels[0], qty_precision),
                    round(quantity * tp_levels[1], qty_precision),
                    0,  # placeholder
                ]
                # Last TP = remainder so sum == total (no dust)
                tp_qtys[2] = round(
                    quantity - tp_qtys[0] - tp_qtys[1],
                    qty_precision
                )
                
                # Place partial TP orders
                for i, (tp_price, tp_qty) in enumerate(
                    zip(tp_prices, tp_qtys)
                ):
                    if tp_qty > 0:
                        await self.place_take_profit(
                            symbol, tp_qty, tp_price, signal
                        )
                        logger.info(
                            f"   🎯 TP{i+1}: "
                            f"${tp_price:.2f} "
                            f"qty={tp_qty}"
                        )
            else:
                # Single TP fallback
                if self.risk_settings['force_tp'] and take_profit:
                    await self.place_take_profit(
                        symbol, quantity, take_profit, signal
                    )
            
            # Place SL
            if self.risk_settings['force_sl'] and stop_loss:
                await self.place_stop_loss(
                    symbol, quantity, stop_loss, signal
                )
            
            # Update tracking
            self.today_trades += 1
            
            # Track position for monitor
            self.positions[symbol] = {
                'entry_price': entry_price,
                'signal': signal,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'quantity': quantity,
                'entry_time': datetime.now(),
                'breakeven_moved': False,
                'trailing_activated': False,
                'highest_price': entry_price,
                'lowest_price': entry_price,
                'partial_tp_hit': [False, False, False],
            }
            
            return True, order
            
        except Exception as e:
            logger.error(f"❌ Error executing trade: {e}")
            return False, str(e)
    
    async def close_position_and_learn(
        self, symbol, exit_price, reason="SL/TP hit"
    ):
        """
        🎓 CLOSE position và GHI NHẬN kết quả để học
        Gọi hàm này khi đóng position (SL/TP hit hoặc manual close)
        Lưu trade history vào file để theo dõi
        """
        try:
            if symbol in self.positions:
                pos = self.positions[symbol]
                entry_price = pos['entry_price']
                signal = pos['signal']
                qty = pos.get('quantity', 0)

                # Calculate profit %
                if signal == 'LONG':
                    profit_pct = (
                        (exit_price - entry_price)
                        / entry_price * 100
                    )
                    usd_pnl = (
                        (exit_price - entry_price) * qty
                    )
                else:  # SHORT
                    profit_pct = (
                        (entry_price - exit_price)
                        / entry_price * 100
                    )
                    usd_pnl = (
                        (entry_price - exit_price) * qty
                    )

                # Record for continuous learning
                self.learning_engine.record_trade_result(
                    symbol=symbol,
                    signal=signal,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    profit_pct=profit_pct
                )

                # Update stats
                if profit_pct > 0:
                    self.today_wins += 1
                self.today_pnl += profit_pct

                # === PERSIST TRADE TO FILE ===
                self._save_trade_record({
                    'symbol': symbol,
                    'signal': signal,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'quantity': round(qty, 6),
                    'pnl_pct': round(profit_pct, 3),
                    'usd_pnl': round(usd_pnl, 2),
                    'stop_loss': pos.get('stop_loss'),
                    'take_profit': pos.get('take_profit'),
                    'close_reason': reason,
                    'breakeven_hit': pos.get(
                        'breakeven_moved', False
                    ),
                    'trailing_hit': pos.get(
                        'trailing_activated', False
                    ),
                    'entry_time': str(
                        pos.get('entry_time', '')
                    ),
                    'exit_time': datetime.now().strftime(
                        '%Y-%m-%d %H:%M:%S'
                    ),
                })
                
                # Remove from tracking
                del self.positions[symbol]
                
                logger.info(
                    f"📊 Position closed: {symbol} "
                    f"{signal} → {profit_pct:+.2f}%"
                )
                
                # Save session state
                self._save_session_state()
                
                # Check if need immediate retrain
                should_retrain, reasons = (
                    await self.learning_engine.should_retrain(
                        symbol
                    )
                )
                if should_retrain and 'Low accuracy' in str(
                    reasons
                ):
                    logger.warning(
                        f"⚠️ {symbol} performance dropped"
                    )
                    asyncio.create_task(
                        self.learning_engine
                        .train_model_realtime(symbol)
                    )
                
        except Exception as e:
            logger.error(
                f"❌ Error closing position: {e}"
            )
    
    def _save_trade_record(self, trade):
        """Persist trade record to JSON file (closed_trades.json)
        Uses a separate file from trade_history.json (learning engine)
        to avoid format conflicts.
        """
        try:
            import json as json_mod
            import os
            # Use separate file so continuous_learning_engine
            # doesn't overwrite our new-format records
            path = 'models/closed_trades.json'
            os.makedirs('models', exist_ok=True)

            data = {'trades': []}
            if os.path.exists(path):
                with open(path, 'r') as f:
                    existing = json_mod.load(f)
                if isinstance(existing, dict):
                    data = existing
                    if 'trades' not in data:
                        data['trades'] = []
                elif isinstance(existing, list):
                    data = {'trades': existing}

            data['trades'].append(trade)
            data['updated'] = datetime.now().strftime(
                '%Y-%m-%d %H:%M:%S'
            )

            with open(path, 'w') as f:
                json_mod.dump(data, f, indent=2)

            logger.debug(f"💾 Trade saved: {trade['symbol']}")
        except Exception as e:
            logger.warning(f"Save trade error: {e}")
    
    def _save_session_state(self):
        """Save session state for recovery after restart"""
        try:
            import json as json_mod
            import os
            path = 'models/session_state.json'
            os.makedirs('models', exist_ok=True)
            
            state = {
                'today_pnl': self.today_pnl,
                'today_trades': self.today_trades,
                'today_wins': self.today_wins,
                'peak_balance': self.peak_balance,
                'session_start': self.session_start
                .strftime('%Y-%m-%d %H:%M:%S'),
                'positions': {},
                'saved_at': datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S'
                ),
            }
            
            # Save tracked positions
            for sym, pos in self.positions.items():
                state['positions'][sym] = {
                    'entry_price': pos['entry_price'],
                    'signal': pos['signal'],
                    'stop_loss': pos['stop_loss'],
                    'take_profit': pos['take_profit'],
                    'quantity': pos['quantity'],
                    'breakeven_moved': pos.get(
                        'breakeven_moved', False
                    ),
                    'trailing_activated': pos.get(
                        'trailing_activated', False
                    ),
                    'entry_time': str(
                        pos.get('entry_time', '')
                    ),
                }
            
            with open(path, 'w') as f:
                json_mod.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Save state error: {e}")
    
    def _load_session_state(self):
        """Load session state from file (call in __init__)"""
        try:
            import json as json_mod
            import os
            path = 'models/session_state.json'
            if not os.path.exists(path):
                return
            
            with open(path, 'r') as f:
                state = json_mod.load(f)
            
            # Only restore if same day
            saved = state.get('saved_at', '')
            today = datetime.now().strftime('%Y-%m-%d')
            if saved.startswith(today):
                self.today_pnl = state.get(
                    'today_pnl', 0
                )
                self.today_trades = state.get(
                    'today_trades', 0
                )
                self.today_wins = state.get(
                    'today_wins', 0
                )
                # Restore peak_balance but validate it won't cause
                # an immediate drawdown stop on the next balance check.
                # If the saved peak is significantly above current
                # balance we reset it so the bot can start fresh.
                saved_peak = state.get('peak_balance', 0)
                # We don't know current balance yet at __init__ time,
                # so just store it — the main loop will overwrite with
                # `max(peak, current)` on the first iteration anyway.
                # To be safe: cap the restored peak to avoid triggering
                # an instant drawdown stop, defer capping to start_bot.
                self.peak_balance = saved_peak
                self._restored_peak = saved_peak  # remember for startup check

                # Restore open positions so monitor can detect SL/TP
                # hits and record them even after a bot restart
                saved_positions = state.get('positions', {})
                if saved_positions:
                    for sym, pos in saved_positions.items():
                        # Convert entry_time string back to datetime
                        et = pos.get('entry_time')
                        if et and isinstance(et, str):
                            for fmt in [
                                '%Y-%m-%d %H:%M:%S.%f',
                                '%Y-%m-%d %H:%M:%S',
                            ]:
                                try:
                                    pos['entry_time'] = (
                                        datetime.strptime(et, fmt)
                                    )
                                    break
                                except ValueError:
                                    pass
                        self.positions[sym] = pos
                    logger.info(
                        f"📂 Restored {len(saved_positions)} "
                        f"open position(s): "
                        f"{list(saved_positions.keys())}"
                    )

                logger.info(
                    f"📂 Session restored: "
                    f"{self.today_trades} trades, "
                    f"PnL={self.today_pnl:+.2f}%"
                )
            else:
                logger.info("📂 New day - fresh session")
        except Exception as e:
            logger.warning(f"Load state error: {e}")
    
    def _get_price_precision(self, symbol):
        """Get tick_size and price precision for a symbol"""
        if symbol in self._tick_size_cache:
            return self._tick_size_cache[symbol]
        try:
            if (
                self._exchange_info_cache is None
                or time.time() - self._exchange_info_ts
                > 3600
            ):
                self._exchange_info_cache = (
                    self.client.client
                    .futures_exchange_info()
                )
                self._exchange_info_ts = time.time()
            for s in self._exchange_info_cache['symbols']:
                if s['symbol'] == symbol:
                    for f in s['filters']:
                        if f['filterType'] == 'PRICE_FILTER':
                            tick = float(f['tickSize'])
                            prec = len(
                                str(tick).rstrip('0')
                                .split('.')[-1]
                            )
                            self._tick_size_cache[symbol] = (
                                tick, prec
                            )
                            return tick, prec
        except Exception as e:
            logger.warning(f"Price precision error: {e}")
        # Fallback
        self._tick_size_cache[symbol] = (0.01, 2)
        return 0.01, 2

    def _round_price(self, symbol, price):
        """Round price to exchange tick_size"""
        import math
        tick, prec = self._get_price_precision(symbol)
        # Round DOWN to nearest tick
        rounded = math.floor(price / tick) * tick
        return round(rounded, prec)

    async def place_stop_loss(
        self, symbol, quantity, stop_price, side
    ):
        """Place stop loss order with correct precision"""
        try:
            sl_side = (
                'SELL' if side == 'LONG' else 'BUY'
            )
            position_side = (
                'LONG' if side == 'LONG' else 'SHORT'
            )
            rounded_price = self._round_price(
                symbol, stop_price
            )

            # Check position mode (hedge vs one-way)
            try:
                position_mode = self.client.client.futures_get_position_mode()
                is_hedge_mode = position_mode.get('dualSidePosition', False)
            except:
                is_hedge_mode = False

            # Use closePosition=True instead of specific quantity
            sl_params = {
                'symbol': symbol,
                'side': sl_side,
                'type': 'STOP_MARKET',
                'stopPrice': rounded_price,
                'closePosition': 'true'
            }
            if is_hedge_mode:
                sl_params['positionSide'] = position_side

            order = self.client.client.futures_create_order(**sl_params)

            logger.info(
                f"🛡️ SL placed @ ${rounded_price:.2f}"
            )
            return order

        except Exception as e:
            logger.error(f"Error placing SL: {e}")
            return None

    async def place_take_profit(
        self, symbol, quantity, tp_price, side
    ):
        """Place take profit order with correct precision"""
        try:
            tp_side = (
                'SELL' if side == 'LONG' else 'BUY'
            )
            position_side = (
                'LONG' if side == 'LONG' else 'SHORT'
            )
            rounded_price = self._round_price(
                symbol, tp_price
            )

            # Check position mode (hedge vs one-way)
            try:
                position_mode = self.client.client.futures_get_position_mode()
                is_hedge_mode = position_mode.get('dualSidePosition', False)
            except:
                is_hedge_mode = False

            tp_params = {
                'symbol': symbol,
                'side': tp_side,
                'type': 'TAKE_PROFIT_MARKET',
                'stopPrice': rounded_price,
                'quantity': quantity
            }
            if is_hedge_mode:
                tp_params['positionSide'] = position_side

            order = self.client.client.futures_create_order(**tp_params)

            logger.info(
                f"🎯 TP placed @ ${rounded_price:.2f}"
            )
            return order

        except Exception as e:
            logger.error(f"Error placing TP: {e}")
            return None
    
    async def position_monitor_loop(self):
        """
        🔍 POSITION MONITOR - Chạy mỗi 30 giây
        - Trailing stop: di chuyển SL theo giá
        - Breakeven: move SL về entry khi lãi đủ
        - Detect closed positions (SL/TP hit)
        """
        logger.info("🔍 Position Monitor started (30s)")
        
        while self.is_running:
            try:
                if self.is_paused or not self.positions:
                    await asyncio.sleep(10)
                    continue
                
                # Get live positions from exchange
                live_positions = (
                    await self.get_current_positions()
                )
                live_symbols = {
                    p['symbol'] for p in live_positions
                }
                # Build size lookup for qty sync
                live_qty_map = {
                    p['symbol']: p['size']
                    for p in live_positions
                }
                
                # Check tracked positions
                closed_symbols = []
                for symbol, pos in self.positions.items():
                    entry = pos['entry_price']
                    signal = pos['signal']
                    
                    # Sync tracked qty with exchange
                    # (partial TP may have reduced size)
                    if symbol in live_qty_map:
                        actual = live_qty_map[symbol]
                        if actual != pos['quantity']:
                            logger.info(
                                f"📦 {symbol} qty sync: "
                                f"{pos['quantity']}"
                                f"→{actual} (partial TP)"
                            )
                            pos['quantity'] = actual
                    
                    # Get current price
                    try:
                        ticker = (
                            self.client.client
                            .futures_symbol_ticker(
                                symbol=symbol
                            )
                        )
                        current = float(ticker['price'])
                    except Exception:
                        continue
                    
                    # Update high/low tracking
                    if current > pos.get(
                        'highest_price', entry
                    ):
                        pos['highest_price'] = current
                    if current < pos.get(
                        'lowest_price', entry
                    ):
                        pos['lowest_price'] = current
                    
                    # Calculate profit %
                    if signal == 'LONG':
                        profit_pct = (
                            (current - entry) / entry * 100
                        )
                    else:
                        profit_pct = (
                            (entry - current) / entry * 100
                        )
                    
                    # === BREAKEVEN ===
                    be_trigger = self.risk_settings.get(
                        'breakeven_trigger_pct', 1.0
                    )
                    if (
                        not pos.get('breakeven_moved')
                        and profit_pct >= be_trigger
                    ):
                        # Move SL to entry + small buffer
                        if signal == 'LONG':
                            new_sl = entry * 1.001
                        else:
                            new_sl = entry * 0.999
                        
                        try:
                            # Cancel old SL, place new
                            ok = await self._update_stop_loss(
                                symbol,
                                pos['quantity'],
                                new_sl,
                                signal
                            )
                            if ok:
                                pos['stop_loss'] = new_sl
                                pos['breakeven_moved'] = True
                                logger.info(
                                    f"🔒 {symbol} breakeven: "
                                    f"SL→${new_sl:.2f} "
                                    f"(profit "
                                    f"{profit_pct:.1f}%)"
                                )
                            else:
                                logger.warning(
                                    f"⚠️ {symbol} BE SL "
                                    f"place failed, "
                                    f"keeping old SL"
                                )
                        except Exception as e:
                            logger.warning(
                                f"BE update failed: {e}"
                            )
                    
                    # === TRAILING STOP ===
                    # Use elif: skip trailing in the same
                    # iteration where breakeven just activated
                    # (avoids double closePosition on Binance)
                    elif pos.get('breakeven_moved'):
                        trail_pct = self.risk_settings.get(
                            'trailing_stop_pct', 0.8
                        )
                        old_sl = pos.get('stop_loss', 0)
                        
                        if signal == 'LONG':
                            new_trail = current * (
                                1 - trail_pct / 100
                            )
                            if new_trail > old_sl:
                                try:
                                    ok = await self._update_stop_loss(
                                        symbol,
                                        pos['quantity'],
                                        new_trail,
                                        signal
                                    )
                                    if ok:
                                        pos['stop_loss'] = new_trail
                                        pos['trailing_activated'] = True
                                        logger.info(
                                            f"📈 {symbol} "
                                            f"trailing SL→"
                                            f"${new_trail:.2f}"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Trail err: {e}"
                                    )
                        else:  # SHORT
                            new_trail = current * (
                                1 + trail_pct / 100
                            )
                            if (
                                new_trail < old_sl
                                or old_sl == 0
                            ):
                                try:
                                    ok = await self._update_stop_loss(
                                        symbol,
                                        pos['quantity'],
                                        new_trail,
                                        signal
                                    )
                                    if ok:
                                        pos['stop_loss'] = new_trail
                                        pos['trailing_activated'] = True
                                        logger.info(
                                            f"📉 {symbol} "
                                            f"trailing SL→"
                                            f"${new_trail:.2f}"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"Trail err: {e}"
                                    )
                    
                    # === MAX LOSS PER POSITION ===
                    max_loss_pct = self.risk_settings.get(
                        'max_loss_per_position', 5.0
                    )
                    if profit_pct <= -max_loss_pct:
                        _reason = (
                            f"Max loss -{max_loss_pct}%"
                        )
                        logger.warning(
                            f"🚨 {symbol} loss "
                            f"{profit_pct:.1f}% >= "
                            f"-{max_loss_pct}% → "
                            f"FORCE CLOSE"
                        )
                        await self._force_close_position(
                            symbol, pos, current,
                            _reason
                        )
                        closed_symbols.append(
                            (symbol, current, _reason)
                        )
                        continue
                    
                    # === MAX HOLD TIME ===
                    max_hours = self.risk_settings.get(
                        'max_hold_hours', 24
                    )
                    entry_time = pos.get('entry_time')
                    if entry_time:
                        if isinstance(entry_time, str):
                            try:
                                entry_time = (
                                    datetime.strptime(
                                        entry_time,
                                        '%Y-%m-%d %H:%M:%S'
                                    )
                                )
                            except Exception:
                                entry_time = None
                        if entry_time:
                            held_hours = (
                                datetime.now() - entry_time
                            ).total_seconds() / 3600
                            if held_hours >= max_hours:
                                _reason = (
                                    f"Max hold "
                                    f"{max_hours}h"
                                )
                                logger.warning(
                                    f"⏰ {symbol} held "
                                    f"{held_hours:.1f}h "
                                    f">= {max_hours}h → "
                                    f"CLOSE"
                                )
                                await (
                                    self
                                    ._force_close_position(
                                        symbol, pos,
                                        current,
                                        _reason
                                    )
                                )
                                closed_symbols.append(
                                    (symbol, current,
                                     _reason)
                                )
                                continue
                    
                    # Detect closed position
                    if symbol not in live_symbols:
                        # Cancel any remaining TP/SL orders
                        # (orphaned orders cause ghost fills
                        # on the next position open)
                        try:
                            open_orders = (
                                self.client.client
                                .futures_get_open_orders(
                                    symbol=symbol
                                )
                            )
                            for o in open_orders:
                                try:
                                    cli = self.client.client
                                    cli.futures_cancel_order(
                                        symbol=symbol,
                                        orderId=o['orderId']
                                    )
                                except Exception:
                                    pass
                            if open_orders:
                                logger.info(
                                    f"🧹 {symbol}: cancelled "
                                    f"{len(open_orders)} "
                                    f"orphaned order(s)"
                                )
                        except Exception as _oe:
                            logger.debug(
                                f"Cancel orphan err: {_oe}"
                            )
                        closed_symbols.append(
                            (symbol, current,
                             'SL/TP hit')
                        )

                # Process closed positions
                for symbol, price, reason in (
                    closed_symbols
                ):
                    await self.close_position_and_learn(
                        symbol, price, reason
                    )
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(
                    f"❌ Position monitor error: {e}"
                )
                await asyncio.sleep(30)
        
        logger.info("🔍 Position Monitor stopped")
    
    async def _force_close_position(
        self, symbol, pos, current_price, reason
    ):
        """Force close a position on the exchange"""
        try:
            signal = pos['signal']
            close_side = (
                'SELL' if signal == 'LONG' else 'BUY'
            )
            position_side = signal  # LONG or SHORT

            # Get ACTUAL position size from exchange
            # (may differ from tracked qty if partial TP filled)
            quantity = pos['quantity']  # fallback
            try:
                ex_positions = (
                    self.client.client
                    .futures_position_information(
                        symbol=symbol
                    )
                )
                for ep in ex_positions:
                    amt = float(ep['positionAmt'])
                    if amt != 0:
                        quantity = abs(amt)
                        break
            except Exception:
                pass

            if quantity <= 0:
                logger.warning(
                    f"⚠️ {symbol} already closed "
                    f"on exchange"
                )
                return

            # Cancel all open orders for this symbol
            try:
                orders = (
                    self.client.client
                    .futures_get_open_orders(
                        symbol=symbol
                    )
                )
                for o in orders:
                    self.client.client.futures_cancel_order(
                        symbol=symbol,
                        orderId=o['orderId']
                    )
            except Exception:
                pass

            # Market close with actual exchange quantity
            self.client.client.futures_create_order(
                symbol=symbol,
                side=close_side,
                type='MARKET',
                quantity=quantity,
                positionSide=position_side
            )
            logger.info(
                f"🚨 Force closed {signal} {symbol} "
                f"@ ${current_price:.2f} "
                f"qty={quantity} "
                f"| Reason: {reason}"
            )
        except Exception as e:
            logger.error(
                f"❌ Force close {symbol} failed: {e}"
            )

    async def _sync_positions_from_exchange(self):
        """
        Sync tracked positions with exchange on startup.
        Prevents orphan positions after bot restart.
        Also places SL/TP for positions that don't have them.
        """
        try:
            live = await self.get_current_positions()
            if not live:
                return
            for p in live:
                sym = p['symbol']
                entry = p['entry_price']
                signal = p['side']
                qty = p['size']

                if sym not in self.positions:
                    # Calculate SL/TP from risk settings
                    sl_pct = self.risk_settings.get(
                        'sl_percentage', 1.5
                    )
                    tp_pct = self.risk_settings.get(
                        'tp_percentage', 3.0
                    )
                    if signal == 'LONG':
                        sl = round(
                            entry * (1 - sl_pct / 100), 2
                        )
                        tp = round(
                            entry * (1 + tp_pct / 100), 2
                        )
                    else:
                        sl = round(
                            entry * (1 + sl_pct / 100), 2
                        )
                        tp = round(
                            entry * (1 - tp_pct / 100), 2
                        )

                    self.positions[sym] = {
                        'entry_price': entry,
                        'signal': signal,
                        'stop_loss': sl,
                        'take_profit': tp,
                        'quantity': qty,
                        'entry_time': datetime.now(),
                        'breakeven_moved': False,
                        'trailing_activated': False,
                        'highest_price': entry,
                        'lowest_price': entry,
                        'partial_tp_hit': [
                            False, False, False
                        ],
                    }
                    logger.info(
                        f"📂 Synced {signal} "
                        f"{sym} from exchange "
                        f"(size={qty})"
                    )

                    # Cancel any stale orders, then place SL/TP
                    try:
                        existing = (
                            self.client.client
                            .futures_get_open_orders(
                                symbol=sym
                            )
                        )
                        for o in existing:
                            if o['type'] in (
                                'STOP_MARKET',
                                'TAKE_PROFIT_MARKET'
                            ):
                                self.client.client\
                                    .futures_cancel_order(
                                        symbol=sym,
                                        orderId=o[
                                            'orderId'
                                        ]
                                    )
                    except Exception:
                        pass

                    # Place SL
                    if self.risk_settings.get(
                        'force_sl', True
                    ):
                        await self.place_stop_loss(
                            sym, qty, sl, signal
                        )
                        logger.info(
                            f"   🛡️ Auto-SL for synced "
                            f"{sym}: ${sl:.2f}"
                        )

                    # Place TP (single order for synced)
                    if self.risk_settings.get(
                        'force_tp', True
                    ):
                        await self.place_take_profit(
                            sym, qty, tp, signal
                        )
                        logger.info(
                            f"   🎯 Auto-TP for synced "
                            f"{sym}: ${tp:.2f}"
                        )

        except Exception as e:
            logger.warning(
                f"Position sync error: {e}"
            )

    async def _update_stop_loss(
        self, symbol, quantity, new_sl, side
    ):
        """Cancel old SL and place new one.
        Returns True if new SL was placed successfully.
        """
        try:
            # Cancel all open SL orders for this symbol
            orders = (
                self.client.client.futures_get_open_orders(
                    symbol=symbol
                )
            )
            cancelled = 0
            for o in orders:
                if o['type'] == 'STOP_MARKET':
                    self.client.client.futures_cancel_order(
                        symbol=symbol,
                        orderId=o['orderId']
                    )
                    cancelled += 1
            
            # Wait for Binance to process cancellations
            # Required when using closePosition=True
            # (only 1 allowed per direction)
            if cancelled > 0:
                await asyncio.sleep(1.0)
            
            # Place new SL
            result = await self.place_stop_loss(
                symbol, quantity, new_sl, side
            )
            return result is not None
        except Exception as e:
            logger.warning(f"Update SL error: {e}")
            return False
    
    async def main_loop(self):
        """
        🔄 MAIN BOT LOOP v2.0
        - Continuous Learning trong background
        - Position Monitor trong background (30 giây)
        - Signal scan mỗi 5 phút
        """
        logger.info(
            "🚀 Bot v2.0 started in {} mode".format(
                self.mode.upper()
            )
        )
        
        # Start continuous learning background task
        logger.info("🧠 Starting Continuous Learning...")
        self.learning_task = asyncio.create_task(
            self.learning_engine.continuous_learning_loop(
                check_interval_hours=2
            )
        )
        
        # Start position monitor background task
        logger.info("🔍 Starting Position Monitor...")
        self.position_monitor_task = asyncio.create_task(
            self.position_monitor_loop()
        )
        
        # Sync existing positions from exchange
        await self._sync_positions_from_exchange()
        
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        startup_priority_entry_done = False
        
        while self.is_running:
            try:
                if self.is_paused:
                    await asyncio.sleep(5)
                    continue
                
                # Check daily loss limit
                account = (
                    self.client.client.futures_account()
                )
                balance = float(
                    account['totalWalletBalance']
                )
                
                # Update peak balance
                if balance > self.peak_balance:
                    self.peak_balance = balance
                
                # Guard: if a stale peak_balance was restored from a
                # previous session and would immediately trigger the
                # drawdown stop, reset it to current balance so the
                # bot can start fresh instead of stopping right away.
                if self.peak_balance > 0:
                    _dd_now = (self.peak_balance - balance) / self.peak_balance * 100
                    _max_dd = self.risk_settings.get('max_drawdown_pct', 10)
                    if _dd_now >= _max_dd:
                        logger.warning(
                            f"⚠️ Stale peak_balance {self.peak_balance:.2f} "
                            f"would trigger {_dd_now:.1f}% drawdown immediately. "
                            f"Resetting peak to current balance {balance:.2f}"
                        )
                        self.peak_balance = balance

                # Daily loss limit check
                # today_pnl is in %, daily_max_loss is also in %
                daily_max_loss_pct = self.risk_settings['daily_max_loss']
                
                if abs(self.today_pnl) >= daily_max_loss_pct:
                    logger.warning(
                        f"🚨 Daily loss limit "
                        f"{self.today_pnl:.1f}% >= "
                        f"{daily_max_loss_pct}% → Stop"
                    )
                    self.is_running = False
                    break
                
                # Drawdown check
                if self.peak_balance > 0:
                    dd = (
                        (self.peak_balance - balance)
                        / self.peak_balance * 100
                    )
                    max_dd = self.risk_settings.get(
                        'max_drawdown_pct', 10
                    )
                    if dd >= max_dd:
                        logger.warning(
                            f"🚨 Drawdown {dd:.1f}% "
                            f">= {max_dd}% → Stop"
                        )
                        self.is_running = False
                        break
                
                # Analyze each symbol
                for symbol in symbols:
                    if not self.is_running:
                        break
                    
                    logger.info(
                        f"\n📊 Analyzing {symbol}..."
                    )
                    signal_data = (
                        await self.analyze_symbol(symbol)
                    )
                    
                    if not signal_data:
                        continue
                    
                    signal = signal_data['signal']
                    confidence = signal_data['confidence']
                    
                    logger.info(
                        f"   Signal: {signal} | "
                        f"Confidence: {confidence:.1f}%"
                    )
                    logger.info(
                        f"   {signal_data['reasoning']}"
                    )
                    
                    # === SIGNAL REVERSAL CLOSE ===
                    if (
                        self.risk_settings.get(
                            'signal_reversal_close', True
                        )
                        and symbol in self.positions
                        and signal != 'HOLD'
                        and confidence >= 50
                    ):
                        pos = self.positions[symbol]
                        pos_side = pos['signal']
                        # LONG position + SHORT signal
                        # or SHORT position + LONG signal
                        if (
                            (pos_side == 'LONG'
                             and signal == 'SHORT')
                            or (pos_side == 'SHORT'
                                and signal == 'LONG')
                        ):
                            try:
                                ticker = (
                                    self.client.client
                                    .futures_symbol_ticker(
                                        symbol=symbol
                                    )
                                )
                                cur = float(
                                    ticker['price']
                                )
                            except Exception:
                                cur = signal_data.get(
                                    'entry_price', 0
                                )
                            logger.warning(
                                f"   🔄 Signal reversal: "
                                f"{pos_side}→{signal} "
                                f"({confidence:.0f}%) "
                                f"→ CLOSING {pos_side}"
                            )
                            await (
                                self._force_close_position(
                                    symbol, pos, cur,
                                    f"Signal reversal "
                                    f"{pos_side}→{signal}"
                                )
                            )
                            await (
                                self
                                .close_position_and_learn(
                                    symbol, cur,
                                    f"Signal reversal "
                                    f"{pos_side}→"
                                    f"{signal}"
                                )
                            )
                            # Continue to open new
                            # position in opposite dir
                    
                    # Skip HOLD
                    if signal == 'HOLD':
                        logger.info("   ⏭️ HOLD")
                        continue
                    
                    min_conf = self.risk_settings[
                        'min_confidence'
                    ]
                    force_entry = (
                        self.mode == 'auto'
                        and self.risk_settings.get(
                            'force_entry_on_signal', True
                        )
                    )

                    # Skip low confidence (unless force-entry)
                    if (
                        not force_entry
                        and confidence < min_conf
                    ):
                        logger.info(
                            f"   ⚠️ Low confidence "
                            f"({confidence:.1f}% < "
                            f"{min_conf}%) → Skip"
                        )
                        continue

                    # ===== STARTUP PRIORITY ENTRY =====
                    # Mục tiêu: vừa START là có thể vào lệnh ngay nếu
                    # đã có tín hiệu đủ mạnh, không chờ các soft filters.
                    # Chỉ áp dụng 1 lần sau khi bot vừa khởi động.
                    if not startup_priority_entry_done:
                        startup_min_conf = max(
                            35,
                            min_conf
                        )
                        if confidence >= startup_min_conf:
                            logger.info(
                                "   ⚡ STARTUP PRIORITY: "
                                "executing immediate entry"
                            )
                            success, result = await self.execute_trade(
                                signal_data,
                                bypass_soft_filters=True,
                            )
                            startup_priority_entry_done = True
                            if success:
                                logger.info(
                                    "   ✅ Startup entry executed"
                                )
                            else:
                                logger.warning(
                                    f"   ❌ Startup entry failed: "
                                    f"{result}"
                                )
                            await asyncio.sleep(2)
                            continue

                    # ===== QUALITY GATE V2 =====
                    # Extra filters to boost win rate
                    if not force_entry:
                        skip_reason = self._quality_gate(
                            symbol, signal_data
                        )
                        if skip_reason:
                            logger.info(
                                f"   🚫 Quality gate: "
                                f"{skip_reason}"
                            )
                            continue
                    else:
                        logger.info(
                            "   ⚡ FORCE ENTRY mode: "
                            "skip confidence/quality gates"
                        )
                    
                    # Execute based on mode
                    if self.mode == 'auto':
                        logger.info(
                            "   🤖 AUTO - Executing..."
                        )
                        success, result = (
                            await self.execute_trade(
                                signal_data,
                                bypass_soft_filters=force_entry,
                            )
                        )
                        if success:
                            logger.info(
                                "   ✅ Trade executed"
                            )
                        else:
                            logger.warning(
                                f"   ❌ Failed: {result}"
                            )
                    
                    elif self.mode == 'semi-auto':
                        logger.info(
                            "   ⚡ SEMI-AUTO → pending"
                        )
                        self.pending_signals.append(
                            signal_data
                        )
                    
                    await asyncio.sleep(2)
                
                # Wait 2 minutes before next scan (faster reaction)
                logger.info(
                    "\n⏳ Next analysis in 2 minutes..."
                )
                # Save session state periodically
                self._save_session_state()
                await asyncio.sleep(120)
                
            except Exception as e:
                logger.error(
                    f"❌ Main loop error: {e}"
                )
                await asyncio.sleep(60)
        
        logger.info("🛑 Bot stopped")
    
    async def start(self, skip_preflight=False):
        """Start bot - preflight already done by dashboard"""
        if not skip_preflight:
            passed, message = await self.pre_flight_check()
            if not passed:
                logger.error(
                    f"❌ Cannot start bot: {message}"
                )
                return False, message
        
        # Start main loop
        self.is_running = True
        self.is_paused = False
        
        await self.main_loop()
        
        return True, "Bot started"
    
    def pause(self):
        """Pause bot (stop creating new positions, keep existing)"""
        self.is_paused = True
        logger.info("⏸️ Bot paused - Keeping existing positions")
    
    def resume(self):
        """Resume bot"""
        self.is_paused = False
        logger.info("▶️ Bot resumed")
    
    def stop(self):
        """Stop bot"""
        self.is_running = False
        
        # Save session state before stopping
        self._save_session_state()
        
        # Stop continuous learning task
        if self.learning_task:
            self.learning_task.cancel()
            logger.info("🧠 Continuous learning stopped")
        
        # Stop position monitor task
        if self.position_monitor_task:
            self.position_monitor_task.cancel()
            logger.info("🔍 Position monitor stopped")
        
        logger.info("🛑 Bot stopping...")
    
    async def emergency_close_all(self):
        """Emergency close all positions"""
        logger.warning("🚨 EMERGENCY CLOSE ALL")

        # Check position mode (hedge vs one-way)
        try:
            position_mode = self.client.client.futures_get_position_mode()
            is_hedge_mode = position_mode.get('dualSidePosition', False)
        except:
            is_hedge_mode = False  # Default to one-way

        positions = await self.get_current_positions()
        closed_count = 0

        for pos in positions:
            try:
                symbol = pos['symbol']
                side = 'SELL' if pos['side'] == 'LONG' else 'BUY'
                position_side = pos['side']  # LONG or SHORT
                quantity = pos['size']

                # Close based on position mode
                if is_hedge_mode:
                    order = self.client.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type='MARKET',
                        quantity=quantity,
                        positionSide=position_side
                    )
                else:
                    # One-way mode: no positionSide
                    order = self.client.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type='MARKET',
                        quantity=quantity
                    )

                closed_count += 1
                logger.info(f"✅ Closed {pos['side']} {symbol}")

            except Exception as e:
                logger.error(f"Error closing {symbol}: {e}")

        self.stop()
        logger.info(f"🚨 Emergency close completed: {closed_count} positions closed")

        return closed_count
