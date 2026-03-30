"""
Web Dashboard cho Binance Trading Bot
Simple web interface để control bot và monitor
"""

from flask import Flask, render_template, jsonify, request, Response
import asyncio
import os
import struct
import threading
import time
import zlib
from datetime import datetime
from loguru import logger

# Load .env file trước khi import Config (để env vars sẵn sàng)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

# Import bot modules
# Config is lightweight (only uses os) — safe to import at top level
from config import Config
# Heavy modules (pandas, numpy, sklearn, xgboost) are lazy-imported
# to let gunicorn bind the port ASAP and avoid Render "No open ports" warning
BinanceFuturesClient = None  # lazy
SmartBotEngine = None  # lazy
_heavy_imports_done = False


def _ensure_heavy_imports():
    """Lazy-load heavy modules on first use, not at startup."""
    global BinanceFuturesClient, SmartBotEngine, _heavy_imports_done
    if _heavy_imports_done:
        return
    from binance_client import BinanceFuturesClient as _BFC
    from smart_bot_engine import SmartBotEngine as _SBE
    BinanceFuturesClient = _BFC
    SmartBotEngine = _SBE
    _heavy_imports_done = True
    logger.info("✅ Heavy modules loaded")

app = Flask(__name__)
_flask_secret = os.environ.get("FLASK_SECRET_KEY")
if not _flask_secret:
    import secrets as _secrets
    _flask_secret = _secrets.token_hex(32)
app.secret_key = _flask_secret

# Global bot instance
bot_instance = None
bot_thread = None
bot_status = "stopped"
bot_logs = []


# Global bot manager reference for logging
_bot_manager_instance = None


def dashboard_log_sink(message):
    """Sink function to send logs to dashboard"""
    global _bot_manager_instance
    if _bot_manager_instance and hasattr(_bot_manager_instance, 'logs'):
        try:
            # Extract the actual message from loguru format
            msg_str = str(message)
            # Parse the log message
            if '|' in msg_str:
                parts = msg_str.split('|')
                if len(parts) >= 3:
                    # Get timestamp and message
                    level_part = parts[1].strip()
                    message_part = '|'.join(parts[2:]).strip()

                    # Skip DEBUG logs and unimportant messages
                    if 'DEBUG' in level_part:
                        return

                    # Skip verbose technical messages
                    skip_keywords = [
                        'Retrieved', 'Getting demo',
                        'Full technical analysis completed',
                        'Socket manager', 'Skipping signal handlers',
                        'Found', 'open positions',
                        'Account info retrieved',
                        'Technical Analyzer initialized',
                        'DataFrame prepared',
                        'indicators added',
                        'Basic indicators',
                        'Advanced indicators',
                    ]
                    if any(keyword in message_part
                           for keyword in skip_keywords):
                        return

                    # Format for dashboard
                    timestamp = datetime.now().strftime('%H:%M:%S')

                    # Add emoji based on level
                    if 'ERROR' in level_part:
                        emoji = '❌'
                    elif 'WARNING' in level_part:
                        emoji = '⚠️'
                    elif 'INFO' in level_part:
                        emoji = '📊'
                    elif 'SUCCESS' in level_part:
                        emoji = '✅'
                    else:
                        emoji = '🔍'

                    log_line = f"{timestamp} {emoji} {message_part}"
                    _bot_manager_instance.logs.append(log_line)

                    # Keep only last 200 logs
                    if len(_bot_manager_instance.logs) > 200:
                        _bot_manager_instance.logs = (
                            _bot_manager_instance.logs[-200:]
                        )
        except Exception:
            pass


class BotManager:
    """Quản lý bot trading với SmartBotEngine"""
    def __init__(self):
        self.smart_bot = None  # SmartBotEngine instance
        self.bot_thread = None
        self.price_simulator_thread = None
        self.price_simulator_running = False
        self.status = "stopped"
        self.logs = []
        self.loop = None
        self.log_handler = None
        self.trading_mode = "auto"  # Default: auto (trade immediately)
        self.pending_signals = []  # Store AI signals for semi-auto mode
        self.preflight_results = None  # Store pre-flight check results
        self.last_decision = None  # Store last AI decision
        
        # Load risk settings from Config (sync with v2 engine)
        cfg = Config.get_config()
        risk_cfg = cfg['risk_management']
        trading_cfg = cfg['trading']
        
        self.risk_settings = {
            'maxLeverage': trading_cfg.get('max_leverage', 40),
            'maxPositionSize': risk_cfg.get('max_position_size_percent', 30),
            'dailyMaxLoss': risk_cfg.get('max_daily_loss_percent', 5),
            'maxPositions': trading_cfg.get('max_open_positions', 3),
            'forceSL': True,
            'forceTP': True,
            'minConfidence': 35,
            'slPercentage': risk_cfg.get('stop_loss_percent', 1.5),
            'tpPercentage': risk_cfg.get('take_profit_percent', 3.0),
            # V2 settings
            'trailingStopPct': risk_cfg.get('trailing_stop_percent', 0.8),
            'breakevenTrigger': risk_cfg.get('breakeven_trigger_percent', 1.0),
            'partialTP': risk_cfg.get('partial_tp_enabled', True),
            'minADX': risk_cfg.get('min_adx_trend', 10),
            'maxDrawdown': risk_cfg.get('max_drawdown_percent', 10),
            'maxFundingRate': risk_cfg.get('max_funding_rate', 0.05),
            'volatilitySpikeMult': risk_cfg.get('volatility_spike_multiplier', 3.0),
            'symbolLeverage': trading_cfg.get('symbol_leverage', {
                'BTCUSDT': 40, 'ETHUSDT': 38, 'SOLUSDT': 35, 'ADAUSDT': 35
            })
        }
        
    def add_log(self, message):
        """Add log message với timestamp"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f"{timestamp} - {message}"
        self.logs.append(log_msg)
        logger.info(message)
    
    def start_price_simulator(self):
        """Start background thread to fetch REAL prices from Binance API"""
        if self.price_simulator_running:
            return

        self.price_simulator_running = True

        def fetch_real_prices():
            import time
            symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

            # Đợi 30s để app khởi động xong + tránh gọi API quá sớm
            time.sleep(30)

            while self.price_simulator_running:
                try:
                    client = _get_client()
                    if client and client.demo_account:
                        try:
                            tickers = (
                                client.client
                                .futures_symbol_ticker()
                            )
                            ticker_map = {
                                t['symbol']: float(t['price'])
                                for t in tickers
                            }
                            for symbol in symbols:
                                if symbol in ticker_map:
                                    client.demo_account.update_price(
                                        symbol, ticker_map[symbol]
                                    )
                        except Exception as e:
                            logger.debug(f"Price fetch error: {e}")

                    time.sleep(30)  # 30s - an toàn cho rate limit
                except Exception as e:
                    logger.debug(f"Price fetcher error: {e}")
                    time.sleep(60)  # Lỗi thì đợi lâu hơn

        self.price_simulator_thread = threading.Thread(
            target=fetch_real_prices, daemon=True
        )
        self.price_simulator_thread.start()
        logger.info("💹 Real-time price fetcher started (using Binance API)")
    
    def stop_price_simulator(self):
        """Stop price fetching"""
        self.price_simulator_running = False
        if self.price_simulator_thread:
            self.price_simulator_thread.join(timeout=3)
        
    def start_bot(self):
        """Start bot with SmartBotEngine and pre-flight check"""
        try:
            if self.bot_thread and self.bot_thread.is_alive():
                return {"success": False, "message": "Bot is already running"}
            
            # Set global reference for logging
            global _bot_manager_instance
            _bot_manager_instance = self
            
            # Clean logs on fresh start
            self.logs.clear()
            
            self.add_log("🚀 Starting SmartBotEngine...")
            self.add_log("🛫 Running Pre-Flight Check...")
            
            _ensure_heavy_imports()
            # Create SmartBotEngine - uses Config for all settings
            # Only pass dashboard overrides that differ from Config
            self.smart_bot = SmartBotEngine()  # Uses Config v2
            self.smart_bot.mode = self.trading_mode
            
            # Apply any dashboard-specific risk overrides
            rs = self.smart_bot.risk_settings
            rs['max_leverage'] = self.risk_settings['maxLeverage']
            rs['max_position_size'] = self.risk_settings['maxPositionSize']
            rs['daily_max_loss'] = self.risk_settings['dailyMaxLoss']
            rs['max_positions'] = self.risk_settings['maxPositions']
            rs['force_sl'] = self.risk_settings['forceSL']
            rs['force_tp'] = self.risk_settings['forceTP']
            rs['min_confidence'] = self.risk_settings['minConfidence']
            rs['sl_percentage'] = self.risk_settings['slPercentage']
            rs['tp_percentage'] = self.risk_settings['tpPercentage']
            
            # Start price simulator
            self.start_price_simulator()
            
            # Create new event loop for bot thread
            def run_bot():
                try:
                    # Create new event loop for this thread
                    self.loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self.loop)

                    # Run pre-flight check
                    passed, message = self.loop.run_until_complete(
                        self.smart_bot.pre_flight_check()
                    )

                    self.preflight_results = {
                        'passed': passed,
                        'message': message,
                        'timestamp': datetime.now().strftime(
                            '%Y-%m-%d %H:%M:%S'
                        )
                    }

                    if not passed:
                        self.add_log(f"❌ Pre-Flight Check FAILED: {message}")
                        self.status = "error"
                        return

                    self.add_log("✅ Pre-Flight Check PASSED - Starting bot...")
                    self.status = "running"

                    # Start bot (skip_preflight=True since we already checked)
                    self.loop.run_until_complete(
                        self.smart_bot.start(skip_preflight=True)
                    )

                except Exception as e:
                    self.add_log(f"❌ Bot error: {e}")
                    logger.error(f"Bot error: {e}", exc_info=True)
                    self.status = "error"
                finally:
                    if self.loop:
                        self.loop.close()
                    self.status = "stopped"

            # Start bot thread
            self.bot_thread = threading.Thread(target=run_bot, daemon=True)
            self.bot_thread.start()

            return {
                "success": True,
                "message": "Bot started - running pre-flight check..."
            }

        except Exception as e:
            self.add_log(f"❌ Error starting bot: {e}")
            logger.error(f"Error starting bot: {e}", exc_info=True)
            self.status = "error"
            return {"success": False, "message": f"Error: {e}"}

    def stop_bot(self):
        """Stop bot gracefully"""
        try:
            if not self.bot_thread or not self.bot_thread.is_alive():
                self.status = "stopped"
                return {"success": True, "message": "Bot was not running"}
            
            self.add_log("🛑 Stopping bot...")
            
            # Stop price simulator
            self.stop_price_simulator()
            
            # Stop SmartBotEngine
            if self.smart_bot:
                self.smart_bot.stop()

                # Wait for thread to finish (max 2 seconds for fast response)
                self.bot_thread.join(timeout=2)
            
            self.status = "stopped"
            self.smart_bot = None
            self.bot_thread = None
            self.add_log("✅ Bot stopped successfully")
            
            return {"success": True, "message": "Bot stopped successfully"}
                
        except Exception as e:
            self.status = "stopped"
            self.smart_bot = None
            self.bot_thread = None
            self.add_log(f"❌ Error stopping bot: {e}")
            return {"success": False, "message": f"Error: {e}"}
    
    def get_status(self):
        """Get current bot status"""
        if self.bot_thread and self.bot_thread.is_alive():
            self.status = "running"
        else:
            if self.status == "running":
                self.status = "stopped"
        return self.status
    
    def is_running(self):
        """Check if bot is currently running"""
        if self.bot_thread and self.bot_thread.is_alive():
            self.status = "running"
            return True
        else:
            if self.status == "running":
                self.status = "stopped"
            return False

    def get_logs(self):
        """Get recent logs"""
        return self.logs[-100:]  # Return last 100 logs


# Initialize bot manager
bot_manager = BotManager()

# Set global reference for logging immediately
_bot_manager_instance = bot_manager

# Add loguru sink to capture all logs to dashboard
logger.add(
    dashboard_log_sink,
    format="{time:HH:mm:ss} | {level: <8} | {message}",
    level="INFO",
    enqueue=True  # Thread-safe
)

# Add initial log
bot_manager.add_log("🚀 Dashboard started - Waiting for commands...")

# ── Lazy Binance client ──────────────────────────────────────────────────
# Không khởi tạo ngay khi import để tránh bị ban IP nếu Render restart
# liên tục. Client chỉ được tạo khi có request đầu tiên thực sự cần.
binance_client = None
_client_last_retry: float = 0.0
_CLIENT_RETRY_COOLDOWN = 60.0  # 60s - tránh gọi API khi đang bị ban
_ban_until: float = 0.0  # epoch (s) khi ban hết hạn


def _get_client():
    """Lazy init: tạo client lần đầu hoặc retry sau cooldown.
    Parse ban expiry để không retry vô ích trong lúc bị ban.
    BinanceFuturesClient(ping=False) chỉ gọi 1 API (time sync).
    """
    _ensure_heavy_imports()
    global binance_client, _client_last_retry, _ban_until
    if binance_client is not None:
        return binance_client
    import time as _t
    now = _t.time()
    # Nếu biết đang bị ban, không thử cho đến khi hết
    if _ban_until > 0 and now < _ban_until:
        return None
    if now - _client_last_retry < _CLIENT_RETRY_COOLDOWN:
        return None  # vẫn trong cooldown, không thử lại
    _client_last_retry = now
    # Không cần pre-check nữa vì BinanceFuturesClient(ping=False)
    # chỉ gọi 1 call /fapi/v1/time (weight=1) và tự raise nếu ban
    try:
        binance_client = BinanceFuturesClient()
        logger.info("Binance client initialized OK!")
        _ban_until = 0.0
    except Exception as e:
        msg = str(e)
        logger.error(f"Client init failed: {e}")
        _parse_ban_until(msg)
        binance_client = None
    return binance_client


def _parse_ban_until(msg: str):
    """Trích ban expiry từ Binance error message."""
    global _ban_until
    import re
    m = re.search(r'banned until (\d+)', msg)
    if m:
        _ban_until = int(m.group(1)) / 1000.0
        import time as _t
        remaining = _ban_until - _t.time()
        if remaining > 0:
            logger.warning(
                f"IP ban expires in {remaining:.0f}s "
                f"(~{remaining / 60:.1f} min)"
            )


# ── Background init thread ───────────────────────────────────────────────
# Tự động thử init client, đợi đúng thời điểm ban hết thay vì retry mù
def _background_client_init():
    import time as _t
    _t.sleep(5)  # Đợi 5s để app khởi động xong (giảm từ 60s)
    while binance_client is None:
        # Nếu biết ban chưa hết → đợi đúng thời điểm + 15s buffer
        if _ban_until > 0:
            wait = _ban_until - _t.time() + 15
            if wait > 0:
                mins = wait / 60
                logger.info(
                    f"Ban active, waiting {mins:.1f} min..."
                )
                _t.sleep(wait)
                continue
        logger.info("Background: attempting Binance client init...")
        _get_client()
        if binance_client is None:
            _t.sleep(60)  # Retry sau 60s nếu không parse được ban (giảm từ 300s)
        else:
            logger.info("Background: Binance client ready!")

_init_thread = threading.Thread(
    target=_background_client_init, daemon=True
)
_init_thread.start()


def _safe_float(v, default=0.0):
    """Convert to float safely — handles '', None, and bad strings."""
    try:
        f = float(v)
        return f if f == f else default  # NaN guard
    except (TypeError, ValueError):
        return default


def _calc_balance(account: dict) -> dict:
    """Tính balance từ account dict, fallback sang per-asset khi cần."""
    total = _safe_float(account.get('totalWalletBalance', 0))
    available = _safe_float(account.get('availableBalance', 0))
    upnl = _safe_float(account.get('totalUnrealizedProfit', 0))

    # Fallback: tổng từng asset nếu totalWalletBalance = 0
    if total == 0:
        for asset in account.get('assets', []):
            wb = _safe_float(asset.get('walletBalance', 0))
            if wb > 0:
                total += wb
                available += _safe_float(
                    asset.get('availableBalance',
                               asset.get('marginAvailable', 0))
                )
                upnl += _safe_float(asset.get('unrealizedProfit', 0))
    return {'total': total, 'available': available, 'upnl': upnl}


# ─── Server-side cache ──────────────────────────────────────────────────────
# Giảm số lần gọi Binance API, tránh lỗi -1003 (Too Many Requests)
# Format: _api_cache[key] = {'data': dict, 'ts': float}
_api_cache: dict = {}


def _cache_get(key: str, ttl: float):
    """Trả về cached data nếu còn hạn, ngược lại trả None."""
    entry = _api_cache.get(key)
    if entry and (time.time() - entry['ts']) < ttl:
        return entry['data']
    return None


def _cache_set(key: str, data: dict):
    """Lưu data vào cache."""
    _api_cache[key] = {'data': data, 'ts': time.time()}
# ────────────────────────────────────────────────────────────────────────────


@app.route('/')
def dashboard():
    """Main dashboard"""
    return render_template('dashboard.html')


@app.route('/api/set_mode', methods=['POST'])
def set_trading_mode():
    """Set trading mode (auto/semi-auto/manual)"""
    try:
        data = request.get_json()
        mode = data.get('mode', 'semi-auto')

        if mode not in ['auto', 'semi-auto', 'manual']:
            return jsonify({'success': False, 'error': 'Invalid mode'})

        bot_manager.trading_mode = mode
        bot_manager.add_log(f"🎮 Chế độ trading: {mode.upper()}")

        return jsonify({
            'success': True,
            'mode': mode,
            'message': f'Đã chuyển sang chế độ {mode.upper()}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/get_mode')
def get_trading_mode():
    """Get current trading mode"""
    try:
        return jsonify({
            'success': True,
            'mode': bot_manager.trading_mode
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/market_data')
def get_market_data():
    """Get real-time market data for BTC, ETH, SOL"""
    cached = _cache_get('market_data', 30)
    if cached:
        return jsonify(cached)
    try:
        client = _get_client()
        if not client:
            return jsonify(
                {'success': False,
                 'error': 'Client not initialized'})
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        market_data = {}
        
        for symbol in symbols:
            try:
                # Get current price
                ticker = client.client.futures_ticker(symbol=symbol)
                
                # Get 24h change
                price = float(ticker['lastPrice'])
                change_24h = float(ticker['priceChangePercent'])
                volume_24h = float(ticker['volume'])
                high_24h = float(ticker['highPrice'])
                low_24h = float(ticker['lowPrice'])
                
                # Get recent candles for mini chart (last 50 candles, 5m)
                klines = client.get_klines(symbol, '5m', 50)
                
                candles = []
                if klines:
                    for k in klines[-20:]:  # Last 20 candles for chart
                        candles.append({
                            'time': k[0],
                            'open': float(k[1]),
                            'high': float(k[2]),
                            'low': float(k[3]),
                            'close': float(k[4]),
                            'volume': float(k[5])
                        })
                
                market_data[symbol] = {
                    'price': price,
                    'change_24h': change_24h,
                    'volume_24h': volume_24h,
                    'high_24h': high_24h,
                    'low_24h': low_24h,
                    'candles': candles,
                    'last_update': datetime.now().strftime('%H:%M:%S')
                }
                
            except Exception as e:
                logger.error(f"Error getting data for {symbol}: {e}")
                market_data[symbol] = {
                    'error': str(e),
                    'price': 0,
                    'change_24h': 0
                }
        
        result = {'success': True, 'data': market_data}
        _cache_set('market_data', result)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in market_data endpoint: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/bot_analysis')
def bot_analysis():
    """Get real-time AI analysis for all symbols.
    When bot is running AND has fresh analysis: return bot's signals.
    Otherwise: fallback to independent calculation.
    """
    try:
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        analysis_data = {}

        # =============================================
        # Check if bot has valid cached analysis
        # =============================================
        smart_bot = (
            bot_manager.smart_bot
            if bot_manager and bot_manager.smart_bot
            else None
        )
        _cached = getattr(
            smart_bot, 'latest_analysis', None
        )

        # Only use bot's cache if it has data for ALL symbols
        use_bot_cache = (
            smart_bot
            and smart_bot.is_running
            and _cached
            and all(symbol in _cached and _cached[symbol].get('signal') for symbol in symbols)
        )

        if use_bot_cache:
            for symbol in symbols:
                cached = _cached.get(symbol)
                if cached and cached.get('signal'):
                    analysis_data[symbol] = {
                        'signal': cached.get('signal', 'N/A'),
                        'confidence': round(
                            cached.get('confidence', 0), 1
                        ),
                        'trend': _rsi_trend(cached),
                        'current_price': cached.get(
                            'entry_price', 0
                        ),
                        'tp_price': cached.get('take_profit'),
                        'sl_price': cached.get('stop_loss'),
                        'rsi': round(
                            cached.get('rsi', 50), 1
                        ),
                        'ai_type': cached.get(
                            'ai_type', 'basic'
                        ),
                        'timestamp': cached.get(
                            'timestamp',
                            datetime.now().strftime(
                                '%H:%M:%S'
                            )
                        ),
                    }

            # If we got all symbols, return
            if len(analysis_data) == len(symbols):
                return jsonify({
                    'success': True,
                    'analysis': analysis_data,
                    'bot_status': bot_manager.get_status(),
                    'trading_mode': bot_manager.trading_mode
                })

        # =============================================
        # FALLBACK: Calculate independently
        # (Bot not running OR cache empty/stale)
        # =============================================
        import joblib
        import numpy as np
        from technical_analysis import TechnicalAnalyzer
        from train_ai_improved import (
            prepare_advanced_features,
            get_htf_features_for_training,
            align_features_to_model,
        )
        import pandas as pd

        models = {}
        for symbol in symbols:
            try:
                md = joblib.load(
                    f'models/gradient_boost_{symbol}.pkl'
                )
                models[symbol] = md
            except Exception as e:
                logger.error(
                    f"Failed to load model {symbol}: {e}"
                )

        client = _get_client()
        if not client:
            return jsonify({
                'success': False,
                'error': 'Client not initialized',
                'analysis': {}
            })
        analyzer = TechnicalAnalyzer()

        for symbol in symbols:
            try:
                klines = client.get_klines(
                    symbol, "5m", 100
                )
                if not klines:
                    analysis_data[symbol] = {
                        'signal': 'N/A',
                        'confidence': 0,
                        'error': 'No data'
                    }
                    continue

                df = analyzer.prepare_dataframe(klines)
                df = analyzer.add_basic_indicators(df)
                df = analyzer.add_advanced_indicators(df)

                htf_dfs = get_htf_features_for_training(
                    client, analyzer, symbol
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
                        htf_df = htf_df.sort_values(
                            'timestamp'
                        )
                        df = pd.merge_asof(
                            df, htf_df,
                            on='timestamp',
                            direction='backward'
                        )

                current_price = float(
                    df['close'].iloc[-1]
                )

                if symbol in models:
                    model_data = models[symbol]
                    model = model_data['model']
                    X, feat_names = (
                        prepare_advanced_features(df)
                    )
                    X = align_features_to_model(
                        X, feat_names, model_data
                    )
                    latest_features = X[-1].reshape(1, -1)

                    prediction = model.predict(
                        latest_features
                    )[0]
                    probabilities = model.predict_proba(
                        latest_features
                    )[0]
                    classes = model.classes_

                    prob_map = {}
                    for ci, cls in enumerate(classes):
                        prob_map[int(cls)] = (
                            probabilities[ci]
                        )
                    prob_short = (
                        prob_map.get(-1, 0) * 100
                    )
                    prob_hold = prob_map.get(0, 0) * 100
                    prob_long = prob_map.get(1, 0) * 100

                    class_idx = np.where(
                        classes == prediction
                    )[0][0]
                    confidence = (
                        probabilities[class_idx] * 100
                    )

                    signal_map = {
                        -1: 'SHORT',
                        0: 'HOLD',
                        1: 'LONG',
                    }
                    signal = signal_map[prediction]

                    # Never return HOLD - ALWAYS follow actual market trend
                    rsi = float(df['rsi'].iloc[-1]) if 'rsi' in df.columns else 50
                    price_change = (float(df['close'].iloc[-1]) - float(df['close'].iloc[-5])) / float(df['close'].iloc[-5]) * 100 if len(df) >= 5 else 0

                    # RULE 1: Strong bearish → SHORT
                    if price_change < -0.5 or (price_change < -0.2 and rsi < 45):
                        signal = 'SHORT'
                        confidence = max(prob_short, 60) if prob_short else 60
                    # RULE 2: Strong bullish → LONG
                    elif price_change > 0.5 or (price_change > 0.2 and rsi > 55):
                        signal = 'LONG'
                        confidence = max(prob_long, 60) if prob_long else 60
                    # RULE 3: RSI extreme low (bearish momentum)
                    elif rsi < 40:
                        signal = 'SHORT'
                        confidence = max(prob_short, 55) if prob_short else 55
                    # RULE 4: RSI extreme high (bullish momentum)
                    elif rsi > 60:
                        signal = 'LONG'
                        confidence = max(prob_long, 55) if prob_long else 55
                    # RULE 5: Negative price = SHORT, Positive = LONG
                    elif price_change < 0:
                        signal = 'SHORT'
                        confidence = max(prob_short, 50) if prob_short else 50
                    elif price_change > 0:
                        signal = 'LONG'
                        confidence = max(prob_long, 50) if prob_long else 50
                    # RULE 6: Use RSI as tiebreaker
                    elif rsi < 50:
                        signal = 'SHORT'
                        confidence = max(prob_short, 50) if prob_short else 50
                    else:
                        signal = 'LONG'
                        confidence = max(prob_long, 50) if prob_long else 50

                    sl_pct = 1.5
                    tp_pct = 3.0
                    if signal == 'LONG':
                        sl_price = current_price * (
                            1 - sl_pct / 100
                        )
                        tp_price = current_price * (
                            1 + tp_pct / 100
                        )
                    elif signal == 'SHORT':
                        sl_price = current_price * (
                            1 + sl_pct / 100
                        )
                        tp_price = current_price * (
                            1 - tp_pct / 100
                        )
                    else:
                        sl_price = None
                        tp_price = None

                    rsi = (
                        df['rsi'].iloc[-1]
                        if 'rsi' in df.columns
                        else 50
                    )
                    if rsi > 70:
                        trend = 'Overbought'
                    elif rsi < 30:
                        trend = 'Oversold'
                    elif rsi > 55:
                        trend = 'Bullish'
                    elif rsi < 45:
                        trend = 'Bearish'
                    else:
                        trend = 'Neutral'

                    analysis_data[symbol] = {
                        'signal': signal,
                        'confidence': round(
                            confidence, 1
                        ),
                        'trend': trend,
                        'current_price': current_price,
                        'tp_price': tp_price,
                        'sl_price': sl_price,
                        'rsi': round(rsi, 1),
                        'ai_type': 'basic',
                        'timestamp': (
                            datetime.now().strftime(
                                '%H:%M:%S'
                            )
                        ),
                    }
                else:
                    analysis_data[symbol] = {
                        'signal': 'N/A',
                        'confidence': 0,
                        'current_price': current_price,
                        'error': 'Model not loaded',
                    }

            except Exception as e:
                logger.error(
                    f"Error analyzing {symbol}: {e}"
                )
                analysis_data[symbol] = {
                    'signal': 'ERROR',
                    'confidence': 0,
                    'error': str(e),
                }

        return jsonify({
            'success': True,
            'analysis': analysis_data,
            'bot_status': bot_manager.get_status(),
            'trading_mode': bot_manager.trading_mode
        })

    except Exception as e:
        logger.error(
            f"Error in bot_analysis endpoint: {e}"
        )
        return jsonify({
            'success': False,
            'error': str(e),
            'analysis': {}
        })


def _rsi_trend(signal_data):
    """Helper: derive trend label from cached signal."""
    rsi = signal_data.get('rsi', 50)
    if rsi > 70:
        return 'Overbought'
    if rsi < 30:
        return 'Oversold'
    if rsi > 55:
        return 'Bullish'
    if rsi < 45:
        return 'Bearish'
    return 'Neutral'

@app.route('/api/pause_bot', methods=['POST'])
def pause_bot():
    """Pause bot (keep positions, stop new trades)"""
    try:
        if bot_manager.smart_bot:
            bot_manager.smart_bot.pause()
            bot_manager.add_log("⏸️ Bot paused - keeping existing positions")
            return jsonify({'success': True, 'message': 'Bot paused'})
        return jsonify({'success': False, 'error': 'Bot not running'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/resume_bot', methods=['POST'])
def resume_bot():
    """Resume bot from pause"""
    try:
        if bot_manager.smart_bot:
            bot_manager.smart_bot.resume()
            bot_manager.add_log("▶️ Bot resumed")
            return jsonify({'success': True, 'message': 'Bot resumed'})
        return jsonify({'success': False, 'error': 'Bot not running'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get_preflight_results')
def get_preflight_results():
    """Get pre-flight check results"""
    try:
        if bot_manager.preflight_results:
            return jsonify({
                'success': True,
                'results': bot_manager.preflight_results
            })
        return jsonify({
            'success': True,
            'results': None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/get_pending_signals')
def get_pending_signals():
    """Get pending AI signals (for semi-auto mode)"""
    try:
        if (bot_manager.smart_bot and
                hasattr(bot_manager.smart_bot, 'pending_signals')):
            # Last 10 signals
            signals = bot_manager.smart_bot.pending_signals[-10:]
            return jsonify({
                'success': True,
                'signals': signals
            })
        return jsonify({
            'success': True,
            'signals': []
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/execute_pending_signal', methods=['POST'])
def execute_pending_signal():
    """Execute a pending signal from semi-auto mode"""
    try:
        if not bot_manager.smart_bot:
            return jsonify({'success': False, 'error': 'Bot not running'})
        
        data = request.get_json()
        signal_index = data.get('index', -1)
        
        # Get signal
        if signal_index < 0 or signal_index >= len(bot_manager.smart_bot.pending_signals):
            return jsonify({'success': False, 'error': 'Invalid signal index'})
        
        signal_data = bot_manager.smart_bot.pending_signals[signal_index]
        
        # Execute trade in async loop
        async def execute():
            return await bot_manager.smart_bot.execute_trade(signal_data)
        
        # Run in bot's event loop
        if bot_manager.loop:
            future = asyncio.run_coroutine_threadsafe(execute(), bot_manager.loop)
            success, result = future.result(timeout=10)
            
            if success:
                # Remove from pending
                bot_manager.smart_bot.pending_signals.pop(signal_index)
                return jsonify({'success': True, 'message': 'Signal executed', 'order': str(result)})
            else:
                return jsonify({'success': False, 'error': result})
        
        return jsonify({'success': False, 'error': 'Bot loop not available'})
        
    except Exception as e:
        logger.error(f"Error executing pending signal: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/execute_signal', methods=['POST'])
def execute_signal():
    """Execute AI signal (for semi-auto mode)"""
    try:
        client = _get_client()
        if not client:
            return jsonify({'success': False, 'error': 'Client not initialized'})

        data = request.get_json()
        symbol = data.get('symbol')
        side = data.get('side')  # LONG or SHORT

        if not symbol or not side:
            return jsonify({'success': False, 'error': 'Missing symbol or side'})

        # Execute trade using SmartBotEngine or direct client
        bot_manager.add_log(f"🚀 Executing {side} signal for {symbol}...")
        
        # Use SmartBotEngine if bot is running
        if bot_manager.smart_bot and bot_manager.loop:
            signal_data = {
                'symbol': symbol,
                'signal': side,
                'confidence': data.get('confidence', 75),
                'entry_price': data.get('entry_price', 0),
                'stop_loss': data.get('stop_loss', 0),
                'take_profit': data.get('take_profit', 0),
            }

            async def execute():
                # BYPASS soft filters for MANUAL trades (user explicitly clicked button)
                return await bot_manager.smart_bot.execute_trade(signal_data, bypass_soft_filters=True)
            
            future = asyncio.run_coroutine_threadsafe(execute(), bot_manager.loop)
            success, result = future.result(timeout=15)
            
            if success:
                bot_manager.add_log(f"✅ {side} {symbol} executed successfully")
                return jsonify({'success': True, 'message': f'{side} order for {symbol} executed', 'order': str(result)})
            else:
                return jsonify({'success': False, 'error': str(result)})
        
        # Fallback: direct execution via client (with TP/SL)
        # client was already validated at function start

        try:
            account = client.client.futures_account()
            balance = float(account['totalWalletBalance'])

            # Check minimum balance
            if balance < 1:
                return jsonify({'success': False, 'error': f'Balance too low: ${balance:.2f} (min $1)'})

            position_value = balance * 0.3  # 30% position size

            ticker = client.client.futures_symbol_ticker(symbol=symbol)
            current_price = float(ticker['price'])

            # Check valid price
            if current_price <= 0:
                return jsonify({'success': False, 'error': 'Invalid price from exchange'})

            quantity = position_value / current_price

            # Round quantity to appropriate precision
            exchange_info = client.client.futures_exchange_info()
            symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
            price_precision = 2
            qty_precision = 3
            min_qty = 0.001

            if symbol_info:
                for f in symbol_info['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        min_qty = float(f.get('minQty', 0.001))
                        # Safe precision calculation
                        step_str = str(step_size)
                        if '.' in step_str:
                            qty_precision = len(step_str.rstrip('0').split('.')[-1])
                        else:
                            qty_precision = 0
                        quantity = round(quantity, qty_precision)
                    if f['filterType'] == 'PRICE_FILTER':
                        tick_size = float(f['tickSize'])
                        tick_str = str(tick_size)
                        if '.' in tick_str:
                            price_precision = len(tick_str.rstrip('0').split('.')[-1])

            # Check minimum quantity
            if quantity < min_qty:
                return jsonify({'success': False, 'error': f'Quantity too small: {quantity} (min {min_qty}). Need more balance.'})

            # Check position mode (hedge vs one-way)
            try:
                position_mode = client.client.futures_get_position_mode()
                is_hedge_mode = position_mode.get('dualSidePosition', False)
            except:
                is_hedge_mode = False  # Default to one-way if can't detect

            order_side = 'BUY' if side == 'LONG' else 'SELL'

            # Create order based on position mode
            if is_hedge_mode:
                position_side = 'LONG' if side == 'LONG' else 'SHORT'
                order = client.client.futures_create_order(
                    symbol=symbol,
                    side=order_side,
                    type='MARKET',
                    quantity=quantity,
                    positionSide=position_side
                )
            else:
                # One-way mode: no positionSide
                order = client.client.futures_create_order(
                    symbol=symbol,
                    side=order_side,
                    type='MARKET',
                    quantity=quantity
                )

            # Calculate and place TP/SL (1.5% SL, 3% TP)
            sl_pct = 0.015
            tp_pct = 0.03
            if side == 'LONG':
                sl_price = round(current_price * (1 - sl_pct), price_precision)
                tp_price = round(current_price * (1 + tp_pct), price_precision)
                sl_side = 'SELL'
            else:
                sl_price = round(current_price * (1 + sl_pct), price_precision)
                tp_price = round(current_price * (1 - tp_pct), price_precision)
                sl_side = 'BUY'

            # Place Stop Loss (handle both hedge and one-way mode)
            try:
                sl_params = {
                    'symbol': symbol,
                    'side': sl_side,
                    'type': 'STOP_MARKET',
                    'stopPrice': sl_price,
                    'closePosition': 'true'
                }
                if is_hedge_mode:
                    sl_params['positionSide'] = 'LONG' if side == 'LONG' else 'SHORT'
                client.client.futures_create_order(**sl_params)
                bot_manager.add_log(f"🛡️ SL set @ ${sl_price}")
            except Exception as sl_err:
                bot_manager.add_log(f"⚠️ SL failed: {sl_err}")

            # Place Take Profit (handle both hedge and one-way mode)
            try:
                tp_params = {
                    'symbol': symbol,
                    'side': sl_side,
                    'type': 'TAKE_PROFIT_MARKET',
                    'stopPrice': tp_price,
                    'closePosition': 'true'
                }
                if is_hedge_mode:
                    tp_params['positionSide'] = 'LONG' if side == 'LONG' else 'SHORT'
                client.client.futures_create_order(**tp_params)
                bot_manager.add_log(f"🎯 TP set @ ${tp_price}")
            except Exception as tp_err:
                bot_manager.add_log(f"⚠️ TP failed: {tp_err}")

            bot_manager.add_log(f"✅ {side} {symbol} x{quantity} @ ${current_price:.2f}")
            return jsonify({'success': True, 'message': f'{side} order for {symbol} executed with TP/SL', 'order': order})
        except Exception as ex:
            return jsonify({'success': False, 'error': str(ex)})
    except Exception as e:
        logger.error(f"Error executing signal: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/close_position', methods=['POST'])
def close_single_position():
    """Close a specific position (supports partial close via percent param)"""
    try:
        if not binance_client:
            return jsonify({'success': False, 'error': 'Client not initialized'})

        data = request.get_json()
        symbol = data.get('symbol')
        close_percent = data.get('percent', 100)  # Default: close 100%

        if not symbol:
            return jsonify({'success': False, 'error': 'Missing symbol'})

        # Check position mode (hedge vs one-way)
        try:
            position_mode = binance_client.client.futures_get_position_mode()
            is_hedge_mode = position_mode.get('dualSidePosition', False)
        except:
            is_hedge_mode = False  # Default to one-way

        # Get current position
        positions = binance_client.client.futures_position_information(symbol=symbol)

        for pos in positions:
            if float(pos['positionAmt']) != 0:
                side = 'SELL' if float(pos['positionAmt']) > 0 else 'BUY'
                position_side = 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT'
                full_qty = abs(float(pos['positionAmt']))

                # Calculate quantity to close based on percent
                close_qty = full_qty * (close_percent / 100)

                # Round to appropriate precision
                exchange_info = binance_client.client.futures_exchange_info()
                symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
                if symbol_info:
                    for f in symbol_info['filters']:
                        if f['filterType'] == 'LOT_SIZE':
                            step_size = float(f['stepSize'])
                            step_str = str(step_size)
                            if '.' in step_str:
                                qty_precision = len(step_str.rstrip('0').split('.')[-1])
                            else:
                                qty_precision = 0
                            close_qty = round(close_qty, qty_precision)
                            break

                if close_qty <= 0:
                    return jsonify({'success': False, 'error': 'Quantity too small to close'})

                # Close position based on mode
                if is_hedge_mode:
                    order = binance_client.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type='MARKET',
                        quantity=close_qty,
                        positionSide=position_side
                    )
                else:
                    # One-way mode: no positionSide
                    order = binance_client.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type='MARKET',
                        quantity=close_qty
                    )

                bot_manager.add_log(f"✅ Đóng {close_percent}% lệnh {symbol} (qty: {close_qty})")

                return jsonify({
                    'success': True,
                    'message': f'Closed {close_percent}% of {symbol} position',
                    'order': order
                })

        return jsonify({'success': False, 'error': 'No position found'})

    except Exception as e:
        logger.error(f"Error closing position: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/emergency_close_all', methods=['POST'])
def emergency_close_all():
    """Emergency close all positions"""
    try:
        # Use SmartBotEngine's emergency close if bot is running
        if bot_manager.smart_bot and bot_manager.loop:
            async def emergency():
                return await bot_manager.smart_bot.emergency_close_all()

            future = asyncio.run_coroutine_threadsafe(emergency(), bot_manager.loop)
            closed_count = future.result(timeout=30)

            return jsonify({
                'success': True,
                'closed_count': closed_count,
                'message': f'Emergency: Closed {closed_count} positions'
            })

        # Fallback to direct close if bot not running
        if not binance_client:
            return jsonify({'success': False, 'error': 'Client not initialized'})

        # Check position mode (hedge vs one-way)
        try:
            position_mode = binance_client.client.futures_get_position_mode()
            is_hedge_mode = position_mode.get('dualSidePosition', False)
        except:
            is_hedge_mode = False  # Default to one-way

        # Get all positions
        positions = binance_client.client.futures_position_information()
        closed_count = 0

        for pos in positions:
            position_amt = float(pos['positionAmt'])
            if position_amt != 0:
                symbol = pos['symbol']
                side = 'SELL' if position_amt > 0 else 'BUY'
                position_side = 'LONG' if position_amt > 0 else 'SHORT'
                qty = abs(position_amt)

                try:
                    # Close position based on mode
                    if is_hedge_mode:
                        order = binance_client.client.futures_create_order(
                            symbol=symbol,
                            side=side,
                            type='MARKET',
                            quantity=qty,
                            positionSide=position_side
                        )
                    else:
                        # One-way mode: no positionSide
                        order = binance_client.client.futures_create_order(
                            symbol=symbol,
                            side=side,
                            type='MARKET',
                            quantity=qty
                        )
                    closed_count += 1
                    bot_manager.add_log(f"🚨 EMERGENCY: Closed {symbol}")
                except Exception as e:
                    logger.error(f"Error closing {symbol}: {e}")

        return jsonify({
            'success': True,
            'closed_count': closed_count,
            'message': f'Closed {closed_count} positions'
        })

    except Exception as e:
        logger.error(f"Error in emergency close: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/manual_trade', methods=['POST'])
def manual_trade():
    """Execute manual trade"""
    try:
        if not binance_client:
            return jsonify({'success': False, 'error': 'Client not initialized'})
        
        data = request.get_json()
        symbol = data.get('symbol')
        side = data.get('side')  # LONG or SHORT
        size_percent = data.get('size_percent', 30)
        
        if not symbol or not side:
            return jsonify({'success': False, 'error': 'Missing symbol or side'})
        
        # Get account balance
        account = binance_client.client.futures_account()
        balance = float(account['totalWalletBalance'])
        
        # Calculate position size
        position_value = balance * (size_percent / 100)
        
        # Get current price
        ticker = binance_client.client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        
        # Calculate quantity
        quantity = position_value / current_price
        
        # Get symbol info for precision
        exchange_info = binance_client.client.futures_exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
        
        if symbol_info:
            # Get quantity precision
            qty_precision = 0
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    qty_precision = len(str(step_size).rstrip('0').split('.')[-1])
                    break
            
            # Round quantity
            quantity = round(quantity, qty_precision)
        
        # Place order
        order_side = 'BUY' if side == 'LONG' else 'SELL'
        position_side = 'LONG' if side == 'LONG' else 'SHORT'  # For Hedge Mode
        order = binance_client.client.futures_create_order(
            symbol=symbol,
            side=order_side,
            type='MARKET',
            quantity=quantity,
            positionSide=position_side  # Required for Hedge Mode
        )
        
        bot_manager.add_log(f"📊 MANUAL: {side} {symbol} x{quantity} @ ${current_price:.2f}")
        
        return jsonify({
            'success': True,
            'message': f'Opened {side} position',
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': current_price,
            'order': order
        })
        
    except Exception as e:
        logger.error(f"Error in manual trade: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/save_risk_settings', methods=['POST'])
def save_risk_settings():
    """Save risk management settings"""
    try:
        data = request.get_json()
        
        # Store in bot manager
        bot_manager.risk_settings = data
        
        bot_manager.add_log(f"⚙️ Risk settings updated: Max leverage {data['maxLeverage']}x, Max size {data['maxPositionSize']}%")
        
        return jsonify({
            'success': True,
            'message': 'Risk settings saved'
        })
    except Exception as e:
        logger.error(f"Error saving risk settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/move_sl_breakeven', methods=['POST'])
def move_sl_breakeven():
    """Move stop loss to breakeven"""
    try:
        if not binance_client:
            return jsonify({'success': False, 'error': 'Client not initialized'})
        
        data = request.get_json()
        symbol = data.get('symbol')
        
        if not symbol:
            return jsonify({'success': False, 'error': 'Missing symbol'})
        
        # Get current position
        positions = binance_client.client.futures_position_information(symbol=symbol)
        
        for pos in positions:
            position_amt = float(pos['positionAmt'])
            if position_amt != 0:
                entry_price = float(pos['entryPrice'])
                
                # Set stop loss at entry price
                side = 'SELL' if position_amt > 0 else 'BUY'
                position_side = 'LONG' if position_amt > 0 else 'SHORT'  # For Hedge Mode
                
                # Cancel existing stop loss orders
                open_orders = binance_client.client.futures_get_open_orders(symbol=symbol)
                for order in open_orders:
                    if order['type'] == 'STOP_MARKET':
                        binance_client.client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                
                # Place new stop loss at breakeven
                order = binance_client.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='STOP_MARKET',
                    stopPrice=entry_price,
                    closePosition=True,
                    positionSide=position_side  # Required for Hedge Mode
                )
                
                bot_manager.add_log(f"🛡️ Moved SL to breakeven for {symbol} @ ${entry_price:.2f}")
                
                return jsonify({
                    'success': True,
                    'message': f'Stop loss moved to breakeven @ ${entry_price:.2f}',
                    'order': order
                })
        
        return jsonify({'success': False, 'error': 'No position found'})
        
    except Exception as e:
        logger.error(f"Error moving SL: {e}")
        return jsonify({'success': False, 'error': str(e)})

def _get_sym_precision(symbol):
    """Return (price_precision, qty_precision) for a symbol"""
    try:
        info = binance_client.client.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] != symbol:
                continue
            price_prec = 2
            qty_prec = 3
            for f in s['filters']:
                if f['filterType'] == 'PRICE_FILTER':
                    tick = float(f['tickSize'])
                    price_prec = (
                        len(f['tickSize'].rstrip('0').split('.')[-1])
                        if '.' in f['tickSize'] else 0
                    )
                if f['filterType'] == 'LOT_SIZE':
                    step = f['stepSize']
                    qty_prec = (
                        len(step.rstrip('0').split('.')[-1])
                        if '.' in step else 0
                    )
            return price_prec, qty_prec
    except Exception:
        pass
    return 2, 3


def _get_conditional_open_orders(symbol=None):
    """Get open conditional (algo) orders.
    After 2025-12-09 python-binance routes STOP_MARKET/TAKE_PROFIT_MARKET
    to the algo order endpoint; use conditional=True to query them.
    """
    try:
        params = {'conditional': True}
        if symbol:
            params['symbol'] = symbol
        result = binance_client.client.futures_get_open_orders(**params)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.warning(f"Could not fetch conditional orders: {e}")
        return []


def _cancel_conditional_order(symbol, algo_id):
    """Cancel a conditional (algo) order by algoId.
    Passing algoId automatically triggers the algo order path.
    """
    return binance_client.client.futures_cancel_order(
        symbol=symbol, algoId=algo_id
    )


@app.route('/api/cancel_all_sltp', methods=['POST'])
def cancel_all_sltp():
    """Cancel ALL pending SL/TP conditional orders across all symbols"""
    try:
        if not binance_client:
            return jsonify({'success': False, 'error': 'Not initialized'})
        # Binance testnet uses Conditional Order API for STOP_MARKET / TP_MARKET
        algo_orders = _get_conditional_open_orders()
        cancelled = 0
        errors = []
        sltp_types = ('STOP_MARKET', 'TAKE_PROFIT_MARKET')
        for o in algo_orders:
            if o.get('orderType') not in sltp_types:
                continue
            try:
                _cancel_conditional_order(o['symbol'], o['algoId'])
                cancelled += 1
            except Exception as e:
                errors.append(str(e))
        bot_manager.add_log(f'🗑️ Cancelled {cancelled} SL/TP orders')
        return jsonify({
            'success': True,
            'cancelled': cancelled,
            'errors': errors
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/force_sltp', methods=['POST'])
def force_sltp():
    """Cancel all stale SL/TP, then place 1 clean SL+TP per position"""
    try:
        if not binance_client:
            return jsonify({'success': False, 'error': 'Client not initialized'})

        # Step 1: Cancel ALL pending SL/TP conditional orders first
        try:
            algo_orders = _get_conditional_open_orders()
            sltp_types = ('STOP_MARKET', 'TAKE_PROFIT_MARKET')
            cancelled_n = 0
            for o in algo_orders:
                if o.get('orderType') in sltp_types:
                    try:
                        _cancel_conditional_order(o['symbol'], o['algoId'])
                        cancelled_n += 1
                    except Exception:
                        pass
            logger.info(f'Cleared {cancelled_n} stale SL/TP orders')
        except Exception as e:
            logger.warning(f'Cancel stale orders warning: {e}')

        # Step 2: Get risk settings
        sl_pct = 1.5
        tp_pct = 3.0
        if (bot_manager.smart_bot and
                hasattr(bot_manager.smart_bot, 'risk_settings')):
            rs = bot_manager.smart_bot.risk_settings
            sl_pct = rs.get('sl_percentage', 1.5)
            tp_pct = rs.get('tp_percentage', 3.0)

        # Step 3: Place fresh SL+TP per position
        positions = binance_client.client.futures_position_information()
        results = []
        for pos in positions:
            amt = float(pos['positionAmt'])
            if amt == 0:
                continue
            sym = pos['symbol']
            entry = float(pos['entryPrice'])
            mark = float(pos.get('markPrice', entry))
            is_long = amt > 0
            qty = abs(amt)
            side = 'LONG' if is_long else 'SHORT'
            pos_side = 'LONG' if is_long else 'SHORT'
            order_side = 'SELL' if is_long else 'BUY'

            # Get correct precision for this symbol
            price_prec, qty_prec = _get_sym_precision(sym)
            qty = round(qty, qty_prec)

            # Calculate SL from entry (risk reference)
            # Calculate TP from MARK price (avoid immediate trigger)
            if is_long:
                sl = round(entry * (1 - sl_pct / 100), price_prec)
                tp = round(mark * (1 + tp_pct / 100), price_prec)
                # Safety: SL must be below mark price, TP above mark
                if sl >= mark:
                    sl = round(mark * (1 - sl_pct / 100), price_prec)
            else:
                sl = round(entry * (1 + sl_pct / 100), price_prec)
                tp = round(mark * (1 - tp_pct / 100), price_prec)
                # Safety: SL must be above mark price, TP below mark
                if sl <= mark:
                    sl = round(mark * (1 + sl_pct / 100), price_prec)

            sl_placed = False
            tp_placed = False

            # Place SL
            try:
                binance_client.client.futures_create_order(
                    symbol=sym,
                    side=order_side,
                    type='STOP_MARKET',
                    stopPrice=sl,
                    quantity=qty,
                    positionSide=pos_side
                )
                sl_placed = True
            except Exception as e:
                logger.error(f'SL error {sym}: {e}')

            # Place TP
            try:
                binance_client.client.futures_create_order(
                    symbol=sym,
                    side=order_side,
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=tp,
                    quantity=qty,
                    positionSide=pos_side
                )
                tp_placed = True
            except Exception as e:
                logger.error(f'TP error {sym}: {e}')

            # Update bot engine
            if (bot_manager.smart_bot and
                    sym in bot_manager.smart_bot.positions):
                bot_manager.smart_bot.positions[sym]['stop_loss'] = sl
                bot_manager.smart_bot.positions[sym]['take_profit'] = tp

            results.append({
                'symbol': sym,
                'side': side,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'sl_placed': sl_placed,
                'tp_placed': tp_placed
            })
            bot_manager.add_log(
                f'🛡️ SL/TP set: {side} {sym} '
                f'entry=${entry:.2f} '
                f'SL=${sl:.{price_prec}f} '
                f'TP=${tp:.{price_prec}f}'
            )

        return jsonify({
            'success': True,
            'count': len(results),
            'positions': results
        })

    except Exception as e:
        logger.error(f'force_sltp error: {e}')
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/open_orders')
def get_open_orders():
    """Get open orders (regular + conditional algo orders)"""
    try:
        if not binance_client:
            return jsonify({'success': False, 'error': 'Not initialized'})

        # Demo mode: return empty orders
        if hasattr(binance_client, 'demo_mode') and binance_client.demo_mode:
            return jsonify({'success': True, 'orders': []})

        order_list = []

        # Regular orders (limit, market, etc.)
        try:
            regular = binance_client.client.futures_get_open_orders()
            for o in regular:
                order_list.append({
                    'orderId': o['orderId'],
                    'algoId': None,
                    'symbol': o['symbol'],
                    'side': o['side'],
                    'type': o['type'],
                    'origQty': o.get('origQty', '0'),
                    'quantity': float(o.get('origQty', 0)),
                    'price': float(o['price']) if o.get('price') else 0,
                    'stopPrice': (
                        float(o['stopPrice']) if o.get('stopPrice') else 0
                    ),
                    'status': o['status'],
                    'orderSource': 'regular'
                })
        except Exception as e:
            logger.warning(f"Regular open orders error: {e}")

        # Conditional (algo) orders — what Binance testnet uses for
        # STOP_MARKET / TAKE_PROFIT_MARKET
        algo_orders = _get_conditional_open_orders()
        for o in algo_orders:
            order_list.append({
                'orderId': None,
                'algoId': o.get('algoId'),
                'symbol': o['symbol'],
                'side': o['side'],
                'type': o.get('orderType', o.get('algoType', '')),
                'origQty': o.get('quantity', '0'),
                'quantity': float(o.get('quantity', 0)),
                'price': float(o.get('price', 0) or 0),
                'stopPrice': float(o.get('triggerPrice', 0) or 0),
                'status': o.get('algoStatus', 'UNKNOWN'),
                'orderSource': 'conditional'
            })

        return jsonify({'success': True, 'orders': order_list})

    except Exception as e:
        logger.error(f"Error getting open orders: {e}")
        return jsonify({'success': False, 'orders': [], 'error': str(e)})

@app.route('/api/cancel_order', methods=['POST'])
def cancel_order():
    """Cancel an open order"""
    try:
        if not binance_client:
            return jsonify({'success': False, 'error': 'Client not initialized'})
        
        data = request.get_json()
        order_id = data.get('orderId')
        symbol = data.get('symbol')
        
        if not order_id or not symbol:
            return jsonify({'success': False, 'error': 'Missing orderId or symbol'})
        
        # Cancel order
        result = binance_client.client.futures_cancel_order(symbol=symbol, orderId=order_id)
        
        bot_manager.add_log(f"❌ Cancelled order {order_id} for {symbol}")
        
        return jsonify({
            'success': True,
            'message': f'Order cancelled',
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/performance_stats')
def get_performance_stats():
    """Get real performance statistics from bot engine"""
    try:
        # Try to get live stats from running bot
        if bot_manager.smart_bot:
            bot = bot_manager.smart_bot
            today_trades = bot.today_trades
            today_wins = bot.today_wins
            today_pnl = bot.today_pnl
            win_rate = (
                (today_wins / today_trades * 100)
                if today_trades > 0 else 0
            )

            # Drawdown info
            peak = bot.peak_balance
            account = bot.client.client.futures_account()
            balance = float(account['totalWalletBalance'])
            dd_pct = (
                (peak - balance) / peak * 100
                if peak > 0 else 0
            )

            # Position monitor info
            tracked = len(bot.positions)
            be_count = sum(
                1 for p in bot.positions.values()
                if p.get('breakeven_moved', False)
            )
            trail_count = sum(
                1 for p in bot.positions.values()
                if p.get('trailing_activated', False)
            )

            return jsonify({
                'success': True,
                'today': {
                    'trades': today_trades,
                    'wins': today_wins,
                    'winrate': round(win_rate, 1),
                    'pnl': round(today_pnl, 2),
                    'maxDD': round(dd_pct, 2)
                },
                'monitor': {
                    'tracked_positions': tracked,
                    'breakeven_active': be_count,
                    'trailing_active': trail_count,
                    'peak_balance': round(peak, 2),
                    'current_drawdown': round(dd_pct, 2)
                },
                'risk_settings': {
                    'trailing_pct': bot.risk_settings.get(
                        'trailing_stop_pct', 0
                    ),
                    'breakeven_pct': bot.risk_settings.get(
                        'breakeven_trigger_pct', 0
                    ),
                    'partial_tp': bot.risk_settings.get(
                        'partial_tp_enabled', False
                    ),
                    'min_adx': bot.risk_settings.get(
                        'min_adx_trend', 0
                    ),
                    'max_dd': bot.risk_settings.get(
                        'max_drawdown_pct', 0
                    ),
                    'symbol_leverage': bot.risk_settings.get(
                        'symbol_leverage', {}
                    )
                }
            })

        # Fallback: load from trade history file
        import json as json_mod
        history_path = 'models/trade_history.json'
        if os.path.exists(history_path):
            with open(history_path, 'r') as f:
                history = json_mod.load(f)
            trades = history.get('trades', [])
            total = len(trades)
            wins = sum(
                1 for t in trades if t.get('pnl', 0) > 0
            )
            wr = wins / total * 100 if total > 0 else 0
            total_pnl = sum(
                t.get('pnl', 0) for t in trades
            )
            return jsonify({
                'success': True,
                'today': {
                    'trades': total,
                    'wins': wins,
                    'winrate': round(wr, 1),
                    'pnl': round(total_pnl, 2),
                    'maxDD': 0
                },
                'monitor': {
                    'tracked_positions': 0,
                    'breakeven_active': 0,
                    'trailing_active': 0,
                    'peak_balance': 0,
                    'current_drawdown': 0
                },
                'risk_settings': {}
            })

        return jsonify({
            'success': True,
            'today': {
                'trades': 0, 'wins': 0,
                'winrate': 0, 'pnl': 0, 'maxDD': 0
            },
            'monitor': {
                'tracked_positions': 0,
                'breakeven_active': 0,
                'trailing_active': 0,
                'peak_balance': 0,
                'current_drawdown': 0
            },
            'risk_settings': {}
        })

    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/run_backtest', methods=['POST'])
def run_backtest_api():
    """Run backtest from dashboard"""
    try:
        from backtest import Backtester

        data = request.get_json() or {}
        symbol = data.get('symbol', None)
        num_candles = data.get('num_candles', 500)
        leverage = data.get('leverage', 15)

        bt = Backtester(initial_balance=10000)

        if symbol:
            result = bt.run_backtest(
                symbol=symbol,
                num_candles=num_candles,
                leverage=leverage,
                sl_pct=1.5, tp_pct=3.0,
                trailing_pct=0.8,
                breakeven_pct=1.0,
                min_confidence=70,
                min_adx=20,
                position_size_pct=30,
            )
            results = {symbol: result} if result else {}
        else:
            results = bt.run_full_backtest(
                num_candles=num_candles,
                leverage=leverage,
                sl_pct=1.5, tp_pct=3.0,
                trailing_pct=0.8,
                breakeven_pct=1.0,
                min_confidence=70,
                min_adx=20,
                position_size_pct=30,
            )

        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/bot_engine_status')
def bot_engine_status():
    """Get detailed v2 bot engine status"""
    try:
        if not bot_manager.smart_bot:
            return jsonify({
                'success': True,
                'running': False,
                'engine': None
            })

        bot = bot_manager.smart_bot
        positions_detail = {}

        for sym, pos in bot.positions.items():
            positions_detail[sym] = {
                'signal': pos.get('signal'),
                'entry_price': pos.get('entry_price'),
                'stop_loss': pos.get('stop_loss'),
                'take_profit': pos.get('take_profit'),
                'breakeven_moved': pos.get(
                    'breakeven_moved', False
                ),
                'trailing_activated': pos.get(
                    'trailing_activated', False
                ),
                'highest_price': pos.get('highest_price'),
                'lowest_price': pos.get('lowest_price'),
                'partial_tp_hit': pos.get(
                    'partial_tp_hit', []
                ),
                'entry_time': str(
                    pos.get('entry_time', '')
                ),
            }

        atr_info = {}
        for sym, atr in bot.atr_history.items():
            atr_info[sym] = {
                'current': round(atr.get('current', 0), 4),
                'average': round(atr.get('average', 0), 4),
                'ratio': round(atr.get('ratio', 1), 2),
            }

        return jsonify({
            'success': True,
            'running': bot.is_running,
            'paused': bot.is_paused,
            'mode': bot.mode,
            'engine': {
                'today_trades': bot.today_trades,
                'today_wins': bot.today_wins,
                'today_pnl': round(bot.today_pnl, 2),
                'peak_balance': round(
                    bot.peak_balance, 2
                ),
                'positions_tracked': positions_detail,
                'atr_history': atr_info,
                'pending_signals': len(
                    bot.pending_signals
                ),
                'models_loaded': list(
                    bot.models.keys()
                ),
                'risk_settings': bot.risk_settings,
            }
        })
    except Exception as e:
        logger.error(f"Engine status error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/test')
def test_page():
    """Test page for API debugging"""
    return jsonify({
        'status': 'ok',
        'message': 'Dashboard API is running',
        'endpoints': [
            '/api/status', '/api/start', '/api/stop',
            '/api/market_data', '/api/bot_analysis',
            '/api/balance', '/api/portfolio', '/api/positions',
            '/api/trade_history', '/api/logs', '/api/clear_logs',
            '/api/performance_stats', '/api/bot_engine_status'
        ]
    })


@app.route('/api/myip')
def get_my_ip():
    """Temporary: get server outbound IP for Binance whitelist"""
    try:
        import requests as _req
        ip = _req.get('https://ifconfig.me', timeout=5).text.strip()
        return jsonify({'server_ip': ip})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/status')
def get_status():
    """Get bot status"""
    try:
        is_running = bot_manager.is_running()
        return jsonify({
            'success': True,
            'running': is_running,
            'status': 'Running' if is_running else 'Stopped',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/positions')
def get_positions():
    """Get real-time positions with PnL and ROE"""
    cached = _cache_get('positions', 10)
    if cached:
        return jsonify(cached)
    try:
        client = _get_client()
        if client is None:
            return jsonify({
                'success': False,
                'error': 'Binance client not initialized',
                'positions': [],
                'count': 0
            }), 500
        
        # Get positions using method that supports demo mode
        positions = client.get_open_positions()

        # --- Fetch open algo orders to extract SL/TP per symbol ---
        # After 2025-12-09 STOP_MARKET/TAKE_PROFIT_MARKET → algo orders
        # Use conditional=True; fields are triggerPrice and orderType
        sl_map = {}  # (symbol, positionSide) -> stop_price
        tp_map = {}  # (symbol, positionSide) -> tp_price
        try:
            if not client.is_demo_mode:
                algo_orders = (
                    client.client
                    .futures_get_open_orders(conditional=True)
                )
                for o in algo_orders:
                    sym = o['symbol']
                    sp = float(o.get('triggerPrice', 0))
                    if sp <= 0:
                        continue
                    order_type = o.get('orderType', '')
                    pos_side = o.get('positionSide', 'BOTH')
                    key = (sym, pos_side)
                    if order_type == 'STOP_MARKET':
                        # Keep only one SL per position — first seen is fine
                        if key not in sl_map:
                            sl_map[key] = sp
                    elif order_type == 'TAKE_PROFIT_MARKET':
                        if key not in tp_map:
                            tp_map[key] = sp
        except Exception:
            pass

        # --- Also try bot engine tracked positions as fallback ---
        engine_sl = {}
        engine_tp = {}
        try:
            if bot_manager.smart_bot:
                for sym, p in bot_manager.smart_bot.positions.items():
                    if p.get('stop_loss'):
                        engine_sl[sym] = float(p['stop_loss'])
                    if p.get('take_profit'):
                        engine_tp[sym] = float(p['take_profit'])
        except Exception:
            pass

        active_positions = []

        for pos in positions:
            position_amt = float(pos.get('positionAmt', 0))
            if position_amt != 0:
                # Calculate values
                entry_price = float(pos.get('entryPrice', 0))
                mark_price = float(pos.get('markPrice', 0))
                unrealized_pnl = float(pos.get('unRealizedProfit', 0))

                # Calculate ROE percentage
                if entry_price > 0:
                    price_change = mark_price - entry_price
                    roe_percent = (price_change / entry_price) * 100
                    if position_amt < 0:  # Short position
                        roe_percent = -roe_percent
                else:
                    roe_percent = 0

                # Determine position side
                side = "LONG" if position_amt > 0 else "SHORT"
                sym = pos.get('symbol', 'UNKNOWN')
                liq_price = float(pos.get('liquidationPrice', 0))

                # If Binance returns 0 (cross margin), estimate from leverage
                if liq_price == 0 and entry_price > 0:
                    try:
                        leverage = int(pos.get('leverage', 10)) or 10
                        # maintenance margin ≈ 0.5% for most symbols
                        maint = 0.005
                        if position_amt > 0:  # LONG
                            liq_price = round(
                                entry_price * (1 - 1 / leverage + maint), 2
                            )
                        else:  # SHORT
                            liq_price = round(
                                entry_price * (1 + 1 / leverage - maint), 2
                            )
                    except Exception:
                        liq_price = 0

                # SL/TP: algo orders keyed by (sym, LONG/SHORT), fallback to engine
                key = (sym, side)
                stop_loss = sl_map.get(
                    key, sl_map.get((sym, 'BOTH'),
                    engine_sl.get(sym, 0))
                )
                take_profit = tp_map.get(
                    key, tp_map.get((sym, 'BOTH'),
                    engine_tp.get(sym, 0))
                )

                active_positions.append({
                    'symbol': sym,
                    'side': side,
                    'size': abs(position_amt),
                    'entryPrice': entry_price,
                    'markPrice': mark_price,
                    'liquidationPrice': liq_price,
                    'stopLoss': stop_loss,
                    'takeProfit': take_profit,
                    'pnl': unrealized_pnl,
                    'roe': round(roe_percent, 2),
                    'percentage': 0,
                    'updateTime': pos.get(
                        'updateTime',
                        int(datetime.now().timestamp() * 1000)
                    )
                })
        
        result = {
            'success': True,
            'positions': active_positions,
            'count': len(active_positions),
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        _cache_set('positions', result)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in get_positions: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'positions': [],
            'count': 0
        }), 500

@app.route('/api/portfolio')
def get_portfolio_summary():
    """Get portfolio summary with total PnL"""
    cached = _cache_get('portfolio', 30)
    if cached:
        return jsonify(cached)
    try:
        client = _get_client()
        if client is None:
            return jsonify({
                'success': False,
                'error': 'Binance client not initialized'
            }), 503

        # Get account info
        account_info = client.get_account_info()
        
        # Calculate total values (with per-asset fallback for USDC collateral)
        bal = _calc_balance(account_info)
        total_wallet_balance = bal['total']
        total_unrealized_pnl = bal['upnl']
        total_margin_balance = (
            _safe_float(
                account_info.get('totalMarginBalance'),
                total_wallet_balance
            ) or total_wallet_balance
        )

        # Fallback: if account-level totalUnrealizedProfit is 0 but there are
        # positions, sum per-position unRealizedProfit for a more accurate value.
        if total_unrealized_pnl == 0:
            try:
                open_positions = client.get_open_positions()
                summed = sum(
                    _safe_float(p.get('unRealizedProfit', 0))
                    for p in open_positions
                    if _safe_float(p.get('positionAmt', 0)) != 0
                )
                if summed != 0:
                    total_unrealized_pnl = summed
            except Exception:
                pass

        # Get positions for count - use the method that supports demo mode
        positions = client.get_open_positions()
        active_count = len([
            p for p in positions
            if _safe_float(p.get('positionAmt', 0)) != 0
        ])
        
        result = {
            'success': True,
            'totalWalletBalance': total_wallet_balance,
            'totalUnrealizedPnL': total_unrealized_pnl,
            'totalMarginBalance': total_margin_balance,
            'activePositions': active_count,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        _cache_set('portfolio', result)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in get_portfolio_summary: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/start', methods=['POST'])
def start_bot():
    """Start the trading bot"""
    try:
        result = bot_manager.start_bot()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error starting bot: {e}'
        }), 500

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Stop the trading bot"""
    try:
        result = bot_manager.stop_bot()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error stopping bot: {e}'
        }), 500

@app.route('/api/restart_bot', methods=['POST'])
def restart_bot():
    """Restart the trading bot (stop then start)"""
    try:
        bot_manager.add_log("🔄 Restarting bot...")
        stop_result = bot_manager.stop_bot()
        import time
        time.sleep(2)  # Wait for clean shutdown
        start_result = bot_manager.start_bot()
        return jsonify({
            'success': start_result.get('success', False),
            'message': f"Stop: {stop_result.get('message', '')} → Start: {start_result.get('message', '')}"
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error restarting bot: {e}'
        }), 500

@app.route('/api/restart_server', methods=['POST'])
def restart_server():
    """Restart the entire server process (systemd or direct)"""
    import subprocess
    try:
        # Check if running under systemd
        result = subprocess.run(
            ['systemctl', 'is-active', 'bot-ai'],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip() == 'active':
            bot_manager.add_log("🔄 Restarting server via systemd...")
            subprocess.Popen(
                ['sudo', 'systemctl', 'restart', 'bot-ai'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return jsonify({
                'success': True,
                'message': 'Server restarting via systemd... Page will reload shortly.'
            })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # Not on systemd, fall through

    # Fallback: restart the process itself
    try:
        bot_manager.add_log("🔄 Restarting server process...")
        import sys
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Cannot restart server: {e}. Please restart manually.'
        }), 500

@app.route('/api/balance')
def check_balance():
    """Check account balance"""
    cached = _cache_get('balance', 30)
    if cached:
        return jsonify(cached)
    client = _get_client()
    if not client:
        return jsonify({
            'success': False,
            'error': 'Client not initialized – check API key / IP whitelist'
        }), 503
    try:
        account = client.client.futures_account(recvWindow=60000)
        bal = _calc_balance(account)
        result = {
            'success': True,
            'data': {
                'total_balance': round(bal['total'], 4),
                'available': round(bal['available'], 4),
                'unrealized_pnl': round(bal['upnl'], 4)
            },
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        _cache_set('balance', result)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in /api/balance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usdc_balance')
def check_usdc():
    """Check USDC balance"""
    try:
        client = _get_client()
        if not client:
            return jsonify({'success': False, 'error': 'Client not initialized'}), 500

        if client.is_demo_mode:
            # Demo mode: return demo balance
            return jsonify({
                'success': True,
                'data': {
                    'futures': '0.000000 USDC',
                    'spot': f'{client.demo_account.balance:.6f} USDC',
                    'total': f'{client.demo_account.balance:.6f} USDC',
                    'sufficient': True
                },
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })

        # Real mode: get USDC balance from futures account
        account = client.client.futures_account()
        assets = account.get('assets', [])
        usdc_asset = next((a for a in assets if a['asset'] == 'USDC'), None)

        if usdc_asset:
            wallet_bal = float(usdc_asset.get('walletBalance', 0))
            return jsonify({
                'success': True,
                'data': {
                    'futures': f'{wallet_bal:.6f} USDC',
                    'spot': '0.000000 USDC',
                    'total': f'{wallet_bal:.6f} USDC',
                    'sufficient': wallet_bal > 10
                },
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })

        return jsonify({
            'success': True,
            'data': {
                'futures': '0.000000 USDC',
                'spot': '0.000000 USDC',
                'total': '0.000000 USDC',
                'sufficient': False
            },
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/test_connection')
def test_connection():
    """Test Binance API connection"""
    try:
        client = _get_client()
        if client:
            # Try to get server time - simple API call
            server_time = client.client.get_server_time()
            mode = "Paper Trading" if client.is_demo_mode else "Live Trading"
            
            return jsonify({
                'success': True,
                'connected': True,
                'message': 'API connection successful',
                'mode': mode,
                'server_time': server_time['serverTime'],
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
        else:
            return jsonify({
                'success': False,
                'connected': False,
                'message': 'Binance client not initialized'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'connected': False,
            'error': str(e)
        }), 500

@app.route('/api/logs')
def get_logs():
    """Get bot logs"""
    try:
        logs = bot_manager.get_logs()
        return jsonify({
            'success': True,
            'logs': logs,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/debug_status')
def debug_status():
    """Debug endpoint - xem trạng thái client, ban, env vars"""
    import time as _t
    now = _t.time()
    env_api = os.environ.get('BINANCE_API_KEY', '')
    env_secret = os.environ.get('BINANCE_SECRET_KEY', '')
    env_testnet = os.environ.get('BINANCE_TESTNET', 'NOT SET')

    # Test Binance API trực tiếp
    api_test = "not tested"
    try:
        import requests as _req
        r = _req.get(
            "https://fapi.binance.com/fapi/v1/time",
            timeout=5
        )
        api_test = r.json()
    except Exception as e:
        api_test = f"error: {e}"

    return jsonify({
        'code_version': 'v3-smart-ban',
        'client_initialized': binance_client is not None,
        'ban_until': _ban_until,
        'ban_remaining_s': max(0, _ban_until - now),
        'last_retry': _client_last_retry,
        'retry_cooldown_remaining': max(
            0, _CLIENT_RETRY_COOLDOWN - (now - _client_last_retry)
        ),
        'env_api_key_set': bool(env_api),
        'env_api_key_prefix': env_api[:8] + '...' if env_api else 'MISSING',
        'env_secret_set': bool(env_secret),
        'env_testnet': env_testnet,
        'binance_api_test': api_test,
        'server_time_utc': datetime.utcnow().isoformat(),
    })


@app.route('/api/force_init', methods=['POST'])
def force_init():
    """Force init client ngay lập tức (reset cooldown)."""
    global _client_last_retry, _ban_until
    _client_last_retry = 0.0
    _ban_until = 0.0
    client = _get_client()
    if client:
        return jsonify({
            'success': True,
            'message': 'Client initialized!'
        })
    return jsonify({
        'success': False,
        'message': 'Init failed - check /api/debug_status'
    }), 500


@app.route('/api/clear_logs', methods=['POST'])
def clear_logs():
    """Clear bot logs"""
    try:
        bot_manager.logs.clear()
        bot_manager.add_log("🗑️ Logs cleared")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/trade_history')
def get_trade_history():
    """Get bot trade history from bot records (trade_history.json)
    with full position info: symbol, LONG/SHORT, entry, exit,
    qty, USD PnL, %PnL, close reason, times.
    """
    try:
        import json as json_mod
        import os

        page = int(request.args.get('page', 1))
        per_page = 8

        # --- Read bot trade history file ---
        # Only use closed_trades.json (new format, written by _save_trade_record)
        # trade_history.json is for ML learning engine only, not displayed here
        base = os.path.dirname(__file__)
        closed_path = os.path.join(
            base, 'models', 'closed_trades.json'
        )
        bot_trades = []
        if os.path.exists(closed_path):
            with open(closed_path) as f:
                raw = json_mod.load(f)
            if isinstance(raw, list):
                bot_trades = raw
            elif isinstance(raw, dict):
                bot_trades = raw.get('trades', [])

        # --- Supplement with Binance income (USD PnL) ---
        # Map: list of {time, income, symbol} sorted desc
        income_records = []
        if (binance_client
                and not binance_client.is_demo_mode):
            try:
                incs = (
                    binance_client.client
                    .futures_income_history(
                        limit=200,
                        incomeType='REALIZED_PNL'
                    )
                )
                for inc in incs:
                    v = float(inc.get('income', 0))
                    if v != 0:
                        income_records.append({
                            'time': inc['time'],
                            'symbol': inc['symbol'],
                            'income': v,
                        })
            except Exception:
                pass

        # Sort bot trades newest first
        def _parse_time(t):
            et = t.get('exit_time', '')
            if et:
                try:
                    from datetime import datetime as _dt
                    return _dt.strptime(
                        et, '%Y-%m-%d %H:%M:%S'
                    ).timestamp()
                except Exception:
                    pass
            ts = t.get('timestamp', '')
            if ts:
                try:
                    from datetime import datetime as _dt
                    for fmt in [
                        '%Y-%m-%dT%H:%M:%S.%f',
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%d %H:%M:%S',
                    ]:
                        try:
                            return _dt.strptime(
                                ts, fmt
                            ).timestamp()
                        except ValueError:
                            pass
                except Exception:
                    pass
            return 0

        bot_trades_sorted = sorted(
            bot_trades, key=_parse_time, reverse=True
        )

        # Enrich trades: fill usd_pnl from income if missing
        enriched = []
        income_idx = 0  # pointer into income_records
        for t in bot_trades_sorted:
            sym = t.get('symbol', '')
            signal = t.get(
                'signal', t.get('side', 'LONG')
            )
            entry = float(t.get('entry_price', 0))
            exit_p = float(t.get('exit_price', 0))
            qty = float(t.get('quantity', 0))

            # pnl_pct: support old 'profit_pct', 'pnl' and new 'pnl_pct'
            pnl_pct = float(
                t.get('pnl_pct',
                      t.get('pnl',
                            t.get('profit_pct', 0)))
            )

            # usd_pnl: use stored, else calc, else income
            usd_pnl = float(t.get('usd_pnl', 0))
            if usd_pnl == 0 and qty > 0 and exit_p > 0:
                if signal == 'LONG':
                    usd_pnl = (exit_p - entry) * qty
                else:
                    usd_pnl = (entry - exit_p) * qty

            # Try to match Binance income record
            if usd_pnl == 0 and income_records:
                for inc in income_records:
                    if inc['symbol'] == sym:
                        usd_pnl = inc['income']
                        break

            # Determine close reason display
            raw_reason = t.get(
                'close_reason', t.get('reason', '')
            )
            if not raw_reason:
                if t.get('breakeven_hit'):
                    raw_reason = 'Trailing SL'
                elif pnl_pct >= 0:
                    raw_reason = 'TP hit'
                else:
                    raw_reason = 'SL hit'

            # Status icon
            if 'Max loss' in raw_reason:
                status = '🔴 SL (-5%)'
                status_color = '#dc3545'
            elif 'Max hold' in raw_reason:
                status = '⏰ Time limit'
                status_color = '#fd7e14'
            elif 'reversal' in raw_reason.lower():
                status = '🔄 Reversal'
                status_color = '#6f42c1'
            elif 'SL/TP' in raw_reason or (
                pnl_pct < 0 and not raw_reason
            ):
                status = '🛡️ SL hit'
                status_color = '#dc3545'
            elif pnl_pct >= 0:
                status = '🎯 TP hit'
                status_color = '#28a745'
            else:
                status = raw_reason
                status_color = '#666'

            enriched.append({
                'symbol': sym,
                'signal': signal,
                'entry_price': entry,
                'exit_price': exit_p,
                'quantity': qty,
                'stop_loss': t.get('stop_loss'),
                'take_profit': t.get('take_profit'),
                'pnl_pct': round(pnl_pct, 3),
                'usd_pnl': round(usd_pnl, 2),
                'close_reason': raw_reason,
                'status': status,
                'status_color': status_color,
                'win': (
                    pnl_pct > 0
                    or usd_pnl > 0
                    or bool(t.get('success', False))
                ),
                'entry_time': t.get('entry_time', ''),
                'exit_time': t.get(
                    'exit_time',
                    t.get('timestamp', '')
                ),
                'breakeven_hit': t.get(
                    'breakeven_hit', False
                ),
                'trailing_hit': t.get(
                    'trailing_hit', False
                ),
            })

        # Summary stats
        total = len(enriched)
        wins = sum(1 for t in enriched if t['win'])
        win_rate = (wins / total * 100) if total else 0
        total_usd = sum(t['usd_pnl'] for t in enriched)
        total_fees = 0
        current_balance = 0
        initial_balance = 5000.0
        if binance_client:
            try:
                if binance_client.is_demo_mode:
                    current_balance = float(
                        binance_client.demo_account
                        .balance
                    )
                    initial_balance = float(
                        binance_client.demo_account
                        .initial_balance
                    )
                else:
                    acct = (
                        binance_client.client
                        .futures_account()
                    )
                    current_balance = float(
                        acct['totalWalletBalance']
                    )
            except Exception:
                pass

        # Pagination
        total_pages = max(
            1, (total + per_page - 1) // per_page
        )
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        page_trades = enriched[start:end]

        return jsonify({
            'success': True,
            'trades': page_trades,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_trades': total,
                'total_pages': total_pages,
            },
            'summary': {
                'total_trades': total,
                'wins': wins,
                'losses': total - wins,
                'win_rate': round(win_rate, 1),
                'total_usd_pnl': round(total_usd, 2),
                'total_fees': round(total_fees, 2),
                'current_balance': current_balance,
                'initial_balance': initial_balance,
                'balance_change': round(
                    current_balance - initial_balance, 2
                ),
            }
        })

    except Exception as e:
        logger.error(f"Error getting trade history: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ===== RETRAIN FROM DASHBOARD =====
_retrain_state = {
    'running': False,
    'logs': [],
    'result': None,
}
_retrain_lock = threading.Lock()

import logging as _logging


class _RetrainLogCapture(_logging.Handler):
    """Capture training logs into _retrain_state['logs']."""
    def emit(self, record):
        msg = self.format(record)
        with _retrain_lock:
            _retrain_state['logs'].append(msg)


@app.route('/api/retrain', methods=['POST'])
def api_retrain():
    """Start retraining in background thread."""
    with _retrain_lock:
        if _retrain_state['running']:
            return jsonify({
                'success': False,
                'error': 'Training already in progress'
            })
        _retrain_state['running'] = True
        _retrain_state['logs'] = ['🚀 Starting V6 binary training...']
        _retrain_state['result'] = None

    def _do_train():
        handler = _RetrainLogCapture()
        handler.setFormatter(
            _logging.Formatter('%(asctime)s | %(message)s', '%H:%M:%S')
        )
        # Attach handler to training logger
        train_logger = _logging.getLogger()
        train_logger.addHandler(handler)
        try:
            from train_ai_improved import train_symbol
            results = {}
            for sym in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                with _retrain_lock:
                    _retrain_state['logs'].append(
                        f'⏳ Training {sym}...'
                    )
                r = train_symbol(sym)
                if r:
                    results[sym] = r
            with _retrain_lock:
                _retrain_state['result'] = results
                if results:
                    summary_lines = []
                    for s, r in results.items():
                        summary_lines.append(
                            f"{s}: GB={r['accuracy']:.1f}% "
                            f"XGB={r['accuracy_xgb']:.1f}% "
                            f"HGB={r['accuracy_hgb']:.1f}%"
                        )
                    _retrain_state['logs'].append(
                        '✅ Training complete!\n'
                        + '\n'.join(summary_lines)
                    )
                else:
                    _retrain_state['logs'].append(
                        '❌ Training failed for all symbols'
                    )
        except Exception as exc:
            with _retrain_lock:
                _retrain_state['logs'].append(f'❌ Error: {exc}')
        finally:
            train_logger.removeHandler(handler)
            with _retrain_lock:
                _retrain_state['running'] = False

    t = threading.Thread(target=_do_train, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Training started'})


@app.route('/api/retrain_status')
def api_retrain_status():
    """Poll training progress."""
    since = request.args.get('since', 0, type=int)
    with _retrain_lock:
        logs = _retrain_state['logs'][since:]
        return jsonify({
            'success': True,
            'running': _retrain_state['running'],
            'logs': logs,
            'total': len(_retrain_state['logs']),
            'result': _retrain_state['result'],
        })


# ──────────────────── PWA Endpoints ────────────────────────────────────────
def _make_trading_icon_png(size):
    """Trading bot icon: dark gradient bg + 4 candlestick bars + trend line.
    Uses only Python stdlib (struct, zlib) — no PIL needed.
    """
    buf = bytearray(size * size * 3)

    # Fast gradient background — one Python iter per row
    for y in range(size):
        t = y / max(size - 1, 1)
        # Dark navy (#0f1923) → dark blue (#1a3050)
        pixel = bytes([int(15 + 11*t), int(25 + 27*t), int(35 + 45*t)])
        s_off = y * size * 3
        buf[s_off:s_off + size * 3] = pixel * size

    sc = size / 192.0  # scale factor for any size

    def rect(x0, y0, x1, y1, r, g, b):
        """Fill axis-aligned rectangle, clamped to image bounds."""
        x0c, x1c = max(0, x0), min(size, x1)
        if x1c <= x0c:
            return
        row_pix = bytes([r, g, b]) * (x1c - x0c)
        for yy in range(max(0, y0), min(size, y1)):
            start = (yy * size + x0c) * 3
            buf[start:start + len(row_pix)] = row_pix

    # Chart area: centred, 70% of icon
    cl = int(28 * sc)
    cr_ = int(164 * sc)
    ct = int(36 * sc)
    cb_ = int(156 * sc)
    cw = cr_ - cl
    ch = cb_ - ct

    # 4 candles: (body_top%, body_bot%, is_green)
    # Arranged to suggest upward trend: down-up-down-up
    candles = [
        (0.32, 0.68, False),   # 1st — red, medium
        (0.10, 0.74, True),    # 2nd — green, tall
        (0.40, 0.72, False),   # 3rd — red, small
        (0.04, 0.84, True),    # 4th — green, tallest
    ]
    bw = max(4, int(cw / 7.8))           # bar body width
    bg_ = max(2, int(bw * 0.55))         # gap between bars
    total_bw = len(candles) * bw + (len(candles) - 1) * bg_
    bx0 = cl + (cw - total_bw) // 2
    wh = max(1, int(sc * 1.6))           # wick half-width

    trend_pts = []
    for i, (tp, bp, green) in enumerate(candles):
        bx = bx0 + i * (bw + bg_)
        by_t = ct + int(tp * ch)
        by_b = ct + int(bp * ch)
        col = (34, 211, 84) if green else (225, 55, 55)
        wx = bx + bw // 2
        # wick (extends above/below body)
        rect(wx - wh, by_t - int(9*sc), wx + wh + 1, by_b + int(7*sc), *col)
        # body
        rect(bx, by_t, bx + bw, by_b, *col)
        trend_pts.append((wx, by_t))    # top of body for trend line

    # Diagonal trend line connecting candle tops (upward left→right)
    lw = max(2, int(3.5 * sc))
    gold = (255, 215, 0)
    for i in range(len(trend_pts) - 1):
        ax, ay = trend_pts[i]
        bxp, byp = trend_pts[i + 1]
        steps = max(abs(bxp - ax), abs(byp - ay), 1)
        for step in range(steps + 1):
            lx = int(ax + (bxp - ax) * step / steps)
            ly = int(ay + (byp - ay) * step / steps)
            rect(lx - lw, ly - lw, lx + lw + 1, ly + lw + 1, *gold)

    # Small arrowhead at the end of trend line (→ up)
    ex, ey = trend_pts[-1]
    asz = max(4, int(10 * sc))
    for k in range(asz):
        rect(ex - k, ey - asz + k, ex + k + 1, ey - asz + k + 1, *gold)

    # Pack pixels → PNG
    raw = b''.join(
        b'\x00' + bytes(buf[y * size * 3:(y + 1) * size * 3])
        for y in range(size)
    )
    idat = zlib.compress(raw, 6)

    def _ck(tag, data):
        c = tag + data
        return (struct.pack('>I', len(data)) + c
                + struct.pack('>I', zlib.crc32(c) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n'
            + _ck(b'IHDR', ihdr)
            + _ck(b'IDAT', idat)
            + _ck(b'IEND', b''))


_pwa_icon_192 = None
_pwa_icon_512 = None


@app.route('/manifest.json')
def pwa_manifest():
    return jsonify({
        "name": "Binance Trading Bot",
        "short_name": "TradeBot",
        "description": "AI Binance Futures Trading Dashboard",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#667eea",
        "theme_color": "#667eea",
        "categories": ["finance", "utilities"],
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    })


@app.route('/icon-192.png')
def pwa_icon_192():
    global _pwa_icon_192
    if _pwa_icon_192 is None:
        _pwa_icon_192 = _make_trading_icon_png(192)
    return Response(_pwa_icon_192, mimetype='image/png',
                    headers={'Cache-Control': 'public, max-age=86400'})


@app.route('/icon-512.png')
def pwa_icon_512():
    global _pwa_icon_512
    if _pwa_icon_512 is None:
        _pwa_icon_512 = _make_trading_icon_png(512)
    return Response(_pwa_icon_512, mimetype='image/png',
                    headers={'Cache-Control': 'public, max-age=86400'})


@app.route('/sw.js')
def service_worker():
    sw_code = r"""const CACHE = 'tradebot-v1';
const SHELL = ['/', '/manifest.json', '/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) return;
  e.respondWith(
    fetch(e.request)
      .then(resp => {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});
"""
    return Response(sw_code.strip(), mimetype='application/javascript',
                    headers={'Service-Worker-Allowed': '/'})
# ────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    host = '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1'
    print("🚀 Starting Binance Bot Dashboard...")
    print(f"📱 Open browser: http://localhost:{port}")
    print("🛑 Press Ctrl+C to stop")
    
    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False
    )
