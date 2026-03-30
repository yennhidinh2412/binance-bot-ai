"""
CONTINUOUS LEARNING ENGINE - Bot tự học liên tục từ thị trường
Kết hợp 3 chiến lược:
1. Auto Re-train Daily - Train lại mỗi ngày với data mới nhất
2. Adaptive Re-train - Train khi performance giảm
3. Continuous Learning - Học từ trades thật
"""
import asyncio
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from binance_client import BinanceFuturesClient
from technical_analysis import TechnicalAnalyzer
from train_ai_improved import (
    prepare_advanced_features, 
    detect_candlestick_patterns, 
    calculate_trend_features,
    create_smart_labels
)
import os
import json

class ContinuousLearningEngine:
    """
    🧠 ENGINE HỌC LIÊN TỤC - Tự động cập nhật model với market mới
    """
    
    def __init__(self):
        self.client = BinanceFuturesClient()
        self.analyzer = TechnicalAnalyzer()
        self.symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        # Tracking
        self.trade_history = []  # Lưu các trades thật để học
        self.performance_log = {}  # Track accuracy theo thời gian
        self.last_train_time = {}  # Lần train cuối
        
        # Thresholds
        self.min_accuracy = 60  # Nếu accuracy < 60% → re-train ngay
        self.min_trades_for_retrain = 100  # Học sau 100 trades
        self.retrain_interval_hours = 24  # Re-train mỗi 24h
        
        # Load performance history
        self.load_performance_history()
    
    def load_performance_history(self):
        """Load lịch sử performance từ file"""
        try:
            if os.path.exists('models/performance_history.json'):
                with open('models/performance_history.json', 'r') as f:
                    data = json.load(f)
                    self.performance_log = data.get('performance_log', {})
                    self.last_train_time = {k: datetime.fromisoformat(v) for k, v in data.get('last_train_time', {}).items()}
                    logger.info("✅ Loaded performance history")
        except Exception as e:
            logger.warning(f"⚠️ Could not load performance history: {e}")
    
    def save_performance_history(self):
        """Lưu lịch sử performance"""
        try:
            os.makedirs('models', exist_ok=True)
            data = {
                'performance_log': self.performance_log,
                'last_train_time': {k: v.isoformat() for k, v in self.last_train_time.items()},
                'updated_at': datetime.now().isoformat()
            }
            with open('models/performance_history.json', 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("💾 Saved performance history")
        except Exception as e:
            logger.error(f"❌ Error saving performance history: {e}")
    
    async def should_retrain(self, symbol):
        """
        🤔 Kiểm tra xem có nên re-train model không?
        Returns: (bool, reason)
        """
        reasons = []
        should_train = False
        
        # 1. Check daily interval
        if symbol not in self.last_train_time:
            should_train = True
            reasons.append("First time training")
        else:
            hours_since_train = (datetime.now() - self.last_train_time[symbol]).total_seconds() / 3600
            if hours_since_train >= self.retrain_interval_hours:
                should_train = True
                reasons.append(f"Daily re-train (last: {hours_since_train:.1f}h ago)")
        
        # 2. Check performance degradation
        if symbol in self.performance_log:
            recent_accuracy = self.performance_log[symbol].get('recent_accuracy', 100)
            if recent_accuracy < self.min_accuracy:
                should_train = True
                reasons.append(f"Low accuracy ({recent_accuracy:.1f}% < {self.min_accuracy}%)")
        
        # 3. Check trades count for continuous learning
        if symbol in self.performance_log:
            trades_since_train = self.performance_log[symbol].get('trades_since_last_train', 0)
            if trades_since_train >= self.min_trades_for_retrain:
                should_train = True
                reasons.append(f"Continuous learning ({trades_since_train} trades collected)")
        
        return should_train, reasons
    
    async def train_model_realtime(self, symbol, lookback_days=7):
        """
        🎓 TRAIN MODEL với dữ liệu REAL-TIME mới nhất
        lookback_days: Số ngày dữ liệu để train (default 7 ngày)
        Note: Binance max limit 1500 candles
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"🎓 REAL-TIME TRAINING: {symbol}")
        logger.info(f"{'='*70}")
        
        try:
            # Calculate candles needed (7 days = 2016 candles of 5m)
            # But Binance max is 1500, so cap it
            num_candles = min(lookback_days * 288, 1500)  # 288 candles per day (5m interval)
            actual_days = num_candles / 288
            
            # Download fresh data
            logger.info(f"📥 Downloading {num_candles} candles (~{actual_days:.1f} days)...")
            klines = self.client.get_klines(symbol, "5m", num_candles)
            
            if not klines:
                logger.error(f"❌ No data for {symbol}")
                return False
            
            logger.info(f"✅ Downloaded {len(klines)} candles")
            logger.info(f"📅 Data range: {klines[0][0]} to {klines[-1][0]}")
            
            # Prepare dataframe with indicators
            logger.info("📊 Calculating indicators...")
            df = self.analyzer.prepare_dataframe(klines)
            df = self.analyzer.add_basic_indicators(df)
            df = self.analyzer.add_advanced_indicators(df)
            
            # Create labels
            logger.info("🏷️ Creating smart labels...")
            labels = create_smart_labels(
                df, future_bars=12, threshold=0.006
            )
            df['label'] = labels
            
            # Prepare features
            logger.info("🔧 Preparing advanced features...")
            X, feature_names = prepare_advanced_features(df)
            y = df['label'].values
            
            # Remove invalid samples
            valid_mask = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
            X = X[valid_mask]
            y = y[valid_mask]
            
            logger.info(f"📈 Dataset: {len(X)} samples, {X.shape[1]} features")
            logger.info(f"📊 Label distribution: LONG={np.sum(y==1)}, SHORT={np.sum(y==-1)}, HOLD={np.sum(y==0)}")
            
            # Time-series split (no data leak)
            split_idx = int(len(X) * 0.8)
            X_train = X[:split_idx]
            X_test = X[split_idx:]
            y_train = y[:split_idx]
            y_test = y[split_idx:]
            
            # Train model with V3 anti-overfit params
            logger.info("🤖 Training Gradient Boosting model...")
            model = GradientBoostingClassifier(
                n_estimators=300,
                learning_rate=0.01,    # was 0.03
                max_depth=4,           # was 6
                subsample=0.75,
                min_samples_split=20,
                min_samples_leaf=15,   # was 5 → stronger regularization
                max_features='sqrt',
                random_state=42
            )
            model.fit(X_train, y_train)
            
            # Evaluate
            train_accuracy = model.score(X_train, y_train) * 100
            test_accuracy = model.score(X_test, y_test) * 100
            
            logger.info(f"✅ Train Accuracy: {train_accuracy:.2f}%")
            logger.info(f"✅ Test Accuracy: {test_accuracy:.2f}%")
            
            # Save model
            os.makedirs('models', exist_ok=True)
            model_path = f'models/gradient_boost_{symbol}.pkl'
            
            model_data = {
                'model': model,
                'accuracy': test_accuracy,
                'feature_names': feature_names,
                'trained_at': datetime.now().isoformat(),
                'data_range_days': actual_days,
                'num_samples': len(X),
                'label_distribution': {
                    'LONG': int(np.sum(y==1)),
                    'SHORT': int(np.sum(y==-1)),
                    'HOLD': int(np.sum(y==0))
                }
            }
            
            joblib.dump(model_data, model_path)
            logger.info(f"💾 Model saved to {model_path}")
            
            # Update tracking
            self.last_train_time[symbol] = datetime.now()
            self.performance_log[symbol] = {
                'recent_accuracy': test_accuracy,
                'train_accuracy': train_accuracy,
                'trained_at': datetime.now().isoformat(),
                'trades_since_last_train': 0,
                'lookback_days': actual_days
            }
            self.save_performance_history()
            
            logger.info(f"✅ Training completed for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Training failed for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def auto_retrain_all_symbols(self):
        """
        🔄 AUTO RE-TRAIN tất cả symbols nếu cần
        Kiểm tra từng symbol và train nếu đủ điều kiện
        """
        logger.info("\n" + "="*70)
        logger.info("🔄 AUTO RE-TRAIN CHECK")
        logger.info("="*70)
        
        results = {}
        
        for symbol in self.symbols:
            should_train, reasons = await self.should_retrain(symbol)
            
            if should_train:
                logger.info(f"\n🎯 {symbol} needs re-training:")
                for reason in reasons:
                    logger.info(f"   • {reason}")
                
                success = await self.train_model_realtime(symbol)
                results[symbol] = {'trained': True, 'success': success, 'reasons': reasons}
            else:
                logger.info(f"✅ {symbol} is up-to-date")
                results[symbol] = {'trained': False, 'reasons': ['Model is current']}
        
        return results
    
    def record_trade_result(self, symbol, signal, entry_price, exit_price, profit_pct):
        """
        📝 GHI NHẬN kết quả trade để học
        Lưu lại trades thật để re-train model
        """
        trade_record = {
            'symbol': symbol,
            'signal': signal,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'profit_pct': profit_pct,
            'success': profit_pct > 0,
            'timestamp': datetime.now().isoformat()
        }
        
        self.trade_history.append(trade_record)
        
        # Update performance tracking
        if symbol not in self.performance_log:
            self.performance_log[symbol] = {
                'recent_accuracy': 100,
                'trades_since_last_train': 0
            }
        
        self.performance_log[symbol]['trades_since_last_train'] += 1
        
        # Calculate recent win rate (last 20 trades)
        recent_trades = [t for t in self.trade_history if t['symbol'] == symbol][-20:]
        if len(recent_trades) >= 10:
            wins = sum(1 for t in recent_trades if t['success'])
            win_rate = (wins / len(recent_trades)) * 100
            self.performance_log[symbol]['recent_accuracy'] = win_rate
        
        # Save to file for persistence
        self.save_trade_history()
        self.save_performance_history()
        
        logger.info(f"📝 Recorded trade: {symbol} {signal} → {profit_pct:+.2f}%")
    
    def save_trade_history(self):
        """Lưu lịch sử trades"""
        try:
            os.makedirs('models', exist_ok=True)
            with open('models/trade_history.json', 'w') as f:
                json.dump(self.trade_history, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Error saving trade history: {e}")
    
    def load_trade_history(self):
        """Load lịch sử trades"""
        try:
            if os.path.exists('models/trade_history.json'):
                with open('models/trade_history.json', 'r') as f:
                    self.trade_history = json.load(f)
                logger.info(f"✅ Loaded {len(self.trade_history)} trade records")
        except Exception as e:
            logger.warning(f"⚠️ Could not load trade history: {e}")
    
    async def continuous_learning_loop(self, check_interval_hours=1):
        """
        🔁 CONTINUOUS LEARNING LOOP
        Chạy background task kiểm tra và re-train định kỳ
        """
        logger.info("\n" + "="*70)
        logger.info("🔁 CONTINUOUS LEARNING LOOP STARTED")
        logger.info(f"   Check interval: {check_interval_hours}h")
        logger.info("="*70)

        # Wait before first retrain so main_loop can start
        await asyncio.sleep(600)  # 10 min delay

        while True:
            try:
                # Check and retrain if needed
                results = await self.auto_retrain_all_symbols()
                
                # Log summary
                trained_count = sum(1 for r in results.values() if r['trained'])
                logger.info(f"\n📊 Re-train summary: {trained_count}/{len(self.symbols)} models updated")
                
                # Wait for next check
                await asyncio.sleep(check_interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"❌ Error in continuous learning loop: {e}")
                await asyncio.sleep(600)  # Wait 10 minutes on error
    
    async def force_retrain_all(self, lookback_days=7):
        """
        🔥 FORCE RE-TRAIN tất cả models ngay lập tức
        Dùng khi cần cập nhật model khẩn cấp
        """
        logger.info("\n" + "="*70)
        logger.info("🔥 FORCE RE-TRAIN ALL MODELS")
        logger.info("="*70)
        
        results = {}
        
        for symbol in self.symbols:
            success = await self.train_model_realtime(symbol, lookback_days)
            results[symbol] = success
        
        # Summary
        success_count = sum(1 for s in results.values() if s)
        logger.info(f"\n✅ Re-trained {success_count}/{len(self.symbols)} models successfully")
        
        return results

# Standalone functions for easy use
async def quick_retrain_all():
    """Quick function để re-train tất cả models"""
    engine = ContinuousLearningEngine()
    return await engine.force_retrain_all()

async def start_continuous_learning(check_interval_hours=1):
    """Start continuous learning background task"""
    engine = ContinuousLearningEngine()
    await engine.continuous_learning_loop(check_interval_hours)

if __name__ == "__main__":
    # Test re-training
    async def test():
        engine = ContinuousLearningEngine()
        
        # Force re-train all models
        logger.info("🎯 Testing force re-train...")
        results = await engine.force_retrain_all(lookback_days=7)
        
        # Show results
        logger.info("\n" + "="*70)
        logger.info("📊 RESULTS:")
        for symbol, success in results.items():
            status = "✅" if success else "❌"
            logger.info(f"   {status} {symbol}")
    
    asyncio.run(test())
