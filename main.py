"""
Main Trading Bot
Bot AI trade futures Binance với độ chính xác cao
"""

import asyncio
import time
import signal
import sys
import os
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from loguru import logger
import pandas as pd

from config import Config
from binance_client import BinanceFuturesClient
from technical_analysis import TechnicalAnalyzer
from ai_engine import AITradingEngine
from risk_management import RiskManager

class BinanceFuturesBot:
    """Bot AI trading futures Binance chuyên nghiệp"""
    
    def __init__(self, config=None):
        # Dùng config được truyền vào hoặc load từ Config class
        if config is None:
            self.config = Config.get_config()
        else:
            self.config = config
        
        # Initialize components
        self.binance_client = BinanceFuturesClient()
        self.technical_analyzer = TechnicalAnalyzer()
        self.ai_engine = AITradingEngine()
        self.risk_manager = RiskManager(self.binance_client)
        
        # Trained models storage - Initialize FIRST before loading
        self.trained_models = {}
        self.trained_scalers = {}
        self.last_analysis_time = {}
        
        # Load trained AI models
        logger.info("📦 Loading trained AI models...")
        self._load_trained_models()
        logger.info("✅ AI models loaded - Ready for instant trading!")
        
        # Bot state
        self.is_running = False
        self.is_trading_enabled = True
        self.symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "SOLUSDT"]  # Default symbols
        self.timeframes = self.config["trading"]["timeframes"]
        
        # Performance tracking
        self.start_balance = 0.0
        self.peak_balance = 0.0
        self.trades_today = 0
        self.successful_trades = 0
        
        # Data storage
        self.market_data = {}

        
        logger.info("Binance Futures Bot initialized successfully")
    
    def _load_trained_models(self):
        """Load trained gradient boost models for instant trading"""
        try:
            import joblib
            
            # Symbols with trained models
            model_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            
            for symbol in model_symbols:
                model_path = f"models/gradient_boost_{symbol}.pkl"
                scaler_path = f"models/scaler_{symbol}.pkl"
                
                if os.path.exists(model_path) and os.path.exists(scaler_path):
                    self.trained_models[symbol] = joblib.load(model_path)
                    self.trained_scalers[symbol] = joblib.load(scaler_path)
                    logger.info(f"  ✅ {symbol}: Model loaded (ready for instant predictions)")
                else:
                    logger.warning(f"  ⚠️ {symbol}: No trained model found")
                    self.trained_models[symbol] = None
                    self.trained_scalers[symbol] = None
            
            loaded_count = len([m for m in self.trained_models.values() if m is not None])
            if loaded_count > 0:
                logger.info(f"🎯 {loaded_count} AI models ready for instant trading!")
            else:
                logger.warning("⚠️ No trained models available - Using technical analysis only")
                
        except Exception as e:
            logger.error(f"Error loading trained models: {e}")
            self.trained_models = {}
            self.trained_scalers = {}
    
    def _predict_with_trained_model(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Predict LONG/SHORT using trained Gradient Boost model"""
        try:
            model = self.trained_models.get(symbol)
            scaler = self.trained_scalers.get(symbol)
            
            if model is None or scaler is None:
                return {'signal': 'HOLD', 'confidence': 0.5}
            
            # Get last row (current market state)
            if len(df) == 0:
                return {'signal': 'HOLD', 'confidence': 0.5}
            
            last_row = df.iloc[-1]
            
            # Prepare 28 features (4 basic + 22 indicators + 2 price position features)
            feature_list = []
            
            # 1-4: Basic features
            feature_list.append(last_row.get('close', 0.0))
            
            # price_change_pct
            if 'open' in df.columns:
                open_price = df.iloc[-1]['open']
                close_price = last_row['close']
                price_change_pct = ((close_price - open_price) / open_price * 100) if open_price != 0 else 0
            else:
                price_change_pct = 0
            feature_list.append(price_change_pct)
            
            feature_list.append(last_row.get('volume', 0.0))
            
            # volume_change
            if 'volume' in df.columns and len(df) > 1:
                prev_volume = df.iloc[-2]['volume']
                volume_change = ((last_row['volume'] - prev_volume) / prev_volume) if prev_volume != 0 else 0
            else:
                volume_change = 0
            feature_list.append(volume_change)
            
            # 5-26: 22 technical indicators
            indicator_cols = [
                'rsi', 'macd', 'macd_signal', 'macd_diff',
                'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
                'ema_9', 'ema_21', 'ema_50', 'ema_200',
                'sma_20', 'sma_50', 'sma_200',
                'stoch_k', 'stoch_d', 'williams_r',
                'adx', 'cci', 'mfi', 'atr'
            ]
            
            for col in indicator_cols:
                feature_list.append(last_row.get(col, 0.0))
            
            # 27-28: Price position features
            # price_vs_sma20
            if 'close' in last_row.index and 'sma_20' in last_row.index and last_row['sma_20'] != 0:
                price_vs_sma20 = ((last_row['close'] - last_row['sma_20']) / last_row['sma_20'] * 100)
            else:
                price_vs_sma20 = 0
            feature_list.append(price_vs_sma20)
            
            # price_vs_ema50
            if 'close' in last_row.index and 'ema_50' in last_row.index and last_row['ema_50'] != 0:
                price_vs_ema50 = ((last_row['close'] - last_row['ema_50']) / last_row['ema_50'] * 100)
            else:
                price_vs_ema50 = 0
            feature_list.append(price_vs_ema50)
            
            # Convert to numpy array (should be 28 features)
            X = np.array(feature_list).reshape(1, -1)
            
            # Handle NaN
            X = np.nan_to_num(X, nan=0.0)
            
            # Scale features
            X_scaled = scaler.transform(X)
            
            # Predict
            prediction = model.predict(X_scaled)[0]
            
            # Get probability
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(X_scaled)[0]
                confidence = max(proba)
            else:
                confidence = 0.80  # Default high confidence for trained model
            
            # Convert to signal: 1=BUY, -1=SELL, 0=HOLD
            if prediction == 1:
                signal = 'BUY'
            elif prediction == -1:
                signal = 'SELL'
            else:
                signal = 'HOLD'
            
            return {
                'signal': signal,
                'confidence': confidence,
                'prediction': int(prediction)
            }
            
        except Exception as e:
            logger.error(f"Error predicting with trained model for {symbol}: {e}")
            return {'signal': 'HOLD', 'confidence': 0.5}
    
    async def initialize(self):
        """Khởi tạo bot và load models"""
        try:
            # Initialize async client
            await self.binance_client.initialize_async_client()
            
            # Load AI models if exist
            self.ai_engine.load_models()
            
            # Get account info
            account_info = self.binance_client.get_account_info()
            self.start_balance = float(account_info['totalWalletBalance'])
            self.peak_balance = self.start_balance
            
            # Set up signal handlers for graceful shutdown (only in main thread)
            try:
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
            except (ValueError, RuntimeError):
                # Running in thread, skip signal handlers
                logger.debug("Skipping signal handlers (running in thread)")
            
            logger.info(f"Bot initialized with balance: {self.start_balance} USDT")
            
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise
    
    async def start(self):
        """Bắt đầu chạy bot"""
        try:
            logger.info("Starting Binance Futures Trading Bot...")
            self.is_running = True
            
            # Initialize
            await self.initialize()
            
            # Start main trading loop
            await self._main_trading_loop()
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Dừng bot"""
        try:
            logger.info("Stopping bot...")
            self.is_running = False
            
            # Close all open positions (optional)
            # await self._close_all_positions()
            
            # Save models
            self.ai_engine.save_models()
            
            # Close connections
            try:
                await self.binance_client.close_connections()
            except Exception as conn_err:
                logger.debug(f"Connection close error (ignored): {conn_err}")
            
            logger.info("Bot stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
    
    async def _main_trading_loop(self):
        """Main trading loop - Trade nhanh mỗi 1-5 phút"""
        logger.info("🚀 Bot bắt đầu phân tích - Sẽ trade trong 10 giây - 5 phút!")
        
        iteration = 0
        while self.is_running:
            try:
                iteration += 1
                start_time = datetime.now()
                
                logger.info(f"🔄 Vòng {iteration}: Bắt đầu phân tích thị trường...")
                
                # Update account info
                await self._update_account_info()
                logger.info(f"💰 Balance: {self._get_current_balance():.2f} USDT")
                
                # Process each symbol - SONG SONG để nhanh hơn
                tasks = []
                for symbol in self.symbols:
                    if not self.is_running:
                        break
                    tasks.append(self._process_symbol(symbol))
                
                logger.info(f"📊 Đang phân tích {len(self.symbols)} symbols...")
                
                # Chạy song song tất cả symbols
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Check for errors
                success_count = 0
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ Error processing {self.symbols[i]}: {result}")
                    else:
                        success_count += 1
                
                logger.info(f"✅ Phân tích hoàn tất: {success_count}/{len(self.symbols)} symbols")
                
                # Check risk limits
                await self._check_risk_limits()
                
                # Log performance mỗi 5 lần
                if iteration % 5 == 0:
                    await self._log_performance()
                
                # TRADE NGAY sau khi phân tích xong
                if iteration == 1:
                    logger.info("🎯 First analysis complete - Opening positions NOW!")
                    # Lần đầu: Trade NGAY LẬP TỨC dựa trên AI predictions
                    wait_time = 2
                    logger.info("⚡ Trade NGAY sau 2 giây!")
                elif iteration < 5:
                    # 4 lần đầu: Trade mỗi 30 giây
                    wait_time = 30
                    logger.info(f"🔄 Vòng {iteration}: Trade tiếp sau 30 giây")
                else:
                    # Sau đó: Trade mỗi 1-2 phút
                    import random
                    wait_time = random.randint(60, 120)
                    logger.info(f"🔄 Vòng {iteration}: Trade tiếp sau {wait_time} giây")
                
                elapsed = (datetime.now() - start_time).total_seconds()
                actual_wait = max(1, wait_time - elapsed)
                
                logger.info(f"⏰ Đợi {actual_wait:.0f} giây trước vòng tiếp...")
                await asyncio.sleep(actual_wait)
                
            except Exception as e:
                logger.error(f"❌ Error in main trading loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _process_symbol(self, symbol: str):
        """Xử lý từng symbol - NHANH"""
        try:
            # Get market data
            klines_data = self.binance_client.get_klines(symbol, "5m", 500)
            
            # Update demo account ONLY if demo_mode is True AND demo_account exists
            if self.config["trading"]["demo_mode"] and klines_data:
                if hasattr(self.binance_client, 'demo_account') and self.binance_client.demo_account:
                    current_price = float(klines_data[-1][4])  # Close price
                    self.binance_client.demo_account.update_price(symbol, current_price)
                    # Update positions with current prices
                    current_prices = {symbol: current_price}
                    self.binance_client.demo_account.update_positions(current_prices)
            
            # Technical analysis
            analysis_result = self.technical_analyzer.full_analysis(klines_data)
            
            # Prepare data for AI
            df = self.technical_analyzer.prepare_dataframe(klines_data)
            df = self.technical_analyzer.add_basic_indicators(df)
            df = self.technical_analyzer.add_advanced_indicators(df)
            df = self.technical_analyzer.detect_candlestick_patterns(df)
            
            # AI prediction - Use trained models if available
            if symbol in self.trained_models and self.trained_models[symbol] is not None:
                # Use trained Gradient Boost model for instant accurate predictions
                ai_prediction = self._predict_with_trained_model(symbol, df)
                logger.info(f"🤖 {symbol}: AI Model Prediction = {ai_prediction['signal']} (Confidence: {ai_prediction['confidence']:.1%})")
            else:
                # Fallback to default AI engine
                features_df = self.ai_engine.prepare_features(df)
                ai_prediction = self.ai_engine.predict(features_df)
                logger.info(f"📊 {symbol}: Technical Analysis = {ai_prediction['signal']}")
            
            # Store market data
            self.market_data[symbol] = {
                'analysis': analysis_result,
                'ai_prediction': ai_prediction,
                'timestamp': datetime.now()
            }
            
            # Make trading decision
            await self._make_trading_decision(symbol, analysis_result, ai_prediction)
            
            # Update trailing stops
            await self._update_trailing_stops(symbol)
            
        except Exception as e:
            logger.error(f"Error processing symbol {symbol}: {e}")
    
    async def _make_trading_decision(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        ai_prediction: Dict[str, Any]
    ):
        """Đưa ra quyết định trading - THÔNG MINH hơn"""
        try:
            if not self.is_trading_enabled:
                logger.debug(f"{symbol}: Trading disabled")
                return
            
            signal = ai_prediction['signal']
            confidence = ai_prediction['confidence']
            
            # Lấy cấu hình AI
            min_confidence = self.config["ai_config"].get("confidence_threshold", 0.01)
            min_signal_strength = self.config["ai_config"].get("min_signal_strength", 0.01)
            
            logger.info(f"📊 {symbol}: Signal={signal}, Confidence={confidence:.2%}")
            
            # TRADE DỄ HƠN - Nếu có signal BUY hoặc SELL thì trade luôn
            if signal == 'HOLD':
                logger.info(f"⏭️ {symbol}: Signal=HOLD - Bỏ qua")
                return
            
            # Kiểm tra tín hiệu - Ngưỡng rất thấp để test
            if confidence < min_confidence:
                logger.info(f"⚠️ {symbol}: Confidence {confidence:.2%} < {min_confidence:.2%} - Bỏ qua")
                return
            
            # Kiểm tra trend và momentum
            trend = analysis.get('trend', 'NEUTRAL')
            rsi = analysis.get('rsi', 50)  # Default 50 if None
            macd_signal = analysis.get('macd_signal', 'NEUTRAL')  # Default NEUTRAL
            
            rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
            logger.info(f"🔍 {symbol}: Trend={trend}, RSI={rsi_str}, MACD={macd_signal}")
            
            # TRADE NGAY - Không cần nhiều tín hiệu xác nhận
            confirmations = 0
            if signal == 'BUY':
                if trend in ['UPTREND', 'STRONG_UPTREND']: confirmations += 1
                if rsi and rsi < 70: confirmations += 1  # RSI loose hơn
                if macd_signal == 'BUY': confirmations += 1
            elif signal == 'SELL':
                if trend in ['DOWNTREND', 'STRONG_DOWNTREND']: confirmations += 1
                if rsi and rsi > 30: confirmations += 1  # RSI loose hơn
                if macd_signal == 'SELL': confirmations += 1
            
            # Chỉ cần 1 tín hiệu là đủ - TRADE NHANH
            if confirmations < 1:
                logger.info(f"⏭️ {symbol}: Không có tín hiệu rõ ràng - Bỏ qua")
                return
            
            logger.info(f"🎯 {symbol}: TÍN HIỆU {signal} - Confidence: {confidence:.2%}, Confirmations: {confirmations}/3 - TRADE NGAY!")
            
            # Get current price
            current_price = analysis['current_price']
            
            # Calculate position size
            account_balance = self._get_current_balance()
            
            # Check if we have an existing position
            open_positions = self.binance_client.get_open_positions()
            existing_position = next((pos for pos in open_positions if pos['symbol'] == symbol), None)
            
            if existing_position:
                await self._manage_existing_position(symbol, existing_position, signal, analysis)
            else:
                await self._open_new_position(symbol, signal, current_price, account_balance, analysis, ai_prediction)
            
        except Exception as e:
            logger.error(f"Error making trading decision for {symbol}: {e}")
    
    async def _open_new_position(
        self,
        symbol: str,
        signal: str,
        current_price: float,
        account_balance: float,
        analysis: Dict[str, Any],
        ai_prediction: Dict[str, Any]
    ):
        """Mở vị thế mới"""
        try:
            if signal == 'HOLD':
                return
            
            side = 'BUY' if signal == 'BUY' else 'SELL'
            
            # Calculate stop loss
            atr = analysis.get('current_atr')
            support_resistance = analysis.get('support_resistance')
            stop_loss_price = self.risk_manager.calculate_stop_loss(
                current_price, side, atr, support_resistance
            )
            
            # Calculate position size
            position_size_info = self.risk_manager.calculate_position_size(
                account_balance, current_price, stop_loss_price, symbol
            )
            
            quantity = position_size_info['quantity']
            
            # Validate trade
            validation = self.risk_manager.validate_trade(
                signal, symbol, quantity, current_price, ai_prediction['confidence']
            )
            
            if not validation['is_valid']:
                logger.warning(f"{symbol}: Trade rejected - {validation['reasons']}")
                return
            
            # Log warnings
            for warning in validation['warnings']:
                logger.warning(f"{symbol}: {warning}")
            
            # Set leverage (35-40x tùy theo symbol)
            leverage_map = {
                "BTCUSDT": 40,
                "ETHUSDT": 38,
                "SOLUSDT": 35,
                "ADAUSDT": 35
            }
            leverage = leverage_map.get(symbol, 35)  # Default 35x
            self.binance_client.set_leverage(symbol, leverage)
            logger.info(f"⚙️ Set {symbol} leverage to {leverage}x")
            
            # Place market order
            try:
                order = self.binance_client.place_market_order(symbol, side, quantity)
                
                if order['status'] == 'FILLED':
                    fill_price = float(order['avgPrice'])
                    
                    # Calculate take profit levels
                    take_profit_levels = self.risk_manager.calculate_take_profit(
                        fill_price, stop_loss_price, side
                    )
                    
                    # Place stop loss order
                    stop_side = 'SELL' if side == 'BUY' else 'BUY'
                    stop_order = self.binance_client.place_stop_market_order(
                        symbol, stop_side, quantity, stop_loss_price
                    )
                    
                    # Place take profit orders (partial)
                    tp_orders = []
                    if take_profit_levels:
                        tp_quantity = quantity / len(take_profit_levels)
                        for i, tp_price in enumerate(take_profit_levels):
                            try:
                                tp_order = self.binance_client.place_limit_order(
                                    symbol, stop_side, tp_quantity, tp_price
                                )
                                tp_orders.append(tp_order)
                            except Exception as e:
                                logger.error(f"Error placing TP order {i+1}: {e}")
                    
                    # Track position
                    position_data = {
                        'symbol': symbol,
                        'side': side,
                        'quantity': quantity,
                        'entry_price': fill_price,
                        'stop_loss_price': stop_loss_price,
                        'take_profit_levels': take_profit_levels,
                        'order_id': order['orderId'],
                        'stop_order_id': stop_order['orderId'] if stop_order else None,
                        'tp_order_ids': [tp['orderId'] for tp in tp_orders],
                        'ai_confidence': ai_prediction['confidence'],
                        'open_time': datetime.now()
                    }
                    
                    self.risk_manager.update_position_tracking(symbol, position_data)
                    
                    logger.info(f"✅ {symbol}: Opened {side} position - "
                               f"Qty: {quantity}, Price: {fill_price}, "
                               f"SL: {stop_loss_price}, Confidence: {ai_prediction['confidence']:.3f}")
                
            except Exception as e:
                logger.error(f"Error placing order for {symbol}: {e}")
        
        except Exception as e:
            logger.error(f"Error opening new position for {symbol}: {e}")
    
    async def _manage_existing_position(
        self,
        symbol: str,
        position: Dict[str, Any],
        signal: str,
        analysis: Dict[str, Any]
    ):
        """Quản lý vị thế hiện tại"""
        try:
            position_side = position['positionSide']
            position_amount = float(position['positionAmt'])
            
            # Check if we should close position
            if (position_amount > 0 and signal == 'SELL') or (position_amount < 0 and signal == 'BUY'):
                logger.info(f"{symbol}: Opposite signal detected - considering position close")
                # Could implement position closing logic here
            
        except Exception as e:
            logger.error(f"Error managing existing position for {symbol}: {e}")
    
    async def _update_trailing_stops(self, symbol: str):
        """Cập nhật trailing stops"""
        try:
            if symbol not in self.risk_manager.open_positions:
                return
            
            current_price = self.market_data[symbol]['analysis']['current_price']
            position_info = self.risk_manager.open_positions[symbol]
            
            new_stop = self.risk_manager.update_trailing_stop(symbol, current_price, position_info)
            
            if new_stop:
                # Update stop loss order on exchange
                # Implementation would go here
                logger.debug(f"{symbol}: Trailing stop updated to {new_stop}")
        
        except Exception as e:
            logger.error(f"Error updating trailing stops for {symbol}: {e}")
    
    async def _update_account_info(self):
        """Cập nhật thông tin tài khoản"""
        try:
            account_info = self.binance_client.get_account_info()
            current_balance = float(account_info['totalWalletBalance'])
            
            # Update peak balance
            if current_balance > self.peak_balance:
                self.peak_balance = current_balance
            
            # Check drawdown
            drawdown_info = self.risk_manager.check_drawdown(current_balance, self.peak_balance)
            
            if drawdown_info['is_critical']:
                logger.warning(f"Critical drawdown reached: {drawdown_info['current_drawdown']:.2f}%")
                if drawdown_info.get('action') == 'stop_trading':
                    self.is_trading_enabled = False
                    logger.warning("Trading disabled due to excessive drawdown")
        
        except Exception as e:
            logger.error(f"Error updating account info: {e}")
    
    async def _check_risk_limits(self):
        """Kiểm tra các giới hạn rủi ro"""
        try:
            risk_metrics = self.risk_manager.get_risk_metrics()
            
            # Check daily loss limit
            daily_loss_limit = self.start_balance * (self.config["risk_management"]["max_daily_loss_percent"] / 100)
            
            if risk_metrics['daily_pnl'] < -daily_loss_limit:
                self.is_trading_enabled = False
                logger.warning(f"Daily loss limit reached: {risk_metrics['daily_pnl']:.2f}")
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
    
    async def _log_performance(self):
        """Log hiệu suất bot"""
        try:
            current_balance = self._get_current_balance()
            daily_pnl = current_balance - self.start_balance
            daily_pnl_percent = (daily_pnl / self.start_balance) * 100 if self.start_balance > 0 else 0
            
            risk_metrics = self.risk_manager.get_risk_metrics()
            
            logger.info(f"📊 Performance Update:")
            logger.info(f"   Balance: {current_balance:.2f} USDT ({daily_pnl:+.2f} | {daily_pnl_percent:+.2f}%)")
            logger.info(f"   Open Positions: {risk_metrics['open_positions']}")
            logger.info(f"   Win Rate: {risk_metrics['win_rate']:.1f}%")
            logger.info(f"   Risk Score: {risk_metrics['risk_score']:.2f}")
            
        except Exception as e:
            logger.error(f"Error logging performance: {e}")
    
    def _get_current_balance(self) -> float:
        """Lấy số dư hiện tại"""
        try:
            account_info = self.binance_client.get_account_info()
            return float(account_info['totalWalletBalance'])
        except Exception as e:
            logger.error(f"Error getting current balance: {e}")
            return 0.0
    
    def _signal_handler(self, signum, frame):
        """Xử lý signal để tắt bot gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.is_running = False
    
    async def retrain_models(self):
        """Retrain AI models với dữ liệu mới"""
        try:
            logger.info("Starting model retraining...")
            
            # Collect training data from all symbols
            all_features = []
            all_targets = []
            
            for symbol in self.symbols:
                try:
                    # Get historical data
                    klines_data = self.binance_client.get_klines(symbol, "5m", 2000)
                    
                    # Prepare data
                    df = self.technical_analyzer.prepare_dataframe(klines_data)
                    df = self.technical_analyzer.add_basic_indicators(df)
                    df = self.technical_analyzer.add_advanced_indicators(df)
                    df = self.technical_analyzer.detect_candlestick_patterns(df)
                    
                    # Prepare features and targets
                    features_df = self.ai_engine.prepare_features(df)
                    targets_df = self.ai_engine.create_targets(df)
                    
                    all_features.append(features_df)
                    all_targets.append(targets_df)
                    
                except Exception as e:
                    logger.error(f"Error preparing training data for {symbol}: {e}")
                    continue
            
            if all_features and all_targets:
                # Combine all data
                combined_features = pd.concat(all_features, ignore_index=True)
                combined_targets = pd.concat(all_targets, ignore_index=True)
                
                # Train models
                performance = self.ai_engine.train_models(combined_features, combined_targets)
                logger.info(f"Models retrained - Accuracy: {performance['accuracy']:.3f}")
            
        except Exception as e:
            logger.error(f"Error retraining models: {e}")

async def main():
    """Main function"""
    # Setup logging
    logger.add("logs/trading_bot.log", rotation="10 MB", retention="30 days", level="INFO")
    
    # Create and start bot
    bot = BinanceFuturesBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
