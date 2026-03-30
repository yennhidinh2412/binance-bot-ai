"""
Binance Futures Trading Bot
Bot AI trading futures với độ chính xác cao
"""

__version__ = "1.0.0"
__author__ = "AI Trading Team"
__description__ = "Professional AI-powered Binance futures trading bot"

from .config import Config
from .binance_client import BinanceFuturesClient
from .technical_analysis import TechnicalAnalyzer
from .risk_management import RiskManager

__all__ = [
    'BinanceFuturesClient',
    'TechnicalAnalyzer',
    'RiskManager',
    'Config'
]
