"""
ADVANCED AI ENGINE - Super Smart Trading Bot
Tích hợp:
1. Multi-Timeframe Analysis (5m, 15m, 1h, 4h)
2. Advanced Candlestick Patterns (20+ patterns)
3. Deep Learning LSTM Model
4. Ensemble Model System (GradientBoosting + XGBoost + LSTM)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from loguru import logger
import joblib
import os
from datetime import datetime

# ML Libraries
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.metrics import accuracy_score, classification_report
import warnings
warnings.filterwarnings('ignore')

# Try to import XGBoost
try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    logger.warning("XGBoost not available, using RandomForest instead")

# TensorFlow/LSTM disabled — bot uses GradientBoosting ensemble (V7)
# Importing TF on servers without it causes 15-20s startup delay
HAS_TENSORFLOW = False


class AdvancedCandlestickPatterns:
    """
    20+ Candlestick Patterns Recognition
    Nhận dạng các mẫu nến phức tạp
    """
    
    @staticmethod
    def detect_all_patterns(df: pd.DataFrame) -> pd.DataFrame:
        """Detect all candlestick patterns"""
        df = df.copy()
        
        # Basic candle properties
        df['body'] = abs(df['close'] - df['open'])
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
        df['body_pct'] = df['body'] / (df['high'] - df['low'] + 0.0001)
        df['is_bullish'] = (df['close'] > df['open']).astype(int)
        
        # 1. Doji (indecision)
        df['doji'] = (df['body_pct'] < 0.1).astype(int) * 50
        
        # 2. Hammer (bullish reversal)
        df['hammer'] = ((df['lower_shadow'] > 2 * df['body']) & 
                        (df['upper_shadow'] < df['body'] * 0.5) &
                        (df['body_pct'] > 0.1)).astype(int) * 100
        
        # 3. Inverted Hammer
        df['inverted_hammer'] = ((df['upper_shadow'] > 2 * df['body']) & 
                                  (df['lower_shadow'] < df['body'] * 0.5) &
                                  (df['body_pct'] > 0.1)).astype(int) * 100
        
        # 4. Shooting Star (bearish reversal)
        df['shooting_star'] = ((df['upper_shadow'] > 2 * df['body']) & 
                                (df['lower_shadow'] < df['body'] * 0.3) &
                                (df['is_bullish'] == 0)).astype(int) * -100
        
        # 5. Hanging Man (bearish)
        df['hanging_man'] = ((df['lower_shadow'] > 2 * df['body']) & 
                              (df['upper_shadow'] < df['body'] * 0.3) &
                              (df['is_bullish'] == 0)).astype(int) * -100
        
        # 6. Bullish Engulfing
        df['bullish_engulfing'] = ((df['is_bullish'] == 1) & 
                                    (df['is_bullish'].shift(1) == 0) &
                                    (df['open'] < df['close'].shift(1)) &
                                    (df['close'] > df['open'].shift(1))).astype(int) * 100
        
        # 7. Bearish Engulfing
        df['bearish_engulfing'] = ((df['is_bullish'] == 0) & 
                                    (df['is_bullish'].shift(1) == 1) &
                                    (df['open'] > df['close'].shift(1)) &
                                    (df['close'] < df['open'].shift(1))).astype(int) * -100
        
        # 8. Morning Star (bullish - 3 candle pattern)
        df['morning_star'] = ((df['is_bullish'].shift(2) == 0) &  # First: bearish
                               (df['body'].shift(1) < df['body'].shift(2) * 0.3) &  # Second: small body
                               (df['is_bullish'] == 1) &  # Third: bullish
                               (df['close'] > (df['open'].shift(2) + df['close'].shift(2)) / 2)).astype(int) * 100
        
        # 9. Evening Star (bearish - 3 candle pattern)
        df['evening_star'] = ((df['is_bullish'].shift(2) == 1) &  # First: bullish
                               (df['body'].shift(1) < df['body'].shift(2) * 0.3) &  # Second: small body
                               (df['is_bullish'] == 0) &  # Third: bearish
                               (df['close'] < (df['open'].shift(2) + df['close'].shift(2)) / 2)).astype(int) * -100
        
        # 10. Three White Soldiers (strong bullish)
        df['three_white_soldiers'] = ((df['is_bullish'] == 1) & 
                                       (df['is_bullish'].shift(1) == 1) & 
                                       (df['is_bullish'].shift(2) == 1) &
                                       (df['close'] > df['close'].shift(1)) &
                                       (df['close'].shift(1) > df['close'].shift(2))).astype(int) * 100
        
        # 11. Three Black Crows (strong bearish)
        df['three_black_crows'] = ((df['is_bullish'] == 0) & 
                                    (df['is_bullish'].shift(1) == 0) & 
                                    (df['is_bullish'].shift(2) == 0) &
                                    (df['close'] < df['close'].shift(1)) &
                                    (df['close'].shift(1) < df['close'].shift(2))).astype(int) * -100
        
        # 12. Piercing Line (bullish)
        df['piercing_line'] = ((df['is_bullish'].shift(1) == 0) &
                                (df['is_bullish'] == 1) &
                                (df['open'] < df['low'].shift(1)) &
                                (df['close'] > (df['open'].shift(1) + df['close'].shift(1)) / 2) &
                                (df['close'] < df['open'].shift(1))).astype(int) * 100
        
        # 13. Dark Cloud Cover (bearish)
        df['dark_cloud'] = ((df['is_bullish'].shift(1) == 1) &
                             (df['is_bullish'] == 0) &
                             (df['open'] > df['high'].shift(1)) &
                             (df['close'] < (df['open'].shift(1) + df['close'].shift(1)) / 2) &
                             (df['close'] > df['close'].shift(1))).astype(int) * -100
        
        # 14. Tweezer Top (bearish reversal)
        df['tweezer_top'] = ((abs(df['high'] - df['high'].shift(1)) < df['body'] * 0.1) &
                              (df['is_bullish'].shift(1) == 1) &
                              (df['is_bullish'] == 0)).astype(int) * -80
        
        # 15. Tweezer Bottom (bullish reversal)
        df['tweezer_bottom'] = ((abs(df['low'] - df['low'].shift(1)) < df['body'] * 0.1) &
                                 (df['is_bullish'].shift(1) == 0) &
                                 (df['is_bullish'] == 1)).astype(int) * 80
        
        # 16. Spinning Top (indecision)
        df['spinning_top'] = ((df['body_pct'] < 0.3) & 
                               (df['body_pct'] > 0.1) &
                               (df['upper_shadow'] > df['body']) &
                               (df['lower_shadow'] > df['body'])).astype(int) * 30
        
        # 17. Marubozu (strong trend)
        df['bullish_marubozu'] = ((df['is_bullish'] == 1) &
                                   (df['body_pct'] > 0.9)).astype(int) * 100
        df['bearish_marubozu'] = ((df['is_bullish'] == 0) &
                                   (df['body_pct'] > 0.9)).astype(int) * -100
        
        # 18. Harami (reversal)
        df['bullish_harami'] = ((df['is_bullish'].shift(1) == 0) &
                                 (df['is_bullish'] == 1) &
                                 (df['body'] < df['body'].shift(1)) &
                                 (df['high'] < df['open'].shift(1)) &
                                 (df['low'] > df['close'].shift(1))).astype(int) * 80
        
        df['bearish_harami'] = ((df['is_bullish'].shift(1) == 1) &
                                 (df['is_bullish'] == 0) &
                                 (df['body'] < df['body'].shift(1)) &
                                 (df['high'] < df['close'].shift(1)) &
                                 (df['low'] > df['open'].shift(1))).astype(int) * -80
        
        # 19. Rising/Falling Three Methods
        # (Complex pattern - simplified version)
        
        # 20. Kicker Pattern (very strong reversal)
        df['bullish_kicker'] = ((df['is_bullish'].shift(1) == 0) &
                                 (df['is_bullish'] == 1) &
                                 (df['open'] > df['open'].shift(1)) &
                                 (df['close'] > df['open'].shift(1))).astype(int) * 100
        
        df['bearish_kicker'] = ((df['is_bullish'].shift(1) == 1) &
                                 (df['is_bullish'] == 0) &
                                 (df['open'] < df['open'].shift(1)) &
                                 (df['close'] < df['open'].shift(1))).astype(int) * -100
        
        # Calculate overall pattern score
        pattern_columns = ['doji', 'hammer', 'inverted_hammer', 'shooting_star', 
                          'hanging_man', 'bullish_engulfing', 'bearish_engulfing',
                          'morning_star', 'evening_star', 'three_white_soldiers',
                          'three_black_crows', 'piercing_line', 'dark_cloud',
                          'tweezer_top', 'tweezer_bottom', 'spinning_top',
                          'bullish_marubozu', 'bearish_marubozu', 
                          'bullish_harami', 'bearish_harami',
                          'bullish_kicker', 'bearish_kicker']
        
        df['pattern_score'] = df[pattern_columns].sum(axis=1)
        df['pattern_signal'] = np.where(df['pattern_score'] > 50, 1,
                                        np.where(df['pattern_score'] < -50, -1, 0))
        
        return df


class MultiTimeframeAnalyzer:
    """
    Multi-Timeframe Analysis
    Phân tích đồng thời 5m, 15m, 1h, 4h
    """
    
    def __init__(self, client, analyzer):
        self.client = client
        self.analyzer = analyzer
        self.timeframes = ['5m', '15m', '1h', '4h']
    
    def get_mtf_features(self, symbol: str) -> Dict:
        """Get features from multiple timeframes"""
        mtf_data = {}
        
        for tf in self.timeframes:
            try:
                klines = self.client.get_klines(symbol, tf, 100)
                df = self.analyzer.prepare_dataframe(klines)
                df = self.analyzer.add_basic_indicators(df)
                
                latest = df.iloc[-1]
                
                # Extract key features
                mtf_data[f'{tf}_rsi'] = latest.get('rsi', 50)
                mtf_data[f'{tf}_macd'] = latest.get('macd', 0)
                mtf_data[f'{tf}_macd_signal'] = latest.get('macd_signal', 0)
                mtf_data[f'{tf}_bb_percent'] = latest.get('bb_percent', 0.5)
                
                # Trend direction
                if 'ema_50' in df.columns and 'ema_200' in df.columns:
                    mtf_data[f'{tf}_trend'] = 1 if latest['ema_50'] > latest['ema_200'] else -1
                else:
                    mtf_data[f'{tf}_trend'] = 0
                
                # Momentum
                mtf_data[f'{tf}_momentum'] = (float(df['close'].iloc[-1]) - float(df['close'].iloc[-5])) / float(df['close'].iloc[-5]) * 100
                
                # ADX for trend strength
                if 'adx' in df.columns:
                    mtf_data[f'{tf}_adx'] = latest['adx']
                
            except Exception as e:
                logger.warning(f"Error getting {tf} data for {symbol}: {e}")
                # Fill with neutral values
                mtf_data[f'{tf}_rsi'] = 50
                mtf_data[f'{tf}_trend'] = 0
                mtf_data[f'{tf}_momentum'] = 0
        
        # Calculate alignment score
        trends = [mtf_data.get(f'{tf}_trend', 0) for tf in self.timeframes]
        mtf_data['trend_alignment'] = sum(trends) / len(trends)  # -1 to 1
        
        # Calculate overall momentum
        momentums = [mtf_data.get(f'{tf}_momentum', 0) for tf in self.timeframes]
        mtf_data['avg_momentum'] = sum(momentums) / len(momentums)
        
        return mtf_data


class LSTMModel:
    """
    Deep Learning LSTM Model for Time Series Prediction
    Sử dụng Bidirectional LSTM với Attention mechanism
    """
    
    def __init__(self, sequence_length: int = 30, n_features: int = 31):
        self.sequence_length = sequence_length
        self.n_features = n_features
        self.model = None
        self.scaler = RobustScaler()
        
    def build_model(self, n_features: int):
        """Build LSTM model architecture"""
        if not HAS_TENSORFLOW:
            logger.error("TensorFlow not available!")
            return None
        
        self.n_features = n_features
        
        # Lighter architecture to prevent overfitting (was BiLSTM128+64+LSTM32)
        # sequence_length reduced: 60→30, removing middle BiLSTM layer
        l2_reg = regularizers.l2(1e-4)
        model = Sequential([
            # Single Bidirectional LSTM with L2 regularization
            Bidirectional(LSTM(
                64, return_sequences=True,
                input_shape=(self.sequence_length, n_features),
                kernel_regularizer=l2_reg,
                recurrent_regularizer=l2_reg
            )),
            BatchNormalization(),
            Dropout(0.4),  # was 0.3

            # Final LSTM layer (no return_sequences)
            LSTM(
                16, return_sequences=False,  # was 32
                kernel_regularizer=l2_reg
            ),
            BatchNormalization(),
            Dropout(0.4),  # was 0.2

            # Dense output layers
            Dense(32, activation='relu'),  # was 64
            Dropout(0.3),
            Dense(16, activation='relu'),  # was 32
            Dense(3, activation='softmax')  # SHORT, HOLD, LONG
        ])

        model.compile(
            optimizer=Adam(learning_rate=0.0005),  # was 0.001
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy']
        )
        
        self.model = model
        return model
    
    def prepare_sequences(self, X: np.ndarray, y: np.ndarray = None) -> Tuple:
        """Prepare sequences for LSTM"""
        X_scaled = self.scaler.fit_transform(X) if y is not None else self.scaler.transform(X)
        
        X_seq = []
        y_seq = [] if y is not None else None
        
        for i in range(self.sequence_length, len(X_scaled)):
            X_seq.append(X_scaled[i-self.sequence_length:i])
            if y is not None:
                y_seq.append(y[i])
        
        X_seq = np.array(X_seq)
        
        if y is not None:
            y_seq = np.array(y_seq)
            # Convert labels: -1->0, 0->1, 1->2
            y_seq = y_seq + 1
            return X_seq, y_seq
        
        return X_seq
    
    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 50, batch_size: int = 32):
        """Train LSTM model"""
        if not HAS_TENSORFLOW:
            logger.error("TensorFlow not available!")
            return None
        
        # Prepare sequences
        X_seq, y_seq = self.prepare_sequences(X, y)
        
        # Split data
        split_idx = int(len(X_seq) * 0.8)
        X_train, X_val = X_seq[:split_idx], X_seq[split_idx:]
        y_train, y_val = y_seq[:split_idx], y_seq[split_idx:]
        
        # Build model if not exists
        if self.model is None:
            self.build_model(X.shape[1])
        
        # Callbacks — reduced patience (5 was 10) to avoid overfitting on small splits
        callbacks = [
            EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True),
            ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3, min_lr=0.0001)
        ]

        # Class weights to handle label imbalance
        from sklearn.utils.class_weight import compute_class_weight
        classes_present = np.unique(y_train)
        cw = compute_class_weight('balanced', classes=classes_present, y=y_train)
        class_weight_dict = {int(c): float(w) for c, w in zip(classes_present, cw)}

        # Train — reduced epochs: 50→25 to prevent overfitting
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=25,
            batch_size=batch_size,
            callbacks=callbacks,
            class_weight=class_weight_dict,
            verbose=1
        )
        
        # Evaluate
        val_loss, val_acc = self.model.evaluate(X_val, y_val, verbose=0)
        logger.info(f"LSTM Validation Accuracy: {val_acc*100:.1f}%")
        
        return history, val_acc
    
    def predict(self, X: np.ndarray) -> Tuple[int, np.ndarray]:
        """Predict using LSTM model"""
        if self.model is None:
            return 0, np.array([0.33, 0.34, 0.33])
        
        X_seq = self.prepare_sequences(X)
        
        if len(X_seq) == 0:
            return 0, np.array([0.33, 0.34, 0.33])
        
        probs = self.model.predict(X_seq[-1:], verbose=0)[0]
        pred = np.argmax(probs) - 1  # Convert back: 0->-1, 1->0, 2->1
        
        return pred, probs
    
    def save(self, path: str):
        """Save model"""
        if self.model:
            self.model.save(path + '_lstm.keras')
            joblib.dump(self.scaler, path + '_scaler.pkl')
    
    def load(self, path: str):
        """Load model"""
        if HAS_TENSORFLOW and os.path.exists(path + '_lstm.keras'):
            self.model = load_model(path + '_lstm.keras')
            self.scaler = joblib.load(path + '_scaler.pkl')
            return True
        return False


class EnsemblePredictor:
    """
    Ensemble Model System
    Kết hợp GradientBoosting + XGBoost + RandomForest + LSTM
    Sử dụng weighted voting
    """
    
    def __init__(self):
        self.models = {}
        self.weights = {
            'gradient_boost': 0.3,
            'xgboost': 0.25,
            'random_forest': 0.2,
            'lstm': 0.25
        }
        self.scaler = RobustScaler()
        self.lstm_model = LSTMModel() if HAS_TENSORFLOW else None
    
    def train(self, X: np.ndarray, y: np.ndarray, symbol: str):
        """Train all models in ensemble"""
        logger.info(f"🧠 Training Ensemble for {symbol}...")
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Time-series split (no data leakage)
        split_idx = int(len(X_scaled) * 0.8)
        X_train = X_scaled[:split_idx]
        X_test = X_scaled[split_idx:]
        y_train = y[:split_idx]
        y_test = y[split_idx:]
        
        results = {}
        
        # 1. Gradient Boosting — anti-overfit V3 params
        logger.info("   Training GradientBoosting...")
        gb_model = GradientBoostingClassifier(
            n_estimators=400,
            max_depth=4,           # was 6 → shallower
            learning_rate=0.01,    # was 0.03 → slower/safer
            min_samples_split=20,
            min_samples_leaf=15,   # was 5 → stronger regularization
            subsample=0.75,
            max_features='sqrt',
            random_state=42
        )
        gb_model.fit(X_train, y_train)
        gb_acc = accuracy_score(y_test, gb_model.predict(X_test))
        self.models['gradient_boost'] = gb_model
        results['gradient_boost'] = gb_acc
        logger.info(f"   ✅ GradientBoosting: {gb_acc*100:.1f}%")
        
        # 2. XGBoost or RandomForest
        if HAS_XGBOOST:
            logger.info("   Training XGBoost...")
            xgb_model = XGBClassifier(
                n_estimators=400,
                max_depth=4,           # was 6 → shallower
                learning_rate=0.01,    # was 0.03 → safer
                subsample=0.75,
                colsample_bytree=0.8,
                min_child_weight=15,   # anti-overfit
                reg_alpha=0.1,
                reg_lambda=1.5,
                random_state=42,
                eval_metric='mlogloss'
            )
            # XGBoost needs labels 0, 1, 2
            y_train_xgb = y_train + 1
            y_test_xgb = y_test + 1
            xgb_model.fit(X_train, y_train_xgb)
            xgb_pred = xgb_model.predict(X_test) - 1
            xgb_acc = accuracy_score(y_test, xgb_pred)
            self.models['xgboost'] = xgb_model
            results['xgboost'] = xgb_acc
            logger.info(f"   ✅ XGBoost: {xgb_acc*100:.1f}%")
        else:
            logger.info("   Training RandomForest (XGBoost not available)...")
            rf_model = RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                min_samples_split=10,
                random_state=42
            )
            rf_model.fit(X_train, y_train)
            rf_acc = accuracy_score(y_test, rf_model.predict(X_test))
            self.models['random_forest'] = rf_model
            results['random_forest'] = rf_acc
            self.weights['random_forest'] = self.weights.pop('xgboost', 0.25)
            logger.info(f"   ✅ RandomForest: {rf_acc*100:.1f}%")
        
        # 3. Additional RandomForest
        logger.info("   Training RandomForest...")
        rf_model2 = RandomForestClassifier(
            n_estimators=150,
            max_depth=8,
            min_samples_split=5,
            random_state=123
        )
        rf_model2.fit(X_train, y_train)
        rf2_acc = accuracy_score(y_test, rf_model2.predict(X_test))
        self.models['random_forest_2'] = rf_model2
        results['random_forest_2'] = rf2_acc
        logger.info(f"   ✅ RandomForest 2: {rf2_acc*100:.1f}%")
        
        # 4. LSTM (if available)
        if HAS_TENSORFLOW and self.lstm_model:
            logger.info("   Training LSTM Deep Learning...")
            try:
                _, lstm_acc = self.lstm_model.train(X, y, epochs=20, batch_size=32)
                results['lstm'] = lstm_acc
                logger.info(f"   ✅ LSTM: {lstm_acc*100:.1f}%")
            except Exception as e:
                logger.warning(f"   ⚠️ LSTM training failed: {e}")
                results['lstm'] = 0.5
        
        # Calculate ensemble accuracy (X_test is already scaled)
        ensemble_preds = self.predict_batch(X_test, already_scaled=True)
        ensemble_acc = accuracy_score(y_test, ensemble_preds)
        results['ensemble'] = ensemble_acc
        
        logger.info(f"\n🎯 ENSEMBLE ACCURACY: {ensemble_acc*100:.1f}%")
        
        return results
    
    def predict(self, X: np.ndarray) -> Tuple[int, float, Dict]:
        """Predict using ensemble with weighted voting"""
        X_scaled = self.scaler.transform(X.reshape(1, -1))
        
        votes = {}
        probabilities = {}
        
        # Get predictions from each model
        for name, model in self.models.items():
            if name == 'xgboost' and HAS_XGBOOST:
                pred = model.predict(X_scaled)[0] - 1
                probs = model.predict_proba(X_scaled)[0]
            else:
                pred = model.predict(X_scaled)[0]
                probs = model.predict_proba(X_scaled)[0]
            
            weight = self.weights.get(name, 0.2)
            votes[name] = {'pred': pred, 'weight': weight, 'probs': probs}
        
        # LSTM prediction
        if HAS_TENSORFLOW and self.lstm_model and self.lstm_model.model:
            try:
                lstm_pred, lstm_probs = self.lstm_model.predict(X_scaled)
                votes['lstm'] = {'pred': lstm_pred, 'weight': self.weights.get('lstm', 0.25), 'probs': lstm_probs}
            except:
                pass
        
        # Weighted voting
        weighted_scores = {-1: 0, 0: 0, 1: 0}
        agreement_count = {-1: 0, 0: 0, 1: 0}
        for name, vote in votes.items():
            weighted_scores[vote['pred']] += vote['weight']
            agreement_count[vote['pred']] += 1
        
        # Get final prediction
        final_pred = max(weighted_scores, key=weighted_scores.get)
        confidence = weighted_scores[final_pred] / sum(self.weights.values())

        # Penalize if fewer than half the models agree
        n_models = len(votes)
        if n_models >= 3 and agreement_count[final_pred] < n_models / 2:
            confidence *= 0.7  # 30% penalty for low agreement
        
        return final_pred, confidence * 100, votes
    
    def predict_batch(self, X: np.ndarray, already_scaled: bool = False) -> np.ndarray:
        """Batch prediction for already scaled data"""
        predictions = []
        
        for i in range(len(X)):
            X_sample = X[i].reshape(1, -1)
            
            # Skip scaling if already scaled
            if not already_scaled:
                X_sample = self.scaler.transform(X_sample)
            
            votes_scores = {-1: 0, 0: 0, 1: 0}
            
            # Get predictions from each model
            for name, model in self.models.items():
                if name == 'xgboost' and HAS_XGBOOST:
                    pred = int(model.predict(X_sample)[0] - 1)
                else:
                    pred = int(model.predict(X_sample)[0])
                
                weight = self.weights.get(name, 0.2)
                votes_scores[pred] += weight
            
            # LSTM prediction
            if HAS_TENSORFLOW and self.lstm_model and self.lstm_model.model:
                try:
                    lstm_pred, _ = self.lstm_model.predict(X_sample)
                    votes_scores[lstm_pred] += self.weights.get('lstm', 0.25)
                except:
                    pass
            
            # Final prediction
            final_pred = max(votes_scores, key=votes_scores.get)
            predictions.append(final_pred)
        
        return np.array(predictions)
    
    def save(self, path: str):
        """Save ensemble models"""
        joblib.dump({
            'models': self.models,
            'weights': self.weights,
            'scaler': self.scaler
        }, path + '_ensemble.pkl')
        
        if self.lstm_model:
            self.lstm_model.save(path)
    
    def load(self, path: str) -> bool:
        """Load ensemble models"""
        if os.path.exists(path + '_ensemble.pkl'):
            data = joblib.load(path + '_ensemble.pkl')
            self.models = data['models']
            self.weights = data['weights']
            self.scaler = data['scaler']
            
            if self.lstm_model:
                self.lstm_model.load(path)
            
            return True
        return False


class AdvancedAIEngine:
    """
    Main Advanced AI Engine
    Tích hợp tất cả các components
    """
    
    def __init__(self, client, analyzer):
        self.client = client
        self.analyzer = analyzer
        self.pattern_detector = AdvancedCandlestickPatterns()
        self.mtf_analyzer = MultiTimeframeAnalyzer(client, analyzer)
        self.ensembles = {}  # One ensemble per symbol
        
    def prepare_advanced_features(
        self, symbol: str
    ) -> Tuple[np.ndarray, pd.DataFrame]:
        """Prepare features for prediction - MUST MATCH
        train_symbol features"""
        # Get 5m data with patterns - same as training
        klines = self.client.get_klines(symbol, '5m', 200)
        df = self.analyzer.prepare_dataframe(klines)
        df = self.analyzer.add_basic_indicators(df)
        df = self.analyzer.add_advanced_indicators(df)

        # Add candlestick patterns - same as training
        df = self.pattern_detector.detect_all_patterns(df)

        # Add multi-TF features (must match training)
        try:
            for htf_tf, prefix in [('1h', 'htf_1h'),
                                   ('4h', 'htf_4h')]:
                htf_klines = self.client.get_klines(
                    symbol, htf_tf, 100
                )
                htf = self.analyzer.prepare_dataframe(
                    htf_klines
                )
                htf = self.analyzer.add_basic_indicators(htf)
                htf = htf[['timestamp', 'close', 'rsi',
                           'macd', 'adx']].copy()
                htf.columns = [
                    'timestamp',
                    f'{prefix}_close',
                    f'{prefix}_rsi',
                    f'{prefix}_macd',
                    f'{prefix}_adx'
                ]
                htf['timestamp'] = pd.to_datetime(
                    htf['timestamp'], unit='ms'
                )
                df['timestamp_dt'] = pd.to_datetime(
                    df['timestamp'], unit='ms'
                )
                df = pd.merge_asof(
                    df.sort_values('timestamp_dt'),
                    htf.sort_values('timestamp'),
                    left_on='timestamp_dt',
                    right_on='timestamp',
                    direction='backward',
                    suffixes=('', f'_{prefix}')
                )
                df.drop(columns=[
                    'timestamp_dt',
                    f'timestamp_{prefix}'
                ], errors='ignore', inplace=True)
        except Exception as e:
            logger.warning(
                f"HTF features skipped in predict: {e}"
            )

        # Handle NaN values
        df = df.ffill().fillna(0)

        # Select features - SAME exclusion as train_symbol()
        excl = [
            'open', 'high', 'low', 'close', 'volume',
            'timestamp', 'close_time',
            'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume',
            'taker_buy_quote_asset_volume',
            'ignore', 'is_bullish', 'body',
            'upper_shadow', 'lower_shadow',
            'body_pct', 'future_return', 'label'
        ]
        feature_cols = [
            col for col in df.columns if col not in excl
        ]

        X = df[feature_cols].values

        return X, df
    
    def _calc_realtime_momentum(self, symbol: str) -> Dict:
        """
        📈 Calculate real-time price momentum across multiple
        timeframes to detect strong directional moves.
        Returns momentum dict with scores and direction.
        """
        result = {
            'direction': 0,     # +1 = bullish, -1 = bearish
            'strength': 0.0,    # 0-100 strength score
            'short_pct': 0.0,   # % change last 3 candles (5m)
            'medium_pct': 0.0,  # % change last 12 candles (1h)
            'long_pct': 0.0,    # % change last 4h
            'consecutive_green': 0,
            'consecutive_red': 0,
            'ema_distance_pct': 0.0,  # price vs EMA20
            'rsi': 50.0,
            'candle_body_ratio': 0.0,
            'volume_surge': False,
        }
        try:
            # --- 5m candles for short-term momentum ---
            klines_5m = self.client.get_klines(
                symbol, '5m', 60
            )
            if not klines_5m or len(klines_5m) < 30:
                return result

            df5 = self.analyzer.prepare_dataframe(klines_5m)
            df5 = self.analyzer.add_basic_indicators(df5)
            closes = df5['close'].values.astype(float)
            opens = df5['open'].values.astype(float)
            highs = df5['high'].values.astype(float)
            lows = df5['low'].values.astype(float)
            vols = df5['volume'].values.astype(float)
            price = closes[-1]

            # Short-term: last 3 candles (~15 min)
            if len(closes) >= 4:
                result['short_pct'] = (
                    (price - closes[-4]) / closes[-4]
                ) * 100
            # Medium-term: last 12 candles (~1 hour)
            if len(closes) >= 13:
                result['medium_pct'] = (
                    (price - closes[-13]) / closes[-13]
                ) * 100
            # Long-term: last 48 candles (~4 hours)
            if len(closes) >= 49:
                result['long_pct'] = (
                    (price - closes[-49]) / closes[-49]
                ) * 100

            # Consecutive green / red candles
            consec_green = 0
            consec_red = 0
            for i in range(len(closes) - 1, max(0, len(closes) - 16), -1):
                if closes[i] > opens[i]:
                    if consec_red == 0:
                        consec_green += 1
                    else:
                        break
                elif closes[i] < opens[i]:
                    if consec_green == 0:
                        consec_red += 1
                    else:
                        break
                else:
                    break
            result['consecutive_green'] = consec_green
            result['consecutive_red'] = consec_red

            # EMA distance: how far is price from EMA20
            if 'sma_20' in df5.columns:
                ema20 = float(df5['sma_20'].iloc[-1])
                if ema20 > 0:
                    result['ema_distance_pct'] = (
                        (price - ema20) / ema20
                    ) * 100

            # RSI
            if 'rsi' in df5.columns:
                result['rsi'] = float(df5['rsi'].iloc[-1])

            # Recent candle body ratio (big bodies = strong move)
            recent_bodies = []
            for i in range(-1, max(-7, -len(closes)), -1):
                body = abs(closes[i] - opens[i])
                rng = highs[i] - lows[i]
                if rng > 0:
                    recent_bodies.append(body / rng)
            result['candle_body_ratio'] = (
                sum(recent_bodies) / len(recent_bodies)
                if recent_bodies else 0
            )

            # Volume surge: current vs 20-period avg
            if len(vols) >= 21:
                vol_avg = float(np.mean(vols[-21:-1]))
                if vol_avg > 0 and vols[-1] > vol_avg * 1.5:
                    result['volume_surge'] = True

            # --- 15m candles for higher TF confirmation ---
            try:
                klines_15m = self.client.get_klines(
                    symbol, '15m', 30
                )
                if klines_15m and len(klines_15m) >= 10:
                    df15 = self.analyzer.prepare_dataframe(
                        klines_15m
                    )
                    c15 = df15['close'].values.astype(float)
                    # 15m 4-candle change (~1h)
                    pct_15m = (
                        (c15[-1] - c15[-5]) / c15[-5]
                    ) * 100 if len(c15) >= 5 else 0
                else:
                    pct_15m = 0
            except Exception:
                pct_15m = 0

            # --- 1h candles for macro trend ---
            try:
                klines_1h = self.client.get_klines(
                    symbol, '1h', 24
                )
                if klines_1h and len(klines_1h) >= 6:
                    df1h = self.analyzer.prepare_dataframe(
                        klines_1h
                    )
                    c1h = df1h['close'].values.astype(float)
                    pct_1h = (
                        (c1h[-1] - c1h[-6]) / c1h[-6]
                    ) * 100 if len(c1h) >= 6 else 0
                else:
                    pct_1h = 0
            except Exception:
                pct_1h = 0

            # === Calculate aggregate direction & strength ===
            # Direction scoring: weighted sum
            dir_score = 0.0
            # Short-term (highest weight)
            dir_score += np.sign(result['short_pct']) * min(
                abs(result['short_pct']) * 8, 30
            )
            # Medium-term
            dir_score += np.sign(result['medium_pct']) * min(
                abs(result['medium_pct']) * 5, 25
            )
            # 15m confirmation
            dir_score += np.sign(pct_15m) * min(
                abs(pct_15m) * 4, 20
            )
            # 1h macro
            dir_score += np.sign(pct_1h) * min(
                abs(pct_1h) * 3, 15
            )
            # Consecutive candles bonus
            dir_score += consec_green * 3
            dir_score -= consec_red * 3
            # EMA distance bonus
            dir_score += np.sign(
                result['ema_distance_pct']
            ) * min(abs(result['ema_distance_pct']) * 5, 10)

            result['direction'] = (
                1 if dir_score > 0 else (-1 if dir_score < 0 else 0)
            )
            result['strength'] = min(abs(dir_score), 100)

            logger.info(
                f"   📊 Momentum {symbol}: "
                f"dir={'BULL' if result['direction'] > 0 else 'BEAR' if result['direction'] < 0 else 'FLAT'} "
                f"str={result['strength']:.0f} "
                f"short={result['short_pct']:+.2f}% "
                f"med={result['medium_pct']:+.2f}% "
                f"15m={pct_15m:+.2f}% "
                f"1h={pct_1h:+.2f}% "
                f"consec_G={consec_green} R={consec_red} "
                f"RSI={result['rsi']:.0f}"
            )
        except Exception as e:
            logger.warning(
                f"Momentum calc error {symbol}: {e}"
            )
        return result

    def get_signal(self, symbol: str) -> Dict:
        """Get trading signal with advanced analysis
        + real-time momentum sanity check"""
        try:
            # Load or check ensemble
            if symbol not in self.ensembles:
                self.ensembles[symbol] = EnsemblePredictor()
                model_path = f'models/advanced_{symbol}'
                if not self.ensembles[symbol].load(model_path):
                    logger.warning(
                        f"No trained ensemble for {symbol}"
                    )
                    return self._get_fallback_signal(symbol)

            # Get features
            X, df = self.prepare_advanced_features(symbol)

            # Get ensemble prediction
            pred, confidence, votes = (
                self.ensembles[symbol].predict(X[-1])
            )

            # Get pattern signal
            pattern_score = df['pattern_score'].iloc[-1]
            pattern_signal = df['pattern_signal'].iloc[-1]

            # Get MTF alignment
            trend_alignment = (
                df['trend_alignment'].iloc[-1]
                if 'trend_alignment' in df.columns else 0
            )

            # Map prediction
            signal_map = {-1: 'SHORT', 0: 'HOLD', 1: 'LONG'}
            signal = signal_map[pred]

            # =============================================
            # 🚨 REAL-TIME MOMENTUM SANITY CHECK
            # Prevent counter-trend trades when price is
            # strongly moving in one direction.
            # =============================================
            momentum = self._calc_realtime_momentum(symbol)
            mom_dir = momentum['direction']
            mom_str = momentum['strength']
            rsi = momentum['rsi']
            short_pct = momentum['short_pct']
            med_pct = momentum['medium_pct']
            consec_g = momentum['consecutive_green']
            consec_r = momentum['consecutive_red']

            original_signal = signal
            original_conf = confidence

            # --- Rule 1: Block counter-trend when momentum
            #     is moderate+ (strength >= 25) ---
            if mom_str >= 25:
                if signal == 'SHORT' and mom_dir > 0:
                    logger.warning(
                        f"   🚫 BLOCKED SHORT {symbol}: "
                        f"strong bullish momentum "
                        f"(str={mom_str:.0f}, "
                        f"short={short_pct:+.2f}%, "
                        f"med={med_pct:+.2f}%)"
                    )
                    signal = 'HOLD'
                    confidence = 0
                elif signal == 'LONG' and mom_dir < 0:
                    logger.warning(
                        f"   🚫 BLOCKED LONG {symbol}: "
                        f"strong bearish momentum "
                        f"(str={mom_str:.0f}, "
                        f"short={short_pct:+.2f}%, "
                        f"med={med_pct:+.2f}%)"
                    )
                    signal = 'HOLD'
                    confidence = 0

            # --- Rule 2: Block SHORT if 4+ consecutive
            #     green candles AND price rising > 0.3% ---
            if (signal == 'SHORT'
                    and consec_g >= 4
                    and short_pct > 0.3):
                logger.warning(
                    f"   🚫 BLOCKED SHORT {symbol}: "
                    f"{consec_g} consecutive green candles, "
                    f"price +{short_pct:.2f}%"
                )
                signal = 'HOLD'
                confidence = 0

            # --- Rule 3: Block LONG if 4+ consecutive
            #     red candles AND price falling > 0.3% ---
            if (signal == 'LONG'
                    and consec_r >= 4
                    and short_pct < -0.3):
                logger.warning(
                    f"   🚫 BLOCKED LONG {symbol}: "
                    f"{consec_r} consecutive red candles, "
                    f"price {short_pct:.2f}%"
                )
                signal = 'HOLD'
                confidence = 0

            # --- Rule 4: RSI extreme guard ---
            # Don't SHORT when RSI is already very high
            # (overbought can stay overbought in strong trends)
            # Don't LONG when RSI is extremely low and dropping
            if signal == 'SHORT' and rsi > 75 and mom_dir > 0:
                logger.warning(
                    f"   🚫 BLOCKED SHORT {symbol}: "
                    f"RSI={rsi:.0f} overbought but "
                    f"bullish momentum continues"
                )
                signal = 'HOLD'
                confidence = 0
            if signal == 'LONG' and rsi < 25 and mom_dir < 0:
                logger.warning(
                    f"   🚫 BLOCKED LONG {symbol}: "
                    f"RSI={rsi:.0f} oversold but "
                    f"bearish momentum continues"
                )
                signal = 'HOLD'
                confidence = 0

            # --- Rule 5: Momentum-aligned confidence boost ---
            # If signal aligns with momentum, boost confidence
            if signal != 'HOLD' and mom_str >= 20:
                if ((signal == 'LONG' and mom_dir > 0)
                        or (signal == 'SHORT' and mom_dir < 0)):
                    boost = min(mom_str * 0.15, 12)
                    confidence = min(100, confidence + boost)
                    logger.info(
                        f"   ✅ Momentum confirms {signal}: "
                        f"confidence +{boost:.1f}%"
                    )

            # --- Rule 6: Flip signal to MOMENTUM direction
            #     if momentum is VERY strong (>= 65) and
            #     model gave weak opposite or HOLD ---
            if (signal == 'HOLD'
                    and mom_str >= 65
                    and original_conf < 60):
                if mom_dir > 0 and rsi < 72:
                    signal = 'LONG'
                    confidence = min(
                        mom_str * 0.7, 75
                    )
                    logger.info(
                        f"   🔄 Momentum override → LONG "
                        f"{symbol} (str={mom_str:.0f})"
                    )
                elif mom_dir < 0 and rsi > 28:
                    signal = 'SHORT'
                    confidence = min(
                        mom_str * 0.7, 75
                    )
                    logger.info(
                        f"   🔄 Momentum override → SHORT "
                        f"{symbol} (str={mom_str:.0f})"
                    )

            if signal != original_signal:
                logger.info(
                    f"   📊 Signal changed: "
                    f"{original_signal}→{signal} "
                    f"(momentum filter)"
                )

            # Calculate entry, SL, TP
            price = float(df['close'].iloc[-1])

            if signal == 'LONG':
                sl = price * 0.985
                tp = price * 1.03
            elif signal == 'SHORT':
                sl = price * 1.015
                tp = price * 0.97
            else:
                sl = None
                tp = None

            return {
                'symbol': symbol,
                'signal': signal,
                'confidence': confidence,
                'price': price,
                'stop_loss': sl,
                'take_profit': tp,
                'pattern_score': pattern_score,
                'pattern_signal': pattern_signal,
                'trend_alignment': trend_alignment,
                'model_votes': votes,
                'momentum': momentum,
                'timestamp': datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S'
                ),
            }

        except Exception as e:
            logger.error(
                f"Error getting signal for {symbol}: {e}"
            )
            return self._get_fallback_signal(symbol)
    
    def _get_fallback_signal(self, symbol: str) -> Dict:
        """Fallback to basic analysis if advanced fails"""
        try:
            klines = self.client.get_klines(symbol, '5m', 100)
            df = self.analyzer.prepare_dataframe(klines)
            price = float(df['close'].iloc[-1])
            
            return {
                'symbol': symbol,
                'signal': 'HOLD',
                'confidence': 50.0,
                'price': price,
                'stop_loss': None,
                'take_profit': None,
                'error': 'Using fallback analysis'
            }
        except:
            return {'symbol': symbol, 'signal': 'HOLD', 'confidence': 0}
    
    def train_symbol(self, symbol: str, days: int = 30) -> Dict:
        """Train advanced AI for a symbol — V2 with extended data"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 TRAINING ADVANCED AI V2 FOR {symbol}")
        logger.info(f"{'='*60}")

        # Get extended training data (paginated)
        from train_ai_improved import get_extended_klines
        total_candles = min(days * 288, 8640)  # up to 30 days
        klines = get_extended_klines(
            self.client, symbol, '5m', total_candles
        )
        if not klines or len(klines) < 500:
            logger.error(f"Insufficient data for {symbol}")
            return {}

        df = self.analyzer.prepare_dataframe(klines)
        df = self.analyzer.add_basic_indicators(df)
        df = self.analyzer.add_advanced_indicators(df)

        # Add candlestick patterns
        df = self.pattern_detector.detect_all_patterns(df)

        # Add multi-TF features (1h + 4h context)
        try:
            for htf_tf, prefix in [('1h', 'htf_1h'),
                                   ('4h', 'htf_4h')]:
                htf_klines = self.client.get_klines(
                    symbol, htf_tf, 500
                )
                htf = self.analyzer.prepare_dataframe(htf_klines)
                htf = self.analyzer.add_basic_indicators(htf)
                htf = htf[['timestamp', 'close', 'rsi',
                           'macd', 'adx']].copy()
                htf.columns = ['timestamp',
                               f'{prefix}_close',
                               f'{prefix}_rsi',
                               f'{prefix}_macd',
                               f'{prefix}_adx']
                htf['timestamp'] = pd.to_datetime(
                    htf['timestamp'], unit='ms'
                )
                df['timestamp_dt'] = pd.to_datetime(
                    df['timestamp'], unit='ms'
                )
                df = pd.merge_asof(
                    df.sort_values('timestamp_dt'),
                    htf.sort_values('timestamp'),
                    left_on='timestamp_dt',
                    right_on='timestamp',
                    direction='backward',
                    suffixes=('', f'_{prefix}')
                )
                df.drop(columns=[
                    'timestamp_dt',
                    f'timestamp_{prefix}'
                ], errors='ignore', inplace=True)
            logger.info("  Added multi-TF features (1h + 4h)")
        except Exception as e:
            logger.warning(f"  HTF features skipped: {e}")

        # Create labels — stricter: 1.2% threshold, 2.0x ratio
        df['future_return'] = (
            df['close'].shift(-15) / df['close'] - 1
        )
        # Use both future return AND gain/loss asymmetry
        future_bars = 15
        labels = []
        closes = df['close'].values
        for i in range(len(closes) - future_bars):
            fp = closes[i+1:i+future_bars+1]
            gain = (fp.max() - closes[i]) / closes[i]
            loss = (closes[i] - fp.min()) / closes[i]
            if gain > 0.012 and gain > loss * 2.0:
                labels.append(1)
            elif loss > 0.012 and loss > gain * 2.0:
                labels.append(-1)
            else:
                labels.append(0)
        labels.extend([0] * future_bars)
        df['label'] = labels

        # Remove NaN
        df = df.dropna()

        # Select features - same exclusion as predict
        excl = [
            'open', 'high', 'low', 'close', 'volume',
            'timestamp', 'close_time',
            'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume',
            'taker_buy_quote_asset_volume',
            'ignore', 'is_bullish', 'body',
            'upper_shadow', 'lower_shadow',
            'body_pct', 'future_return', 'label'
        ]
        feature_cols = [
            c for c in df.columns if c not in excl
        ]

        X = df[feature_cols].values
        y = df['label'].values

        logger.info(
            f"Training: {len(X)} samples, "
            f"{len(feature_cols)} features"
        )
        logger.info(
            f"Labels: LONG={sum(y == 1)}, "
            f"HOLD={sum(y == 0)}, "
            f"SHORT={sum(y == -1)}"
        )
        
        # Train ensemble
        ensemble = EnsemblePredictor()
        results = ensemble.train(X, y, symbol)
        
        # Save
        model_path = f'models/advanced_{symbol}'
        ensemble.save(model_path)
        self.ensembles[symbol] = ensemble
        
        logger.info(f"\n✅ Training completed for {symbol}")
        
        return results


# Test function
if __name__ == "__main__":
    from binance_client import BinanceFuturesClient
    from technical_analysis import TechnicalAnalyzer
    
    client = BinanceFuturesClient()
    analyzer = TechnicalAnalyzer()
    
    engine = AdvancedAIEngine(client, analyzer)
    
    # Train for all symbols
    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        results = engine.train_symbol(symbol)
        print(f"\n{symbol} Results: {results}")
