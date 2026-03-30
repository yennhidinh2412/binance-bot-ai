"""
Advanced Technical Analysis Engine
Phân tích kỹ thuật chuyên nghiệp cho trading bot
"""

import pandas as pd
import numpy as np
# import talib  # Not available, using 'ta' library instead
try:
    import pandas_ta as pta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
from ta import trend, momentum, volatility, volume as ta_volume
from typing import Dict, List, Tuple, Optional, Any
from loguru import logger
from config import Config

class TechnicalAnalyzer:
    """Engine phân tích kỹ thuật cao cấp"""
    
    def __init__(self):
        self.config = Config.get_config()
        self.lookback_periods = self.config["ai_config"]["lookback_periods"]
        logger.info("Technical Analyzer initialized")
    
    def prepare_dataframe(self, klines_data: List[List]) -> pd.DataFrame:
        """Chuyển đổi dữ liệu klines thành DataFrame"""
        try:
            df = pd.DataFrame(klines_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Chuyển đổi kiểu dữ liệu
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Sắp xếp theo thời gian
            df.sort_index(inplace=True)
            
            logger.debug(f"DataFrame prepared with {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error preparing DataFrame: {e}")
            raise
    
    def add_basic_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Thêm các chỉ báo kỹ thuật cơ bản"""
        try:
            # Moving Averages using ta library
            df['sma_20'] = trend.sma_indicator(df['close'], window=20)
            df['sma_50'] = trend.sma_indicator(df['close'], window=50)
            df['sma_200'] = trend.sma_indicator(df['close'], window=200)
            
            df['ema_9'] = trend.ema_indicator(df['close'], window=9)
            df['ema_12'] = trend.ema_indicator(df['close'], window=12)
            df['ema_21'] = trend.ema_indicator(df['close'], window=21)
            df['ema_26'] = trend.ema_indicator(df['close'], window=26)
            df['ema_50'] = trend.ema_indicator(df['close'], window=50)
            df['ema_200'] = trend.ema_indicator(df['close'], window=200)
            
            # RSI
            df['rsi'] = momentum.rsi(df['close'], window=14)
            df['rsi_6'] = momentum.rsi(df['close'], window=6)
            df['rsi_21'] = momentum.rsi(df['close'], window=21)
            
            # MACD
            macd_indicator = trend.MACD(df['close'])
            df['macd'] = macd_indicator.macd()
            df['macd_signal'] = macd_indicator.macd_signal()
            df['macd_histogram'] = macd_indicator.macd_diff()
            
            # Bollinger Bands
            bb_indicator = volatility.BollingerBands(df['close'])
            df['bb_upper'] = bb_indicator.bollinger_hband()
            df['bb_middle'] = bb_indicator.bollinger_mavg()
            df['bb_lower'] = bb_indicator.bollinger_lband()
            df['bb_width'] = bb_indicator.bollinger_wband()
            df['bb_percent'] = bb_indicator.bollinger_pband()
            
            # Stochastic
            stoch_indicator = momentum.StochasticOscillator(
                df['high'], df['low'], df['close']
            )
            df['stoch_k'] = stoch_indicator.stoch()
            df['stoch_d'] = stoch_indicator.stoch_signal()
            
            # Williams %R
            df['williams_r'] = momentum.williams_r(
                df['high'], df['low'], df['close']
            )
            
            # ADX (Average Directional Index)
            adx_indicator = trend.ADXIndicator(df['high'], df['low'], df['close'])
            df['adx'] = adx_indicator.adx()
            df['plus_di'] = adx_indicator.adx_pos()
            df['minus_di'] = adx_indicator.adx_neg()
            
            # CCI (Commodity Channel Index)
            df['cci'] = trend.cci(df['high'], df['low'], df['close'])
            
            # MFI (Money Flow Index)
            df['mfi'] = ta_volume.money_flow_index(
                df['high'], df['low'], df['close'], df['volume']
            )
            
            # ATR (Average True Range)
            df['atr'] = volatility.average_true_range(
                df['high'], df['low'], df['close']
            )
            
            logger.debug("Basic indicators added successfully")
            return df
        except Exception as e:
            logger.error(f"Error adding basic indicators: {e}")
            raise
    
    def add_advanced_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Thêm các chỉ báo kỹ thuật nâng cao"""
        try:
            # TODO: These require TA-Lib - will add after installation
            # For now, using simplified versions with 'ta' library
            
            # Aroon
            aroon_indicator = trend.AroonIndicator(df['high'], df['low'])
            df['aroon_up'] = aroon_indicator.aroon_up()
            df['aroon_down'] = aroon_indicator.aroon_down()
            df['aroon_osc'] = df['aroon_up'] - df['aroon_down']
            
            # OBV (On Balance Volume)
            df['obv'] = ta_volume.on_balance_volume(df['close'], df['volume'])
            
            # TRIX
            df['trix'] = trend.trix(df['close'])
            
            # Commodity Channel Index với nhiều timeframe  
            df['cci_14'] = trend.cci(df['high'], df['low'], df['close'], window=14)
            df['cci_20'] = trend.cci(df['high'], df['low'], df['close'], window=20)
            
            # ROC (Rate of Change)
            df['roc'] = momentum.roc(df['close'])
            
            # Volume indicators
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # Parabolic SAR - simplified
            df['sar'] = trend.psar_up(df['high'], df['low'], df['close']).fillna(
                trend.psar_down(df['high'], df['low'], df['close'])
            )
            
            logger.debug("Advanced indicators added successfully")
            return df
        except Exception as e:
            logger.error(f"Error adding advanced indicators: {e}")
            raise
    
    def detect_candlestick_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Phát hiện các mô hình nến - FULL 12 patterns"""
        try:
            body = abs(df['close'] - df['open'])
            range_hl = df['high'] - df['low'] + 0.0001
            lower_shadow = (
                df[['open', 'close']].min(axis=1) - df['low']
            )
            upper_shadow = (
                df['high'] - df[['open', 'close']].max(axis=1)
            )
            is_bullish = (df['close'] > df['open'])
            is_bearish = (df['close'] < df['open'])
            body_pct = body / range_hl

            # Shifted helpers (filled False to avoid NaN)
            is_bull_1 = is_bullish.shift(1).fillna(False)
            is_bear_1 = is_bearish.shift(1).fillna(False)
            is_bull_2 = is_bullish.shift(2).fillna(False)
            is_bear_2 = is_bearish.shift(2).fillna(False)

            # 1. Doji
            df['doji'] = (body_pct < 0.1).astype(int) * 100

            # 2. Hammer (bullish reversal)
            df['hammer'] = (
                (lower_shadow > 2 * body)
                & (upper_shadow < body * 0.5)
                & (body_pct > 0.1)
            ).astype(int) * 100

            # 3. Hanging Man (bearish)
            df['hanging_man'] = (
                (lower_shadow > 2 * body)
                & (upper_shadow < body * 0.3)
                & is_bearish
            ).astype(int) * -100

            # 4. Shooting Star (bearish reversal)
            df['shooting_star'] = (
                (upper_shadow > 2 * body)
                & (lower_shadow < body * 0.3)
                & is_bearish
            ).astype(int) * -100

            # 5. Bullish Engulfing
            df['engulfing'] = (
                (is_bear_1 & is_bullish)
                & (df['open'] <= df['close'].shift(1))
                & (df['close'] >= df['open'].shift(1))
            ).astype(int) * 100

            # Also detect bearish engulfing → negative
            bear_engulf = (
                (is_bull_1 & is_bearish)
                & (df['open'] >= df['close'].shift(1))
                & (df['close'] <= df['open'].shift(1))
            ).astype(int) * -100
            df['engulfing'] = df['engulfing'] + bear_engulf

            # 6. Morning Star (3-candle bullish)
            df['morning_star'] = (
                (df['close'].shift(2) < df['open'].shift(2))
                & (body.shift(1) < body.shift(2) * 0.3)
                & is_bullish
                & (df['close'] > (
                    df['open'].shift(2) + df['close'].shift(2)
                ) / 2)
            ).astype(int) * 100

            # 7. Evening Star (3-candle bearish)
            df['evening_star'] = (
                is_bull_2
                & (body.shift(1) < body.shift(2) * 0.3)
                & is_bearish
                & (df['close'] < (
                    df['open'].shift(2) + df['close'].shift(2)
                ) / 2)
            ).astype(int) * -100

            # 8. Piercing Line (bullish)
            df['piercing'] = (
                is_bear_1 & is_bullish
                & (df['open'] < df['low'].shift(1))
                & (df['close'] > (
                    df['open'].shift(1) + df['close'].shift(1)
                ) / 2)
                & (df['close'] < df['open'].shift(1))
            ).astype(int) * 100

            # 9. Dark Cloud Cover (bearish)
            df['dark_cloud'] = (
                is_bull_1 & is_bearish
                & (df['open'] > df['high'].shift(1))
                & (df['close'] < (
                    df['open'].shift(1) + df['close'].shift(1)
                ) / 2)
            ).astype(int) * -100

            # 10. Three White Soldiers (strong bullish)
            df['three_white_soldiers'] = (
                is_bullish & is_bull_1 & is_bull_2
                & (df['close'] > df['close'].shift(1))
                & (df['close'].shift(1) > df['close'].shift(2))
            ).astype(int) * 100

            # 11. Three Black Crows (strong bearish)
            df['three_black_crows'] = (
                is_bearish & is_bear_1 & is_bear_2
                & (df['close'] < df['close'].shift(1))
                & (df['close'].shift(1) < df['close'].shift(2))
            ).astype(int) * -100

            # 12. Spinning Top (indecision)
            df['spinning_top'] = (
                (body_pct < 0.3) & (body_pct > 0.1)
                & (upper_shadow > body)
                & (lower_shadow > body)
            ).astype(int) * 30

            # 13. Harami (reversal)
            df['harami'] = (
                is_bear_1 & is_bullish
                & (body < body.shift(1))
                & (df['high'] < df['open'].shift(1))
                & (df['low'] > df['close'].shift(1))
            ).astype(int) * 80
            bear_harami = (
                is_bull_1 & is_bearish
                & (body < body.shift(1))
                & (df['high'] < df['close'].shift(1))
                & (df['low'] > df['open'].shift(1))
            ).astype(int) * -80
            df['harami'] = df['harami'] + bear_harami

            logger.debug("Candlestick patterns detected (12 real)")
            return df
        except Exception as e:
            logger.error(
                f"Error detecting candlestick patterns: {e}"
            )
            raise
    
    def identify_support_resistance(self, df: pd.DataFrame, window: int = 20) -> Dict[str, List[float]]:
        """Xác định các mức hỗ trợ và kháng cự"""
        try:
            highs = df['high'].rolling(window=window, center=True).max()
            lows = df['low'].rolling(window=window, center=True).min()
            
            # Tìm các điểm cực đại và cực tiểu cục bộ
            resistance_levels = []
            support_levels = []
            
            for i in range(window, len(df) - window):
                if df['high'].iloc[i] == highs.iloc[i]:
                    resistance_levels.append(df['high'].iloc[i])
                
                if df['low'].iloc[i] == lows.iloc[i]:
                    support_levels.append(df['low'].iloc[i])
            
            # Nhóm các mức gần nhau
            resistance_levels = self._cluster_levels(resistance_levels)
            support_levels = self._cluster_levels(support_levels)
            
            logger.debug(f"Found {len(resistance_levels)} resistance and {len(support_levels)} support levels")
            
            return {
                'resistance': resistance_levels,
                'support': support_levels
            }
        except Exception as e:
            logger.error(f"Error identifying support/resistance: {e}")
            raise
    
    def _cluster_levels(self, levels: List[float], threshold: float = 0.005) -> List[float]:
        """Nhóm các mức giá gần nhau"""
        if not levels:
            return []
        
        clustered = []
        sorted_levels = sorted(levels)
        current_cluster = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            if abs(level - current_cluster[-1]) / current_cluster[-1] <= threshold:
                current_cluster.append(level)
            else:
                clustered.append(np.mean(current_cluster))
                current_cluster = [level]
        
        clustered.append(np.mean(current_cluster))
        return clustered
    
    def calculate_trend_strength(self, df: pd.DataFrame) -> Dict[str, float]:
        """Tính toán độ mạnh của xu hướng"""
        try:
            # ADX trend strength
            adx_value = df['adx'].iloc[-1] if not pd.isna(df['adx'].iloc[-1]) else 0
            
            # EMA trend
            ema_12 = df['ema_12'].iloc[-1]
            ema_26 = df['ema_26'].iloc[-1]
            ema_50 = df['ema_50'].iloc[-1]
            
            # Trend direction
            if ema_12 > ema_26 > ema_50:
                trend_direction = 1  # Uptrend
            elif ema_12 < ema_26 < ema_50:
                trend_direction = -1  # Downtrend
            else:
                trend_direction = 0  # Sideways
            
            # MACD momentum
            macd_histogram = df['macd_histogram'].iloc[-1] if not pd.isna(df['macd_histogram'].iloc[-1]) else 0
            
            # Volume confirmation
            volume_ratio = df['volume_ratio'].iloc[-1] if not pd.isna(df['volume_ratio'].iloc[-1]) else 1
            
            trend_strength = {
                'adx_strength': adx_value,
                'trend_direction': trend_direction,
                'macd_momentum': macd_histogram,
                'volume_confirmation': volume_ratio,
                'overall_strength': (adx_value / 100) * abs(trend_direction) * min(volume_ratio, 2)
            }
            
            logger.debug(f"Trend strength calculated: {trend_strength}")
            return trend_strength
        except Exception as e:
            logger.error(f"Error calculating trend strength: {e}")
            raise
    
    def generate_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Tạo tín hiệu trading dựa trên phân tích kỹ thuật"""
        try:
            signals = {
                'buy_signals': 0,
                'sell_signals': 0,
                'signal_strength': 0,
                'confidence': 0,
                'details': []
            }
            
            current_idx = -1  # Sử dụng dữ liệu mới nhất
            
            # RSI signals
            rsi = df['rsi'].iloc[current_idx]
            if rsi < 30:
                signals['buy_signals'] += 1
                signals['details'].append('RSI oversold')
            elif rsi > 70:
                signals['sell_signals'] += 1
                signals['details'].append('RSI overbought')
            
            # MACD signals
            macd = df['macd'].iloc[current_idx]
            macd_signal = df['macd_signal'].iloc[current_idx]
            macd_hist = df['macd_histogram'].iloc[current_idx]
            
            if macd > macd_signal and macd_hist > 0:
                signals['buy_signals'] += 1
                signals['details'].append('MACD bullish')
            elif macd < macd_signal and macd_hist < 0:
                signals['sell_signals'] += 1
                signals['details'].append('MACD bearish')
            
            # Bollinger Bands signals
            bb_percent = df['bb_percent'].iloc[current_idx]
            if bb_percent < 0.2:
                signals['buy_signals'] += 1
                signals['details'].append('BB oversold')
            elif bb_percent > 0.8:
                signals['sell_signals'] += 1
                signals['details'].append('BB overbought')
            
            # Moving Average signals
            close = df['close'].iloc[current_idx]
            ema_12 = df['ema_12'].iloc[current_idx]
            ema_26 = df['ema_26'].iloc[current_idx]
            
            if ema_12 > ema_26 and close > ema_12:
                signals['buy_signals'] += 1
                signals['details'].append('EMA bullish crossover')
            elif ema_12 < ema_26 and close < ema_12:
                signals['sell_signals'] += 1
                signals['details'].append('EMA bearish crossover')
            
            # Stochastic signals
            stoch_k = df['stoch_k'].iloc[current_idx]
            stoch_d = df['stoch_d'].iloc[current_idx]
            
            if stoch_k < 20 and stoch_k > stoch_d:
                signals['buy_signals'] += 1
                signals['details'].append('Stochastic bullish')
            elif stoch_k > 80 and stoch_k < stoch_d:
                signals['sell_signals'] += 1
                signals['details'].append('Stochastic bearish')
            
            # Candlestick pattern signals
            bullish_patterns = ['hammer', 'engulfing', 'morning_star', 'piercing']
            bearish_patterns = ['hanging_man', 'shooting_star', 'evening_star', 'dark_cloud']
            
            for pattern in bullish_patterns:
                if df[pattern].iloc[current_idx] > 0:
                    signals['buy_signals'] += 1
                    signals['details'].append(f'Bullish {pattern}')
            
            for pattern in bearish_patterns:
                if df[pattern].iloc[current_idx] < 0:
                    signals['sell_signals'] += 1
                    signals['details'].append(f'Bearish {pattern}')
            
            # Tính toán signal strength và confidence
            total_signals = signals['buy_signals'] + signals['sell_signals']
            if total_signals > 0:
                if signals['buy_signals'] > signals['sell_signals']:
                    signals['signal_strength'] = (signals['buy_signals'] - signals['sell_signals']) / total_signals
                    signals['confidence'] = signals['buy_signals'] / 7  # Tối đa 7 chỉ báo
                else:
                    signals['signal_strength'] = -(signals['sell_signals'] - signals['buy_signals']) / total_signals
                    signals['confidence'] = signals['sell_signals'] / 7
            
            # Giới hạn confidence trong khoảng [0, 1]
            signals['confidence'] = min(abs(signals['confidence']), 1.0)
            
            logger.debug(f"Generated signals: {signals}")
            return signals
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            raise
    
    def analyze_market_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Phân tích cấu trúc thị trường"""
        try:
            # Xác định Higher Highs, Lower Lows
            highs = df['high'].rolling(window=5, center=True).max()
            lows = df['low'].rolling(window=5, center=True).min()
            
            # Đếm số lượng HH, HL, LH, LL trong 20 nến gần nhất
            recent_data = df.tail(20)
            
            structure = {
                'market_phase': 'consolidation',
                'trend_quality': 'weak',
                'volatility': 'normal',
                'volume_profile': 'average'
            }
            
            # Phân tích volatility
            atr = df['atr'].iloc[-1]
            atr_avg = df['atr'].tail(20).mean()
            
            if atr > atr_avg * 1.5:
                structure['volatility'] = 'high'
            elif atr < atr_avg * 0.7:
                structure['volatility'] = 'low'
            
            # Phân tích volume
            volume_avg = df['volume'].tail(20).mean()
            current_volume = df['volume'].iloc[-1]
            
            if current_volume > volume_avg * 1.5:
                structure['volume_profile'] = 'high'
            elif current_volume < volume_avg * 0.7:
                structure['volume_profile'] = 'low'
            
            # Phân tích trend quality dựa trên ADX
            adx = df['adx'].iloc[-1]
            if adx > 40:
                structure['trend_quality'] = 'strong'
            elif adx > 25:
                structure['trend_quality'] = 'moderate'
            
            # Xác định market phase
            ema_12 = df['ema_12'].iloc[-1]
            ema_26 = df['ema_26'].iloc[-1]
            ema_50 = df['ema_50'].iloc[-1]
            
            if ema_12 > ema_26 > ema_50:
                structure['market_phase'] = 'uptrend'
            elif ema_12 < ema_26 < ema_50:
                structure['market_phase'] = 'downtrend'
            
            logger.debug(f"Market structure analyzed: {structure}")
            return structure
        except Exception as e:
            logger.error(f"Error analyzing market structure: {e}")
            raise
    
    def full_analysis(self, klines_data: List[List]) -> Dict[str, Any]:
        """Phân tích kỹ thuật đầy đủ"""
        try:
            # Chuẩn bị dữ liệu
            df = self.prepare_dataframe(klines_data)
            
            # Thêm indicators
            df = self.add_basic_indicators(df)
            df = self.add_advanced_indicators(df)
            df = self.detect_candlestick_patterns(df)
            
            # Phân tích
            support_resistance = self.identify_support_resistance(df)
            trend_strength = self.calculate_trend_strength(df)
            signals = self.generate_signals(df)
            market_structure = self.analyze_market_structure(df)
            
            # Thêm patterns vào kết quả
            patterns = {}
            pattern_columns = ['hammer', 'hanging_man', 'engulfing', 'shooting_star', 'morning_star', 'evening_star', 'piercing', 'dark_cloud']
            for pattern in pattern_columns:
                if pattern in df.columns:
                    patterns[pattern] = int(df[pattern].sum())
                else:
                    patterns[pattern] = 0

            analysis_result = {
                'current_price': float(df['close'].iloc[-1]),
                'signals': signals,
                'trend_strength': trend_strength,
                'support_resistance': support_resistance,
                'market_structure': market_structure,
                'patterns': patterns,
                'timestamp': df.index[-1].isoformat()
            }
            
            logger.info("Full technical analysis completed")
            return analysis_result
        except Exception as e:
            logger.error(f"Error in full analysis: {e}")
            raise
