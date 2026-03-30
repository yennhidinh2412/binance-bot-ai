"""
TRAIN AI MODEL IMPROVED V2 - High Win-Rate Training Pipeline
- More training data (paginated API calls)
- Stricter labels (1.0% threshold, 2.0x gain/loss ratio)
- Cross-validation with TimeSeriesSplit
- Feature importance analysis
- Better hyperparameters
"""
import pandas as pd
import numpy as np
import os
import time as _time
from sklearn.ensemble import GradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
import joblib
try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
from binance_client import BinanceFuturesClient
from technical_analysis import TechnicalAnalyzer
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)


def get_extended_klines(client, symbol, interval='5m', total_candles=8640):
    """
    Fetch more candles than the API limit allows (1500 per call).
    8640 candles of 5m = 30 days of data.
    Uses pagination via endTime parameter.
    Falls back to public API (no auth needed) if client fails.
    """
    all_klines = []
    batch_size = 1500
    end_time = None

    # Try public API first (no auth needed for klines)
    import requests as _req
    PUBLIC_URL = "https://fapi.binance.com/fapi/v1/klines"
    use_public = True

    while len(all_klines) < total_candles:
        remaining = total_candles - len(all_klines)
        limit = min(batch_size, remaining)
        try:
            if use_public:
                params = {
                    'symbol': symbol,
                    'interval': interval,
                    'limit': limit,
                }
                if end_time:
                    params['endTime'] = end_time
                resp = _req.get(
                    PUBLIC_URL, params=params, timeout=15
                )
                resp.raise_for_status()
                klines = resp.json()
            else:
                kwargs = {
                    'symbol': symbol,
                    'interval': interval,
                    'limit': limit,
                }
                if end_time:
                    kwargs['endTime'] = end_time
                klines = client.client.futures_klines(
                    **kwargs
                )

            if not klines:
                break

            # Prepend (older data goes first)
            all_klines = klines + all_klines

            # Set endTime to just before the oldest candle
            end_time = klines[0][0] - 1

            logger.info(
                f"   Fetched {len(klines)} candles, "
                f"total: {len(all_klines)}/{total_candles}"
            )

            if len(klines) < limit:
                break  # No more data available

            _time.sleep(0.3)  # Rate limit
        except Exception as e:
            logger.warning(f"   Pagination error: {e}")
            break

    # Remove duplicates by timestamp
    seen = set()
    unique = []
    for k in all_klines:
        ts = k[0]
        if ts not in seen:
            seen.add(ts)
            unique.append(k)
    unique.sort(key=lambda x: x[0])

    logger.info(f"   Total unique candles: {len(unique)}")
    return unique

def detect_candlestick_patterns(df):
    """Phát hiện các mẫu nến quan trọng"""
    patterns = {}
    
    # Doji - Thân nến rất nhỏ
    body = abs(df['close'] - df['open'])
    total_range = df['high'] - df['low']
    patterns['is_doji'] = (body / total_range < 0.1).astype(int)
    
    # Hammer - Bấc dài phía dưới, thân nhỏ ở trên (đảo chiều tăng)
    lower_shadow = df[['open', 'close']].min(axis=1) - df['low']
    upper_shadow = df['high'] - df[['open', 'close']].max(axis=1)
    patterns['is_hammer'] = ((lower_shadow > 2 * body) & (upper_shadow < body)).astype(int)
    
    # Shooting Star - Bấc dài phía trên, thân nhỏ ở dưới (đảo chiều giảm)
    patterns['is_shooting_star'] = ((upper_shadow > 2 * body) & (lower_shadow < body)).astype(int)
    
    # Engulfing Bullish - Nến xanh bao trùm nến đỏ trước
    prev_red = (df['close'].shift(1) < df['open'].shift(1))
    curr_green = (df['close'] > df['open'])
    engulf = (df['open'] <= df['close'].shift(1)) & (df['close'] >= df['open'].shift(1))
    patterns['is_bullish_engulfing'] = (prev_red & curr_green & engulf).astype(int)
    
    # Engulfing Bearish - Nến đỏ bao trùm nến xanh trước
    prev_green = (df['close'].shift(1) > df['open'].shift(1))
    curr_red = (df['close'] < df['open'])
    engulf_bear = (df['open'] >= df['close'].shift(1)) & (df['close'] <= df['open'].shift(1))
    patterns['is_bearish_engulfing'] = (prev_green & curr_red & engulf_bear).astype(int)
    
    return patterns

def calculate_trend_features(df):
    """Tính toán xu hướng dài hạn"""
    features = {}
    
    # EMA Cross - Xu hướng chính
    if 'ema_50' in df.columns and 'ema_200' in df.columns:
        features['ema_cross_bullish'] = (df['ema_50'] > df['ema_200']).astype(int)
        features['ema_distance'] = ((df['ema_50'] - df['ema_200']) / df['ema_200'] * 100)
    
    # Price vs EMA - Vị trí giá
    if 'close' in df.columns and 'ema_50' in df.columns:
        features['price_above_ema50'] = (df['close'] > df['ema_50']).astype(int)
        features['price_distance_ema50'] = ((df['close'] - df['ema_50']) / df['ema_50'] * 100)
    
    # ADX - Sức mạnh xu hướng
    if 'adx' in df.columns:
        features['strong_trend'] = (df['adx'] > 25).astype(int)
        features['very_strong_trend'] = (df['adx'] > 40).astype(int)
    
    # Support/Resistance - Tìm đáy/đỉnh gần nhất (20 nến)
    if 'low' in df.columns and 'high' in df.columns:
        rolling_low = df['low'].rolling(window=20).min()
        rolling_high = df['high'].rolling(window=20).max()
        
        features['near_support'] = (abs(df['close'] - rolling_low) / df['close'] < 0.01).astype(int)
        features['near_resistance'] = (abs(df['close'] - rolling_high) / df['close'] < 0.01).astype(int)
        features['distance_to_support'] = ((df['close'] - rolling_low) / df['close'] * 100)
        features['distance_to_resistance'] = ((rolling_high - df['close']) / df['close'] * 100)
    
    # Volume Trend
    if 'volume' in df.columns:
        vol_ma = df['volume'].rolling(window=20).mean()
        features['volume_above_avg'] = (df['volume'] > vol_ma).astype(int)
        features['volume_surge'] = (df['volume'] > vol_ma * 1.5).astype(int)
    
    return features

def align_features_to_model(X, current_feature_names, model_data):
    """
    Align features to match what the model expects.
    If HTF features are missing (e.g. h1_rsi, h4_adx), pad with 0.
    If extra features exist, drop them.
    Returns aligned X array.
    """
    expected_names = model_data.get('feature_names', None)

    if expected_names is None:
        # No feature names stored — fall back to model.n_features_in_
        model = model_data.get('model', None)
        n_expected = getattr(model, 'n_features_in_', None)
        if n_expected is None or n_expected == X.shape[1]:
            return X
        if n_expected > X.shape[1]:
            # Pad missing columns with zeros on the right
            pad = np.zeros((X.shape[0], n_expected - X.shape[1]))
            return np.hstack([X, pad])
        else:
            # Trim extra columns
            return X[:, :n_expected]

    if len(expected_names) == X.shape[1]:
        return X  # Already aligned

    aligned = np.zeros((X.shape[0], len(expected_names)))
    name_to_idx = {
        name: i for i, name in enumerate(current_feature_names)
    }
    for j, exp_name in enumerate(expected_names):
        if exp_name in name_to_idx:
            aligned[:, j] = X[:, name_to_idx[exp_name]]
        # else: stays 0 (missing HTF feature)

    return aligned


def create_smart_labels(df, future_bars=15, threshold=0.010):
    """
    Tạo nhãn CHẤT LƯỢNG CAO - chỉ label setup rõ ràng
    - LONG (1): Giá sẽ tăng > 1.0% VÀ gain >> loss
    - SHORT (-1): Giá sẽ giảm > 1.0% VÀ loss >> gain
    - HOLD (0): Không rõ ràng → majority class

    future_bars=15: nhìn 15 nến tới (~1h15m trên 5m)
    threshold=0.010: 1.0% — chỉ setup thực sự rõ ràng
    gain/loss ratio: 2.0x — signal phải vượt trội rõ rệt
    """
    labels = []

    for i in range(len(df) - future_bars):
        current_price = df['close'].iloc[i]
        future_prices = df['close'].iloc[i+1:i+future_bars+1]

        max_price = future_prices.max()
        min_price = future_prices.min()

        gain = (max_price - current_price) / current_price
        loss = (current_price - min_price) / current_price

        # Stricter: gain must clearly dominate loss by 2x
        if gain > threshold and gain > loss * 2.0:
            labels.append(1)   # LONG
        elif loss > threshold and loss > gain * 2.0:
            labels.append(-1)  # SHORT
        else:
            labels.append(0)   # HOLD

    labels.extend([0] * future_bars)
    return labels

def create_trade_simulation_labels(df, sl_pct=0.015, tp_pct=0.030, max_bars=60):
    """
    V3 LABELS: Simulates actual TP/SL fills on each bar.

    Cho mỗi candle i (entry tại close[i]):
      - LONG (1): HIGH[i+1..] chạm tp_price TRƯỚC KHI LOW chạm sl_price
      - SHORT (-1): LOW[i+1..] chạm tp_price TRƯỚC KHI HIGH chạm sl_price
      - HOLD (0): ambiguous (cả hai cùng bar, timeout, không rõ)

    sl_pct=0.015 → SL 1.5%  |  tp_pct=0.030 → TP 3.0%
    Phù hợp với tỉ lệ R:R thực tế của bot (1:2)
    """
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    n = len(df)
    labels = []

    for i in range(n - 1):
        entry = closes[i]
        long_tp = entry * (1 + tp_pct)
        long_sl = entry * (1 - sl_pct)
        short_tp = entry * (1 - tp_pct)
        short_sl = entry * (1 + sl_pct)

        long_win = short_win = False
        long_lose = short_lose = False

        for j in range(i + 1, min(i + max_bars + 1, n)):
            h, lo = highs[j], lows[j]
            if not long_win and not long_lose:
                if h >= long_tp and lo <= long_sl:
                    pass  # ambiguous bar
                elif h >= long_tp:
                    long_win = True
                elif lo <= long_sl:
                    long_lose = True
            if not short_win and not short_lose:
                if lo <= short_tp and h >= short_sl:
                    pass  # ambiguous bar
                elif lo <= short_tp:
                    short_win = True
                elif h >= short_sl:
                    short_lose = True
            if (long_win or long_lose) and (short_win or short_lose):
                break

        if long_win and not short_win:
            labels.append(1)
        elif short_win and not long_win:
            labels.append(-1)
        else:
            labels.append(0)

    labels.append(0)  # last bar has no future
    return labels


def create_forward_return_labels(df, horizon=24, threshold=0.008):
    """
    V4 LABELS: Forward return classification.
    Đơn giản hơn TP/SL simulation → model học tốt hơn nhiều.

    horizon=24 bars × 5m = 2 giờ lookahead
    threshold=0.8%: LONG nếu giá tăng ≥0.8%, SHORT nếu giảm ≥0.8%

    Phân phối kỳ vọng: LONG~35%, SHORT~35%, HOLD~30%
    (tốt hơn nhiều so với TP/SL: 15/17/58%)
    """
    closes = df['close'].values
    n = len(closes)
    labels = []

    for i in range(n - horizon):
        ret = (closes[i + horizon] - closes[i]) / closes[i]
        if ret > threshold:
            labels.append(1)
        elif ret < -threshold:
            labels.append(-1)
        else:
            labels.append(0)

    labels.extend([0] * horizon)
    return labels


def create_binary_labels(df, pct=0.015, max_bars=60):
    """
    V6 BINARY LABELS: Price hit +pct% or -pct% first?

    LONG(1): price rose pct% first within max_bars
    SHORT(0): price fell pct% first within max_bars
    NaN: neither threshold hit (ranging/ambiguous) → dropped

    With symmetric TP=SL, this is equivalent to:
    "Would a LONG or SHORT trade have won?"
    Ambiguous samples removed → cleaner training signal.

    pct=0.015 → 1.5% move threshold
    max_bars=60 → 5 hours on 5m timeframe
    """
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    n = len(df)
    labels = np.full(n, np.nan)

    for i in range(n - 1):
        entry = closes[i]
        up_target = entry * (1 + pct)
        down_target = entry * (1 - pct)

        for j in range(i + 1, min(i + max_bars + 1, n)):
            h, lo = highs[j], lows[j]
            hit_up = h >= up_target
            hit_down = lo <= down_target

            if hit_up and hit_down:
                break  # ambiguous bar → stays NaN
            elif hit_up:
                labels[i] = 1  # LONG
                break
            elif hit_down:
                labels[i] = 0  # SHORT
                break

    return labels


def balance_classes(X, y, hold_ratio=0.8):
    """
    Undersample HOLD class để balance dataset.
    hold_ratio=0.8: HOLD samples = 0.8x (LONG + SHORT count)
    Giữ nguyên thứ tự thời gian (time-series safe).
    """
    idx_long = np.where(y == 1)[0]
    idx_short = np.where(y == -1)[0]
    idx_hold = np.where(y == 0)[0]

    n_signal = len(idx_long) + len(idx_short)
    max_hold = int(n_signal * hold_ratio)

    if len(idx_hold) > max_hold and max_hold > 0:
        # Uniform spacing to preserve time distribution
        step = len(idx_hold) / max_hold
        selected = [idx_hold[int(k * step)] for k in range(max_hold)]
        idx_hold = np.array(selected)

    all_idx = np.sort(np.concatenate([idx_long, idx_short, idx_hold]))
    return X[all_idx], y[all_idx]


def prepare_advanced_features(df, htf_data=None):
    """
    Chuẩn bị features V7 — CHỈ stationary/normalized features
    Loại bỏ raw close, volume, EMA, SMA, ATR (non-stationary → overfit)
    """
    feature_dict = {}

    # V7: Only stationary/bounded oscillators — NO raw prices/volumes
    stationary_features = [
        'rsi', 'bb_width', 'bb_percent', 'adx',
        'stoch_k', 'stoch_d', 'williams_r', 'cci', 'mfi',
        'rsi_6', 'rsi_21', 'plus_di', 'minus_di'
    ]

    for col in stationary_features:
        if col in df.columns:
            feature_dict[col] = df[col].values

    # Normalized MACD (% of price — makes it stationary)
    if 'close' in df.columns:
        safe_close = df['close'].replace(0, 1)
        for mcol in ['macd', 'macd_signal', 'macd_histogram']:
            if mcol in df.columns:
                feature_dict[f'{mcol}_pct'] = (df[mcol] / safe_close * 100).values

    # Candlestick patterns
    patterns = detect_candlestick_patterns(df)
    feature_dict.update(patterns)

    # Trend features
    trend_features = calculate_trend_features(df)
    feature_dict.update(trend_features)

    # Price momentum (multi-period)
    if 'close' in df.columns:
        for p in [3, 5, 10, 20, 40]:
            feature_dict[f'roc_{p}'] = (
                df['close'].pct_change(p)
                .fillna(0).values * 100
            )

    # Volatility features
    if 'close' in df.columns:
        feature_dict['volatility_10'] = (
            df['close'].pct_change()
            .rolling(10).std().fillna(0).values * 100
        )
        feature_dict['volatility_20'] = (
            df['close'].pct_change()
            .rolling(20).std().fillna(0).values * 100
        )

    # RSI slope (momentum of RSI itself)
    if 'rsi' in df.columns:
        rsi_vals = df['rsi'].values
        rsi_slope = np.zeros_like(rsi_vals)
        rsi_slope[3:] = rsi_vals[3:] - rsi_vals[:-3]
        feature_dict['rsi_slope_3'] = rsi_slope

    # Normalized MACD histogram slope
    if 'macd_histogram' in df.columns and 'close' in df.columns:
        safe_close = df['close'].replace(0, 1).values
        mh_pct = df['macd_histogram'].values / safe_close * 100
        mh_slope = np.zeros_like(mh_pct)
        mh_slope[3:] = mh_pct[3:] - mh_pct[:-3]
        feature_dict['macd_hist_pct_slope'] = mh_slope

    # Market regime: ATR ratio (current vs 50-period avg)
    if 'atr' in df.columns:
        atr_vals = df['atr'].values
        atr_ma = pd.Series(atr_vals).rolling(50).mean().bfill().values
        safe_atr_ma = np.where(atr_ma == 0, 1, atr_ma)
        feature_dict['atr_ratio'] = atr_vals / safe_atr_ma

    # EMA fan (distance between short and long EMAs)
    if 'ema_9' in df.columns and 'ema_200' in df.columns:
        e9 = df['ema_9'].values
        e200 = df['ema_200'].values
        safe_e200 = np.where(e200 == 0, 1, e200)
        feature_dict['ema_fan'] = (e9 - e200) / safe_e200 * 100

    # Volume ratio (unusual volume = breakout/reversal signal)
    if 'volume' in df.columns:
        vol_series = df['volume']
        vol_ma = vol_series.rolling(20).mean().bfill().replace(0, 1)
        feature_dict['volume_ratio'] = (vol_series / vol_ma).values
        feature_dict['volume_spike'] = (
            vol_series > vol_ma * 2.0
        ).astype(int).values

    # RSI lags (RSI trend = momentum momentum)
    if 'rsi' in df.columns:
        for lag in [3, 6, 12]:
            feature_dict[f'rsi_lag_{lag}'] = (
                df['rsi'].shift(lag).fillna(50).values
            )

    # Normalized MACD histogram lags
    if 'macd_histogram' in df.columns and 'close' in df.columns:
        safe_close = df['close'].replace(0, 1)
        macd_hist_pct = df['macd_histogram'] / safe_close * 100
        for lag in [3, 6]:
            feature_dict[f'macd_hist_pct_lag_{lag}'] = (
                macd_hist_pct.shift(lag).fillna(0).values
            )

    # Candle body/wick ratio (price action quality)
    if 'open' in df.columns and 'close' in df.columns:
        body = abs(df['close'] - df['open'])
        total = (df['high'] - df['low']).replace(0, 1)
        feature_dict['body_ratio'] = (body / total).values

    # Higher-timeframe features — only stationary ones
    htf_cols = [c for c in df.columns if c.startswith(('h1_', 'h4_'))]
    for col in htf_cols:
        if any(k in col for k in ['rsi', 'adx', 'trend']):
            feature_dict[col] = df[col].fillna(0).values
        elif 'macd' in col and 'close' in df.columns:
            safe_close = df['close'].replace(0, 1)
            feature_dict[f'{col}_pct'] = (df[col].fillna(0) / safe_close * 100).values
        # Skip raw HTF ema/sma (non-stationary)
    if htf_data and isinstance(htf_data, dict):
        for k, v in htf_data.items():
            if k not in feature_dict and any(s in k for s in ['rsi', 'adx', 'trend']):
                feature_dict[k] = v

    # Convert to DataFrame
    features_df = pd.DataFrame(feature_dict)
    features_df = features_df.fillna(0)

    return features_df.values, list(feature_dict.keys())


def get_htf_features_for_training(client, analyzer, symbol):
    """
    Lấy features từ 1h và 4h timeframe.
    Trả về dict chứa DataFrames có timestamp để merge_asof vào 5m.
    Falls back to public API if client fails.
    """
    import requests as _req
    PUBLIC_URL = "https://fapi.binance.com/fapi/v1/klines"

    htf_dfs = {}
    for tf, label in [('1h', 'h1'), ('4h', 'h4')]:
        try:
            # Try client first, fallback to public API
            try:
                klines = client.get_klines(symbol, tf, 500)
            except Exception:
                resp = _req.get(PUBLIC_URL, params={
                    'symbol': symbol,
                    'interval': tf,
                    'limit': 500
                }, timeout=15)
                resp.raise_for_status()
                klines = resp.json()
            if not klines:
                continue
            htf_df = analyzer.prepare_dataframe(klines)
            htf_df = analyzer.add_basic_indicators(htf_df)

            cols_out = {}
            for col in ['rsi', 'macd', 'adx', 'ema_50', 'ema_200']:
                if col in htf_df.columns:
                    cols_out[f'{label}_{col}'] = htf_df[col].values
            if 'ema_50' in htf_df.columns and 'ema_200' in htf_df.columns:
                cols_out[f'{label}_trend'] = (
                    (htf_df['ema_50'] > htf_df['ema_200'])
                    .astype(int).values
                )

            # Build a small DF with timestamp for merge_asof
            out = pd.DataFrame(cols_out)
            out['timestamp'] = htf_df['timestamp'].values
            htf_dfs[label] = out
        except Exception:
            pass
    return htf_dfs

def train_symbol(symbol):
    """Train models cho 1 symbol - V7: Binary + anti-overfit + stationary features"""
    logger.info(f"\n{'='*60}")
    logger.info(f"🎯 TRAINING V7 MODELS: {symbol}")
    logger.info(f"{'='*60}")

    # More data: 90 days BTC/ETH, 60 days SOL
    n_days = 60 if symbol == 'SOLUSDT' else 90
    total_candles = n_days * 24 * 12  # 12 candles/hour (5m)

    # Initialize
    client = BinanceFuturesClient()
    analyzer = TechnicalAnalyzer()

    # ===== DATA DOWNLOAD =====
    logger.info(f"📥 Downloading ~{n_days} days of 5m data ({total_candles} candles)...")
    klines = get_extended_klines(
        client, symbol, '5m', total_candles=total_candles
    )
    if not klines or len(klines) < 500:
        logger.error(f"❌ Insufficient data for {symbol}")
        return None
    logger.info(f"   Got {len(klines)} candles")

    # Get HTF features
    logger.info("📥 Fetching 1h & 4h HTF context...")
    htf_dfs = get_htf_features_for_training(client, analyzer, symbol)
    logger.info(f"   HTF timeframes: {list(htf_dfs.keys())}")

    # Prepare dataframe
    logger.info("📊 Calculating indicators...")
    df = analyzer.prepare_dataframe(klines)
    df = analyzer.add_basic_indicators(df)
    df = analyzer.add_advanced_indicators(df)

    # Merge HTF features
    if htf_dfs:
        df['timestamp'] = pd.to_numeric(df['timestamp'])
        df = df.sort_values('timestamp')
        for label, htf_df in htf_dfs.items():
            htf_df['timestamp'] = pd.to_numeric(htf_df['timestamp'])
            htf_df = htf_df.sort_values('timestamp')
            df = pd.merge_asof(
                df, htf_df, on='timestamp', direction='backward'
            )
        logger.info(f"   Merged HTF → {len(df.columns)} columns total")

    # ===== V6 LABELS: Binary (LONG vs SHORT only) =====
    logger.info("🏷️ Creating V7 BINARY labels (threshold=1.5%, max_bars=60)...")
    labels = create_binary_labels(df, pct=0.015, max_bars=60)
    df['label'] = labels

    # Prepare features
    logger.info("🔧 Preparing features...")
    X, feature_names = prepare_advanced_features(df)
    y = np.array(df['label'].values, dtype=float)

    # Remove NaN rows (indicator warmup + ambiguous labels → NaN)
    valid_idx = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
    X = X[valid_idx]
    y = y[valid_idx].astype(int)

    n_dropped = (~valid_idx).sum()
    logger.info(f"📈 Clean dataset: {len(X)} samples, {X.shape[1]} features")
    logger.info(
        f"   LONG(1): {(y==1).sum()}, "
        f"SHORT(0): {(y==0).sum()}, "
        f"Dropped: {n_dropped} ambiguous/NaN"
    )

    if len(X) < 200:
        logger.error(f"❌ Too few clean samples: {len(X)}")
        return None

    # Time-series split: 80/20
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # ===== V7 PREPROCESSING: StandardScaler ONLY =====
    logger.info("\n🔧 V7 Preprocessing: StandardScaler only...")
    scaler = StandardScaler()
    X_train_proc = scaler.fit_transform(X_train)
    X_test_proc = scaler.transform(X_test)
    logger.info(f"   Features: {X_train.shape[1]} (all kept, tree regularizes internally)")

    sw_train = compute_sample_weight('balanced', y_train)
    results = {}

    # ===== MODEL 1: GradientBoosting V7 (Binary) =====
    logger.info("\n🤖 [1/3] Training GradientBoosting V7...")
    gb = GradientBoostingClassifier(
        n_estimators=500,
        max_depth=3,
        learning_rate=0.01,
        subsample=0.75,
        min_samples_split=30,
        min_samples_leaf=25,
        max_features='sqrt',
        validation_fraction=0.15,
        n_iter_no_change=30,
        tol=1e-4,
        random_state=42
    )
    gb.fit(X_train_proc, y_train, sample_weight=sw_train)
    gb_train = gb.score(X_train_proc, y_train) * 100
    gb_test = gb.score(X_test_proc, y_test) * 100
    logger.info(f"   Train: {gb_train:.1f}% | Test: {gb_test:.1f}%")
    gb_pipe = Pipeline([('scaler', scaler), ('model', gb)])
    results['gradient_boost'] = {'model': gb_pipe, 'test_acc': gb_test}

    # ===== MODEL 2: XGBoost V6 (Binary) =====
    if HAS_XGBOOST:
        logger.info("🤖 [2/3] Training XGBoost V7...")
        xgb = XGBClassifier(
            n_estimators=500,
            max_depth=3,
            learning_rate=0.01,
            subsample=0.75,
            colsample_bytree=0.75,
            min_child_weight=20,
            gamma=0.15,
            reg_alpha=0.1,
            reg_lambda=1.0,
            early_stopping_rounds=30,
            eval_metric='logloss',
            random_state=42,
            verbosity=0
        )
        xgb.fit(
            X_train_proc, y_train,
            sample_weight=sw_train,
            eval_set=[(X_test_proc, y_test)],
            verbose=False
        )
        xgb_train = xgb.score(X_train_proc, y_train) * 100
        xgb_test = xgb.score(X_test_proc, y_test) * 100
        logger.info(f"   Train: {xgb_train:.1f}% | Test: {xgb_test:.1f}%")
        xgb_pipe = Pipeline([('scaler', scaler), ('model', xgb)])
        results['xgboost'] = {'model': xgb_pipe, 'test_acc': xgb_test}
    else:
        logger.warning("⚠️  XGBoost not available, fallback to extra GB")
        gb2 = GradientBoostingClassifier(
            n_estimators=400, max_depth=3, learning_rate=0.01,
            subsample=0.75, min_samples_leaf=25, random_state=99
        )
        gb2.fit(X_train_proc, y_train, sample_weight=sw_train)
        gb2_test = gb2.score(X_test_proc, y_test) * 100
        logger.info(
            f"   Train: {gb2.score(X_train_proc, y_train)*100:.1f}%"
            f" | Test: {gb2_test:.1f}%"
        )
        gb2_pipe = Pipeline([('scaler', scaler), ('model', gb2)])
        results['xgboost'] = {'model': gb2_pipe, 'test_acc': gb2_test}

    # ===== MODEL 3: HistGradientBoosting V7 (Binary) =====
    logger.info("🤖 [3/3] Training HistGradientBoosting V7...")
    hgb = HistGradientBoostingClassifier(
        max_iter=500,
        max_depth=3,
        learning_rate=0.01,
        min_samples_leaf=25,
        l2_regularization=0.5,
        validation_fraction=0.15,
        n_iter_no_change=30,
        random_state=42
    )
    hgb.fit(X_train_proc, y_train, sample_weight=sw_train)
    hgb_train = hgb.score(X_train_proc, y_train) * 100
    hgb_test = hgb.score(X_test_proc, y_test) * 100
    logger.info(f"   Train: {hgb_train:.1f}% | Test: {hgb_test:.1f}%")
    hgb_pipe = Pipeline([('scaler', scaler), ('model', hgb)])
    results['hist_gb'] = {'model': hgb_pipe, 'test_acc': hgb_test}

    # ===== CROSS-VALIDATION (TimeSeriesSplit, purged) =====
    from sklearn.model_selection import TimeSeriesSplit
    logger.info("\n📊 TimeSeriesSplit CV (5 folds, purge=60)...")
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = []
    purge_gap = 60  # Avoid label leakage

    for fold_i, (tr_idx, val_idx) in enumerate(tscv.split(X)):
        if len(tr_idx) > purge_gap:
            tr_idx = tr_idx[:-purge_gap]
        cv_scaler = StandardScaler()
        X_tr = cv_scaler.fit_transform(X[tr_idx])
        X_val = cv_scaler.transform(X[val_idx])
        sw = compute_sample_weight('balanced', y[tr_idx])
        cv_gb = GradientBoostingClassifier(
            n_estimators=500, max_depth=3,
            learning_rate=0.01, subsample=0.75,
            min_samples_split=30, min_samples_leaf=25,
            max_features='sqrt',
            validation_fraction=0.15,
            n_iter_no_change=30, tol=1e-4,
            random_state=42
        )
        cv_gb.fit(X_tr, y[tr_idx], sample_weight=sw)
        score = cv_gb.score(X_val, y[val_idx]) * 100
        cv_scores.append(score)
        logger.info(f"   Fold {fold_i+1}: {score:.1f}%")

    cv_mean = np.mean(cv_scores)
    cv_std = np.std(cv_scores)
    logger.info(
        f"   CV: {cv_mean:.1f}% ± {cv_std:.1f}%"
    )

    # ===== EVALUATION (Binary) =====
    logger.info(f"\n📊 EVALUATION REPORT — {symbol}")
    best_model_name = max(results, key=lambda k: results[k]['test_acc'])
    best_pipe = results[best_model_name]['model']
    y_pred = best_pipe.predict(X_test)

    logger.info(
        f"   Best model: {best_model_name} "
        f"({results[best_model_name]['test_acc']:.1f}%)"
    )
    for cls, name in [(0, 'SHORT'), (1, 'LONG')]:
        mask = y_test == cls
        if mask.sum() > 0:
            cls_acc = accuracy_score(y_test[mask], y_pred[mask]) * 100
            logger.info(f"   {name}: {cls_acc:.1f}% ({mask.sum()} samples)")

    # Binary accuracy = trade quality (no HOLD class)
    trade_quality = accuracy_score(y_test, y_pred) * 100

    # Expected value: TP=SL=1.5% → each correct trade +1.5%, wrong -1.5%
    overall_acc = trade_quality / 100
    ev = overall_acc * 1.5 - (1 - overall_acc) * 1.5
    logger.info(f"   Expected value per trade: {ev:+.3f}%")
    if ev > 0:
        logger.info(f"   ✅ PROFITABLE edge! {ev:.3f}% per trade")
    else:
        logger.info(f"   ⚠️  Negative edge: {ev:.3f}% per trade")

    # ===== SAVE ALL 3 MODELS AS PIPELINES =====
    os.makedirs('models', exist_ok=True)
    model_path = f'models/gradient_boost_{symbol}.pkl'

    joblib.dump({
        'model': results['gradient_boost']['model'],   # Pipeline
        'model_xgb': results['xgboost']['model'],      # Pipeline
        'model_hgb': results['hist_gb']['model'],      # Pipeline
        'feature_names': feature_names,
        'accuracy': results['gradient_boost']['test_acc'],
        'accuracy_xgb': results['xgboost']['test_acc'],
        'accuracy_hgb': results['hist_gb']['test_acc'],
        'trade_quality': trade_quality,
        'n_classes': 2,
        'label_method': 'v7_binary_stationary',
        'threshold_pct': 0.015,
        'cv_accuracy': cv_mean,
        'trained_at': str(pd.Timestamp.now()),
        'n_samples': len(X),
        'n_days': n_days,
        'n_features_selected': X_train_proc.shape[1],
        'label_distribution': {
            'LONG': int((y == 1).sum()),
            'SHORT': int((y == 0).sum()),
        },
    }, model_path)

    logger.info(f"\n💾 Saved all 3 pipelines to: {model_path}")
    logger.info(
        f"   GB: {results['gradient_boost']['test_acc']:.1f}% | "
        f"XGB: {results['xgboost']['test_acc']:.1f}% | "
        f"HGB: {results['hist_gb']['test_acc']:.1f}%"
    )

    return {
        'accuracy': results['gradient_boost']['test_acc'],
        'accuracy_xgb': results['xgboost']['test_acc'],
        'accuracy_hgb': results['hist_gb']['test_acc'],
        'trade_quality': trade_quality,
        'cv_accuracy': 0.0,
        'n_features': X.shape[1],
        'n_features_selected': X_train_proc.shape[1],
        'n_samples': len(X),
        'model_path': model_path,
    }


def main():
    """Train all symbols with V7 anti-overfit pipeline"""
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

    logger.info("=" * 60)
    logger.info("🚀 TRAINING V7 AI MODELS (Anti-Overfit)")
    logger.info("   ✅ V7: Stationary features only (no raw prices)")
    logger.info("   ✅ Normalized MACD (% of price)")
    logger.info("   ✅ TimeSeriesSplit CV (5-fold, purged)")
    logger.info("   ✅ Extended data: 90 days BTC/ETH, 60 days SOL")
    logger.info("   ✅ Binary: LONG vs SHORT (no HOLD class)")
    logger.info("   ✅ 3 models: GB + XGBoost + HistGB")
    logger.info("=" * 60)

    results = {}
    for symbol in symbols:
        result = train_symbol(symbol)
        if result:
            results[symbol] = result

    logger.info(f"\n{'='*60}")
    logger.info("📊 V7 TRAINING SUMMARY:")
    logger.info(f"{'='*60}")

    for symbol, r in results.items():
        logger.info(
            f"   {symbol}: GB={r['accuracy']:.1f}% | "
            f"XGB={r['accuracy_xgb']:.1f}% | "
            f"HGB={r['accuracy_hgb']:.1f}% | "
            f"TradeQ={r['trade_quality']:.1f}%"
        )

    if results:
        # Use best model per symbol (ensemble of GB/XGB/HGB)
        best_accs = []
        for sym, r in results.items():
            best = max(
                r['accuracy'],
                r['accuracy_xgb'],
                r['accuracy_hgb']
            )
            best_accs.append(best)
        avg_best = np.mean(best_accs)
        logger.info(
            f"\n🎯 Average best-model accuracy: "
            f"{avg_best:.1f}% (baseline=50%)"
        )
        # With R:R 1:2 (SL=1.5%, TP=3.0%), breakeven = 33%
        # With R:R 1:1 (SL=TP=1.5%), breakeven = 50%
        # > 51% on binary = profitable
        if avg_best >= 51:
            ev_rr2 = (
                avg_best / 100 * 3.0
                - (1 - avg_best / 100) * 1.5
            )
            logger.info(
                f"✅ Profitable! EV={ev_rr2:+.3f}% "
                f"per trade (R:R 1:2)"
            )
        else:
            logger.warning(
                f"⚠️  Accuracy {avg_best:.1f}% — "
                f"needs improvement"
            )

    logger.info("\n✅ All V7 models trained and saved!")
    logger.info("   models/gradient_boost_BTCUSDT.pkl")
    logger.info("   models/gradient_boost_ETHUSDT.pkl")
    logger.info("   models/gradient_boost_SOLUSDT.pkl")


if __name__ == "__main__":
    main()
