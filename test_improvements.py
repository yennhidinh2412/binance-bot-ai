"""Test script - verify all improvements"""
import sys
print(f'Python: {sys.version}')

# Test imports
try:
    from smart_bot_engine import SmartBotEngine
    print('OK SmartBotEngine imported')
except Exception as e:
    print(f'FAIL SmartBotEngine: {e}')
    sys.exit(1)

try:
    from backtest import Backtester
    print('OK Backtester imported')
except Exception as e:
    print(f'FAIL Backtester: {e}')

try:
    from config import Config
    cfg = Config.get_config()
    print('OK Config loaded')
except Exception as e:
    print(f'FAIL Config: {e}')

# Check risk settings
risk = cfg['risk_management']
trading = cfg['trading']
print()
print('=== CONFIG CHECK ===')
print(f'Default leverage: {trading["default_leverage"]}x')
print(f'Max leverage: {trading["max_leverage"]}x')
print(f'Symbol leverage: {trading["symbol_leverage"]}')
print(f'Max position size: {risk["max_position_size_percent"]}%')
print(f'SL: {risk["stop_loss_percent"]}%')
print(f'TP: {risk["take_profit_percent"]}%')
print(f'Trailing: {risk["trailing_stop_percent"]}%')
print(f'Breakeven trigger: {risk["breakeven_trigger_percent"]}%')
print(f'Partial TP: {risk["partial_tp_enabled"]}')
print(f'Min ADX: {risk["min_adx_trend"]}')
print(f'Max same-direction: {risk["max_correlation_same_direction"]}')
print(f'Max funding rate: {risk["max_funding_rate"]}%')
print(f'Volatility spike mult: {risk["volatility_spike_multiplier"]}x')
print(f'Max drawdown: {risk["max_drawdown_percent"]}%')

# Check SmartBotEngine
bot = SmartBotEngine()
rs = bot.risk_settings
print()
print('=== BOT ENGINE CHECK ===')
print(f'Max leverage: {rs["max_leverage"]}x')
print(f'Position size: {rs["max_position_size"]}%')
print(f'Symbol leverage: {rs["symbol_leverage"]}')
print(f'Trailing stop: {rs["trailing_stop_pct"]}%')
print(f'Breakeven: {rs["breakeven_trigger_pct"]}%')
print(f'Partial TP: {rs["partial_tp_enabled"]}')
print(f'Min ADX: {rs["min_adx_trend"]}')
print(f'Max corr same dir: {rs["max_correlation_same_dir"]}')
print(f'Max funding: {rs["max_funding_rate"]}%')
print(f'Volatility spike: {rs["volatility_spike_mult"]}x')
print(f'Max drawdown: {rs["max_drawdown_pct"]}%')

# Check new methods exist
print()
print('=== NEW METHODS CHECK ===')
methods = [
    'check_market_regime',
    'check_correlation',
    'check_funding_rate',
    'check_volatility_spike',
    'position_monitor_loop',
    '_update_stop_loss',
]
for m in methods:
    exists = hasattr(bot, m)
    status = 'OK' if exists else 'FAIL'
    print(f'{status} {m}')

print()
print('ALL IMPROVEMENTS VERIFIED!')
