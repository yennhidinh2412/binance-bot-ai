"""
Utility Functions
Các hàm tiện ích cho trading bot
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
from loguru import logger

def format_number(number: float, decimals: int = 2) -> str:
    """Format số với độ chính xác"""
    return f"{number:,.{decimals}f}"

def calculate_percentage(value: float, total: float) -> float:
    """Tính phần trăm"""
    return (value / total * 100) if total != 0 else 0

def calculate_pnl(entry_price: float, current_price: float, quantity: float, side: str) -> float:
    """Tính toán PnL"""
    if side.upper() == 'BUY':
        return (current_price - entry_price) * quantity
    else:  # SELL
        return (entry_price - current_price) * quantity

def timestamp_to_datetime(timestamp: int) -> datetime:
    """Chuyển timestamp thành datetime"""
    return datetime.fromtimestamp(timestamp / 1000)

def datetime_to_timestamp(dt: datetime) -> int:
    """Chuyển datetime thành timestamp"""
    return int(dt.timestamp() * 1000)

def is_market_hours() -> bool:
    """Kiểm tra có phải giờ giao dịch không (24/7 cho crypto)"""
    return True  # Crypto markets are 24/7

def get_timeframe_minutes(timeframe: str) -> int:
    """Lấy số phút từ timeframe"""
    timeframe_map = {
        '1m': 1,
        '3m': 3,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '2h': 120,
        '4h': 240,
        '6h': 360,
        '8h': 480,
        '12h': 720,
        '1d': 1440,
        '3d': 4320,
        '1w': 10080
    }
    return timeframe_map.get(timeframe, 5)

def validate_symbol(symbol: str) -> bool:
    """Validate symbol format"""
    return len(symbol) >= 6 and symbol.endswith('USDT')

def calculate_moving_average(data: List[float], period: int) -> List[float]:
    """Tính moving average"""
    if len(data) < period:
        return [np.nan] * len(data)
    
    result = []
    for i in range(len(data)):
        if i < period - 1:
            result.append(np.nan)
        else:
            avg = sum(data[i - period + 1:i + 1]) / period
            result.append(avg)
    
    return result

def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """Tính RSI đơn giản"""
    if len(prices) < period + 1:
        return [np.nan] * len(prices)
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(0, delta) for delta in deltas]
    losses = [max(0, -delta) for delta in deltas]
    
    # Initial average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsi_values = [np.nan] * (period + 1)
    
    for i in range(period, len(deltas)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        rsi_values.append(rsi)
    
    return rsi_values

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Chia an toàn, tránh division by zero"""
    return numerator / denominator if denominator != 0 else default

def round_to_tick_size(price: float, tick_size: float) -> float:
    """Round price theo tick size"""
    return round(price / tick_size) * tick_size

def calculate_volatility(prices: List[float], period: int = 20) -> float:
    """Tính volatility (standard deviation)"""
    if len(prices) < period:
        return 0.0
    
    recent_prices = prices[-period:]
    mean_price = sum(recent_prices) / len(recent_prices)
    variance = sum((price - mean_price) ** 2 for price in recent_prices) / len(recent_prices)
    
    return variance ** 0.5

def detect_trend(prices: List[float], short_period: int = 10, long_period: int = 30) -> str:
    """Phát hiện xu hướng đơn giản"""
    if len(prices) < long_period:
        return "UNKNOWN"
    
    short_ma = sum(prices[-short_period:]) / short_period
    long_ma = sum(prices[-long_period:]) / long_period
    
    if short_ma > long_ma * 1.01:  # 1% threshold
        return "UPTREND"
    elif short_ma < long_ma * 0.99:
        return "DOWNTREND"
    else:
        return "SIDEWAYS"

def format_trade_log(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    pnl: Optional[float] = None
) -> str:
    """Format log entry cho trade"""
    trade_info = f"{symbol} {side} {quantity} @ {price}"
    if pnl is not None:
        trade_info += f" | PnL: {pnl:+.4f}"
    return trade_info

def save_to_json(data: Dict[str, Any], filename: str):
    """Lưu data vào JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug(f"Data saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving to {filename}: {e}")

def load_from_json(filename: str) -> Dict[str, Any]:
    """Load data từ JSON file"""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        logger.debug(f"Data loaded from {filename}")
        return data
    except FileNotFoundError:
        logger.warning(f"File {filename} not found")
        return {}
    except Exception as e:
        logger.error(f"Error loading from {filename}: {e}")
        return {}

def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
    """Tính Sharpe ratio"""
    if not returns or len(returns) < 2:
        return 0.0
    
    avg_return = sum(returns) / len(returns)
    std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
    
    if std_return == 0:
        return 0.0
    
    # Annualize (assuming daily returns)
    annual_return = avg_return * 365
    annual_std = std_return * (365 ** 0.5)
    
    return (annual_return - risk_free_rate) / annual_std

def calculate_max_drawdown(equity_curve: List[float]) -> Dict[str, float]:
    """Tính max drawdown"""
    if not equity_curve:
        return {'max_drawdown': 0.0, 'max_drawdown_percent': 0.0}
    
    peak = equity_curve[0]
    max_dd = 0.0
    max_dd_percent = 0.0
    
    for value in equity_curve:
        if value > peak:
            peak = value
        
        drawdown = peak - value
        drawdown_percent = (drawdown / peak * 100) if peak > 0 else 0
        
        if drawdown > max_dd:
            max_dd = drawdown
            max_dd_percent = drawdown_percent
    
    return {
        'max_drawdown': max_dd,
        'max_drawdown_percent': max_dd_percent
    }

def generate_report(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tạo báo cáo hiệu suất"""
    if not trades:
        return {}
    
    # Calculate basic metrics
    total_trades = len(trades)
    winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
    losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
    
    win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
    
    total_pnl = sum(t.get('pnl', 0) for t in trades)
    avg_win = sum(t.get('pnl', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t.get('pnl', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
    
    profit_factor = abs(avg_win * len(winning_trades) / (avg_loss * len(losing_trades))) if losing_trades and avg_loss != 0 else float('inf')
    
    returns = [t.get('pnl', 0) for t in trades]
    sharpe = calculate_sharpe_ratio(returns)
    
    equity_curve = []
    running_total = 0
    for trade in trades:
        running_total += trade.get('pnl', 0)
        equity_curve.append(running_total)
    
    drawdown_info = calculate_max_drawdown(equity_curve)
    
    return {
        'total_trades': total_trades,
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'average_win': avg_win,
        'average_loss': avg_loss,
        'profit_factor': profit_factor,
        'sharpe_ratio': sharpe,
        'max_drawdown': drawdown_info['max_drawdown'],
        'max_drawdown_percent': drawdown_info['max_drawdown_percent']
    }

class PerformanceTracker:
    """Class để track performance"""
    
    def __init__(self):
        self.trades = []
        self.daily_pnl = {}
        self.start_time = datetime.now()
    
    def add_trade(self, trade_info: Dict[str, Any]):
        """Thêm trade vào tracking"""
        trade_info['timestamp'] = datetime.now()
        self.trades.append(trade_info)
        
        # Update daily PnL
        date_key = trade_info['timestamp'].date()
        if date_key not in self.daily_pnl:
            self.daily_pnl[date_key] = 0.0
        self.daily_pnl[date_key] += trade_info.get('pnl', 0)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Lấy báo cáo performance"""
        return generate_report(self.trades)
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """Lấy tóm tắt theo ngày"""
        today = datetime.now().date()
        
        today_pnl = self.daily_pnl.get(today, 0.0)
        today_trades = [t for t in self.trades if t['timestamp'].date() == today]
        
        return {
            'date': today,
            'pnl': today_pnl,
            'trades_count': len(today_trades),
            'win_rate': len([t for t in today_trades if t.get('pnl', 0) > 0]) / len(today_trades) * 100 if today_trades else 0
        }
