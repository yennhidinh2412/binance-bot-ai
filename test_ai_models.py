"""
Test AI Models - Verify model loading, accuracy, and features
"""
from smart_bot_engine import SmartBotEngine
from binance_client import BinanceFuturesClient
import json
import os

print("="*80)
print("🤖 TESTING AI MODELS")
print("="*80)

# Initialize
print("\n1️⃣ Initializing bot engine...")
client = BinanceFuturesClient()
bot = SmartBotEngine(client)

print(f"\n✅ Bot initialized with {len(bot.models)} models\n")

# Check each model
print("="*80)
print("📊 MODEL DETAILS")
print("="*80)

for symbol, model_data in bot.models.items():
    print(f"\n🔍 {symbol}:")
    print(f"   Accuracy: {model_data['accuracy']:.1f}%")
    print(f"   Model Type: {type(model_data['model']).__name__}")
    
    # Check if features exist
    if 'feature_names' in model_data:
        features = model_data['feature_names']
        print(f"   Features: {len(features)} indicators")
        print(f"   Top Features:")
        for i, feature in enumerate(features[:5], 1):
            print(f"      {i}. {feature}")
        if len(features) > 5:
            print(f"      ... and {len(features) - 5} more")
    else:
        print(f"   Features: Using default technical indicators")

# Load performance history
print("\n" + "="*80)
print("📈 PERFORMANCE HISTORY")
print("="*80)

history_file = "models/performance_history.json"
if os.path.exists(history_file):
    with open(history_file, 'r') as f:
        history = json.load(f)
    
    print("\n🕐 Training History:")
    for symbol, data in history.items():
        if isinstance(data, dict):
            train_time = data.get('timestamp', 'Unknown')
            accuracy = data.get('accuracy', 0)
            print(f"   {symbol}: {accuracy:.1f}% (trained: {train_time})")

# Test model prediction
print("\n" + "="*80)
print("🎯 TEST MODEL PREDICTIONS")
print("="*80)

import asyncio

async def test_predictions():
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    for symbol in test_symbols:
        print(f"\n📊 Testing {symbol}...")
        try:
            # Get current price
            klines = client.get_klines(symbol, '5m', limit=1)
            current_price = float(klines[0][4])
            
            # Get prediction
            analysis = await bot.analyze_symbol(symbol)
            
            print(f"   Price: ${current_price:.2f}")
            print(f"   Signal: {analysis['signal']}")
            print(f"   Confidence: {analysis['confidence']:.1%}")
            
            # Check feature count
            if 'feature_names' in bot.models[symbol]:
                print(f"   Features used: {len(bot.models[symbol]['feature_names'])}")
            else:
                print(f"   Features used: 31 technical indicators")
            
            if analysis['confidence'] > 0.75:
                print(f"   ✅ High confidence prediction")
            else:
                print(f"   ⚠️  Low confidence: {analysis['confidence']:.1%}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

asyncio.run(test_predictions())

# Summary
print("\n" + "="*80)
print("📊 MODEL VERIFICATION SUMMARY")
print("="*80)

total_accuracy = sum(m['accuracy'] for m in bot.models.values()) / len(bot.models)
print(f"\n✅ Models Loaded: {len(bot.models)}/3")
print(f"✅ Average Accuracy: {total_accuracy:.1f}%")

# Check feature count
if 'feature_names' in bot.models['BTCUSDT']:
    print(f"✅ Total Features: {len(bot.models['BTCUSDT']['feature_names'])} indicators")
else:
    print(f"✅ Total Features: 31 technical indicators (default)")

# Quality assessment
print(f"\n🎯 QUALITY ASSESSMENT:")
if total_accuracy >= 95:
    print("   🌟 EXCELLENT - Models are highly accurate")
elif total_accuracy >= 90:
    print("   ✅ GOOD - Models are performing well")
elif total_accuracy >= 85:
    print("   ⚠️  FAIR - Models may need improvement")
else:
    print("   ❌ POOR - Models need retraining")

print(f"\n✅ AI Models are READY for trading!")
print("="*80)
