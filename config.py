"""
Binance Futures Trading Bot Configuration
Secure API key management and settings
"""

import os
from typing import Dict, Any


def _env_float(name: str, default: float) -> float:
    """Read float env var safely with fallback."""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    """Read bool env var safely with fallback."""
    val = os.environ.get(name)
    if val is None:
        return bool(default)
    return str(val).strip().lower() in (
        '1', 'true', 'yes', 'y', 'on'
    )


class Config:
    """Cấu hình bot trading với bảo mật cao"""

    # ──────────────────────────────────────────────────────
    # API Keys
    # Ưu tiên: biến môi trường → fallback testnet hardcode
    # ⚠️  PRODUCTION: bắt buộc phải set env BINANCE_API_KEY
    #     và BINANCE_SECRET_KEY — KHÔNG bao giờ dùng key thật
    #     trong code.
    # ──────────────────────────────────────────────────────
    _is_testnet = os.environ.get(
        'BINANCE_TESTNET', 'true'
    ).lower() == 'true'

    _env_api_key = os.environ.get('BINANCE_API_KEY')
    _env_secret_key = os.environ.get('BINANCE_SECRET_KEY')

    # Nếu đang chạy mainnet (production) mà không có env var → crash ngay
    if not _is_testnet and not _env_api_key:
        raise EnvironmentError(
            "PRODUCTION MODE: biến môi trường BINANCE_API_KEY "
            "chưa được set! Tuyệt đối không dùng key hardcode "
            "cho tài khoản thật."
        )

    # Fallback chỉ dùng cho testnet local dev
    BINANCE_API_KEY = _env_api_key or (
        "bKB0TeDnFtDLh1yc7zEQWv0egLJbT1PoxGexmTzRAsMRueZOm62hOjFIc7nXyHgD"
        if _is_testnet else None
    )
    BINANCE_SECRET_KEY = _env_secret_key or (
        "FbRdzXolQmMndEgwGX4oM1aapSk9r5z8XSPOTSdhEQh2YrgXunEzFsVXdbAlhLnq"
        if _is_testnet else None
    )

    # Trusted IP addresses
    TRUSTED_IPS = [
        "34.2.147.137",   # Google Cloud VM
        "115.79.215.63",  # MacBook IP
        "58.186.75.18",   # Windows PC IP
        "42.114.205.215", # IP Binance whitelist
        "112.197.29.55",  # IP Binance whitelist
        "1.53.114.43",    # Home IP
        "113.176.62.98",  # Current location IP (added 2026-03-07)
    ]

    # Trading Configuration
    TRADING_CONFIG = {
        "testnet": _is_testnet,  # Controlled by BINANCE_TESTNET env var
        "demo_mode": False,
        "demo_balance": 10000,
        # base_url đúng theo môi trường (dùng bởi legacy code nếu có)
        "base_url": (
            "https://testnet.binancefuture.com"
            if _is_testnet
            else "https://fapi.binance.com"
        ),
        "websocket_url": (
            "wss://stream.binancefuture.com"
            if _is_testnet
            else "wss://fstream.binance.com"
        ),
        "default_symbol": "BTCUSDT",
        "timeframes": ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"],
        "max_open_positions": 3,  # Tối đa 3 lệnh cùng lúc (chia đều vốn)
        "default_leverage": 35,  # Đòn bẩy mặc định 35x
        "max_leverage": 40,  # Đòn bẩy tối đa 40x

        # Leverage theo symbol
        # 35-40x: Đòn bẩy tối ưu cho từng coin
        "symbol_leverage": {
            "BTCUSDT": 40,
            "ETHUSDT": 38,
            "SOLUSDT": 35,
            "ADAUSDT": 35
        }
    }
    
    # Risk Management
    # Với 200.000 VNĐ (~$8), chia 3 lệnh = ~$2.67/lệnh
    # Đòn bẩy 100x -> Khối lượng thực = $267/lệnh
    RISK_MANAGEMENT = {
        "min_start_balance_usd": _env_float('MIN_START_BALANCE_USD', 1.0),
        # Mục tiêu lợi nhuận tối thiểu mỗi lệnh (USD)
        # $4 ≈ 100,000 VND | Bot tự scale position size để đạt mục tiêu này
        # Override bằng env: MIN_PROFIT_TARGET_USD
        "min_profit_target_usd": _env_float('MIN_PROFIT_TARGET_USD', 4.0),
        # Auto mode: có LONG/SHORT là vào lệnh ngay
        # (bỏ qua confidence/quality/soft filters)
        # Override bằng env: FORCE_ENTRY_ON_SIGNAL=true/false
        "force_entry_on_signal": _env_bool(
            'FORCE_ENTRY_ON_SIGNAL', True
        ),
        "max_position_size_percent": 30.0,  # 30% - dùng làm baseline
        "stop_loss_percent": 1.5,  # SL 1.5%
        "take_profit_percent": 3.0,  # TP 3% (R:R = 1:2)
        "max_daily_loss_percent": 5.0,  # Max loss 5%/ngày
        "trailing_stop_percent": 0.8,  # Trailing stop 0.8%
        "max_drawdown_percent": 10.0,  # Max drawdown 10%
        "breakeven_trigger_percent": 1.0,  # Move SL to breakeven when +1%
        "partial_tp_enabled": True,  # Chốt lời từng phần
        "partial_tp_levels": [0.5, 0.3, 0.2],  # TP1: 50%, TP2: 30%, TP3: 20% quantity
        "min_adx_trend": 15,  # Chỉ trade khi ADX > 15 (thị trường trending)
        "max_correlation_same_direction": 2,  # Max 2 lệnh cùng hướng
        "max_funding_rate": 0.05,  # Skip nếu funding > 0.05%
        "volatility_spike_multiplier": 3.0  # ATR spike = 3x average → skip
    }
    
    # AI/ML Configuration
    AI_CONFIG = {
        "lookback_periods": 200,
        "prediction_timeframe": "5m",
        # LOWERED to 60% for demo testing (easier to trigger trades)
        "confidence_threshold": 0.60,
        "model_retrain_hours": 24,
        "technical_indicators": [
            "RSI", "MACD", "Bollinger_Bands", "EMA", "SMA",
            "Stochastic", "Williams_R", "ADX", "CCI", "MFI"
        ]
    }
    
    # Logging and Monitoring
    LOGGING_CONFIG = {
        "level": "INFO",
        "file_path": "logs/trading_bot.log",
        "max_file_size": "10MB",
        "backup_count": 5,
        # Set to True if using Telegram alerts
        "telegram_notifications": False,
        "email_notifications": False
    }

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Trả về toàn bộ cấu hình"""
        return {
            "api_keys": {
                "binance_api_key": cls.BINANCE_API_KEY,
                "binance_secret_key": cls.BINANCE_SECRET_KEY
            },
            "trusted_ips": cls.TRUSTED_IPS,
            "trading": cls.TRADING_CONFIG,
            "risk_management": cls.RISK_MANAGEMENT,
            "ai_config": cls.AI_CONFIG,
            "logging": cls.LOGGING_CONFIG
        }
