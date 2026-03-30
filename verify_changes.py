"""Verification script for all improvements"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

print(f"Python: {sys.version}")
results = []

# 1. Test SmartBotEngine imports
try:
    from smart_bot_engine import SmartBotEngine
    results.append("✅ SmartBotEngine imported OK")
    
    # Check new persistence methods
    assert hasattr(SmartBotEngine, '_save_trade_record')
    assert hasattr(SmartBotEngine, '_save_session_state')
    assert hasattr(SmartBotEngine, '_load_session_state')
    results.append("✅ Persistence methods exist")
    
    # Check v2 methods from Phase 6
    assert hasattr(SmartBotEngine, 'check_market_regime')
    assert hasattr(SmartBotEngine, 'check_correlation')
    assert hasattr(SmartBotEngine, 'check_funding_rate')
    assert hasattr(SmartBotEngine, 'check_volatility_spike')
    assert hasattr(SmartBotEngine, 'position_monitor_loop')
    results.append("✅ All v2 methods present")
except Exception as e:
    results.append(f"❌ SmartBotEngine: {e}")

# 2. Test web_dashboard
try:
    from web_dashboard import app, BotManager
    results.append("✅ web_dashboard imported OK")
    
    # Check new endpoints exist
    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert '/api/run_backtest' in rules, "Missing /api/run_backtest"
    assert '/api/bot_engine_status' in rules, "Missing /api/bot_engine_status"
    assert '/api/performance_stats' in rules
    results.append("✅ New API endpoints registered")
    
    # Check BotManager risk_settings have v2 keys
    bm = BotManager()
    rs = bm.risk_settings
    assert 'trailingStopPct' in rs, "Missing trailingStopPct"
    assert 'breakevenTrigger' in rs, "Missing breakevenTrigger"
    assert 'maxDrawdown' in rs, "Missing maxDrawdown"
    assert rs['maxLeverage'] >= 15, f"Leverage too low: {rs['maxLeverage']}"
    results.append(f"✅ Risk settings v2 OK (leverage={rs['maxLeverage']}x)")
except Exception as e:
    results.append(f"❌ web_dashboard: {e}")

# 3. Test backtest
try:
    from backtest import Backtester
    results.append("✅ Backtester imported OK")
except Exception as e:
    results.append(f"❌ Backtester: {e}")

# 4. Test config
try:
    from config import Config
    assert Config.DEFAULT_LEVERAGE == 15
    rm = Config.RISK_MANAGEMENT
    assert rm['trailing_stop_percent'] > 0
    assert rm['breakeven_trigger_percent'] > 0
    assert rm['partial_tp_enabled'] == True
    results.append(f"✅ Config OK (leverage={Config.DEFAULT_LEVERAGE}x, trailing={rm['trailing_stop_percent']}%)")
except Exception as e:
    results.append(f"❌ Config: {e}")

# 5. Test continuous learning
try:
    from continuous_learning_engine import ContinuousLearningEngine
    results.append("✅ ContinuousLearningEngine OK")
except Exception as e:
    results.append(f"❌ ContinuousLearning: {e}")

# 6. Test advanced AI
try:
    from advanced_ai_engine import AdvancedAIEngine
    results.append("✅ AdvancedAIEngine OK")
except Exception as e:
    results.append(f"❌ AdvancedAI: {e}")

# 7. Test technical analysis
try:
    from technical_analysis import TechnicalAnalyzer
    results.append("✅ TechnicalAnalyzer OK")
except Exception as e:
    results.append(f"❌ TechnicalAnalyzer: {e}")

# Print results
print("\n" + "="*50)
print("VERIFICATION RESULTS")  
print("="*50)
for r in results:
    print(r)

errors = [r for r in results if r.startswith("❌")]
print(f"\n{'🎉 ALL CHECKS PASSED!' if not errors else f'⚠️ {len(errors)} ERRORS FOUND'}")
print(f"Score: {len(results) - len(errors)}/{len(results)}")
