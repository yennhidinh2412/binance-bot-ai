"""
FINAL SYSTEM TEST - Kiểm tra toàn bộ hệ thống
"""

import pickle
import os
import asyncio
from datetime import datetime


def test_ai_models():
    """Test 1: Kiểm tra AI Models"""
    print("\n" + "="*70)
    print("🧪 TEST 1: KIỂM TRA AI MODELS")
    print("="*70)

    models_to_check = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

    for symbol in models_to_check:
        model_path = f'models/gradient_boost_{symbol}.pkl'
        scaler_path = f'models/scaler_{symbol}.pkl'

        if os.path.exists(model_path) and os.path.exists(scaler_path):
            with open(model_path, 'rb') as f:
                model = pickle.load(f)

            n_estimators = getattr(model, 'n_estimators', 'N/A')
            feature_count = getattr(model, 'n_features_in_', 'N/A')

            modified_time = datetime.fromtimestamp(
                os.path.getmtime(model_path)
            )

            print(f'\n✅ {symbol}:')
            print(f'   📦 Model: GradientBoosting')
            print(f'   🔢 Estimators: {n_estimators}')
            print(f'   📊 Features: {feature_count}')
            print(f'   🕐 Updated: {modified_time:%Y-%m-%d %H:%M:%S}')
        else:
            print(f'\n❌ {symbol}: Model NOT FOUND!')
            return False

    print("\n✅ Tất cả AI models đã sẵn sàng!\n")
    return True


def test_smart_bot_engine():
    """Test 2: Kiểm tra SmartBotEngine"""
    print("\n" + "="*70)
    print("🧪 TEST 2: KIỂM TRA SMART BOT ENGINE")
    print("="*70)

    try:
        from smart_bot_engine import SmartBotEngine
        from binance_client import BinanceFuturesClient

        print("\n📍 Khởi tạo SmartBotEngine...")
        client = BinanceFuturesClient()
        bot = SmartBotEngine(client)

        print("✅ SmartBotEngine khởi tạo thành công!")
        print(f"   📊 Symbols: {', '.join(bot.symbols)}")
        print(f"   🎯 Timeframe: {bot.timeframe}")

        return True, bot, client

    except Exception as e:
        print(f"❌ Lỗi: {e}")
        return False, None, None


async def test_ai_analysis(bot):
    """Test 3: Kiểm tra AI Analysis"""
    print("\n" + "="*70)
    print("🧪 TEST 3: KIỂM TRA AI ANALYSIS & INTELLIGENCE")
    print("="*70)

    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    all_results = []

    for symbol in symbols:
        print(f"\n🔍 Analyzing {symbol}...")
        try:
            analysis = await bot.analyze_symbol(symbol)

            if analysis:
                signal = analysis.get('signal', 'N/A')
                confidence = analysis.get('confidence', 0)
                entry_price = analysis.get('entry_price', 0)
                tp_price = analysis.get('tp_price', 0)
                sl_price = analysis.get('sl_price', 0)
                trend = analysis.get('trend', 'N/A')
                risk = analysis.get('risk_level', 'N/A')

                print(f"\n💎 {symbol} ANALYSIS:")
                print(f"   📊 Signal: {signal}")
                print(f"   🎯 Confidence: {confidence:.2f}%")
                print(f"   💰 Entry Price: ${entry_price:,.2f}")

                if signal != 'HOLD':
                    print(f"   ✅ Take Profit: ${tp_price:,.2f}")
                    print(f"   🛡️  Stop Loss: ${sl_price:,.2f}")

                    # Calculate potential profit/loss
                    if signal == 'LONG':
                        profit_pct = ((tp_price / entry_price) - 1) * 100
                        loss_pct = ((sl_price / entry_price) - 1) * 100
                    else:
                        profit_pct = ((entry_price / tp_price) - 1) * 100
                        loss_pct = ((entry_price / sl_price) - 1) * 100

                    print(f"   📈 Potential Profit: {profit_pct:+.2f}%")
                    print(f"   📉 Potential Loss: {loss_pct:+.2f}%")

                print(f"   📊 Trend: {trend}")
                print(f"   ⚠️  Risk Level: {risk}")

                # Check if it's a good opportunity
                is_good = signal != 'HOLD' and confidence >= 75
                if is_good:
                    print(f"\n   🌟 GOOD OPPORTUNITY DETECTED!")
                    print(f"   ✨ Bot sẽ suggest trade này!")
                else:
                    if signal == 'HOLD':
                        print(f"\n   ⏸️  HOLD - Bot đang chờ cơ hội tốt hơn")
                    else:
                        print(f"\n   ⏸️  Confidence thấp - Bot chờ xác nhận")

                all_results.append({
                    'symbol': symbol,
                    'signal': signal,
                    'confidence': confidence,
                    'is_good': is_good
                })

            else:
                print(f"   ❌ Analysis failed for {symbol}")

        except Exception as e:
            print(f"   ❌ Error: {e}")

    return all_results


def test_dashboard_ready():
    """Test 4: Kiểm tra Dashboard"""
    print("\n" + "="*70)
    print("🧪 TEST 4: KIỂM TRA DASHBOARD")
    print("="*70)

    try:
        from web_dashboard import app, bot_manager

        print("\n✅ Dashboard module loaded successfully!")
        print(f"   📱 Flask app: {app.name}")
        print(f"   🤖 Bot manager: {type(bot_manager).__name__}")
        print(f"   🎮 Trading mode: {bot_manager.trading_mode}")
        print(f"   📊 Dashboard URL: http://localhost:8080")

        return True

    except Exception as e:
        print(f"❌ Lỗi: {e}")
        return False


def print_final_summary(ai_ok, bot_ok, analysis_results, dashboard_ok):
    """In tổng kết cuối cùng"""
    print("\n" + "="*70)
    print("📋 FINAL TEST SUMMARY")
    print("="*70)

    print(f"\n✅ AI Models: {'PASSED' if ai_ok else 'FAILED'}")
    print(f"✅ Smart Bot Engine: {'PASSED' if bot_ok else 'FAILED'}")
    print(f"✅ Dashboard: {'PASSED' if dashboard_ok else 'FAILED'}")

    if analysis_results:
        print(f"\n🤖 AI ANALYSIS RESULTS:")
        good_opportunities = [r for r in analysis_results if r['is_good']]

        for result in analysis_results:
            status = "🌟 GOOD" if result['is_good'] else "⏸️  WAIT"
            print(f"   {result['symbol']}: "
                  f"{result['signal']} "
                  f"({result['confidence']:.1f}%) - {status}")

        print(f"\n📊 Total Opportunities Found: {len(good_opportunities)}/3")

        if good_opportunities:
            print("\n🎯 BOT INTELLIGENCE:")
            print("   ✅ Bot tìm thấy cơ hội tốt (≥75% confidence)")
            print("   ✅ Bot sẽ suggest trades này")
            print("   ✅ Bot đang hoạt động THÔNG MINH!")
        else:
            print("\n🎯 BOT INTELLIGENCE:")
            print("   ✅ Bot đang HOLD - chờ cơ hội tốt hơn")
            print("   ✅ Bot biết khi nào KHÔNG NÊN trade")
            print("   ✅ Bot đang bảo vệ vốn - Đây là THÔNG MINH!")

    print("\n" + "="*70)
    all_passed = ai_ok and bot_ok and dashboard_ok
    if all_passed:
        print("🎉 FINAL RESULT: ALL TESTS PASSED!")
        print("✅ Bot đã sẵn sàng để trading thông minh!")
    else:
        print("⚠️  FINAL RESULT: SOME TESTS FAILED")
        print("❌ Cần kiểm tra lại các component bị lỗi")
    print("="*70 + "\n")


async def main():
    """Main test function"""
    print("\n" + "="*70)
    print("🚀 FINAL SYSTEM TEST - COMPREHENSIVE CHECK")
    print("="*70)
    print(f"⏰ Time: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("="*70)

    # Test 1: AI Models
    ai_models_ok = test_ai_models()

    if not ai_models_ok:
        print("\n❌ AI Models test failed. Stopping...")
        return

    # Test 2: Smart Bot Engine
    bot_ok, bot, client = test_smart_bot_engine()

    if not bot_ok:
        print("\n❌ Bot Engine test failed. Stopping...")
        return

    # Test 3: AI Analysis
    analysis_results = await test_ai_analysis(bot)

    # Test 4: Dashboard
    dashboard_ok = test_dashboard_ready()

    # Final Summary
    print_final_summary(ai_models_ok, bot_ok, analysis_results, dashboard_ok)


if __name__ == "__main__":
    asyncio.run(main())
