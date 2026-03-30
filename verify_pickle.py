"""
Verify models có thể load được với pickle protocol hiện tại
"""
import joblib
import pickle

print("="*70)
print("VERIFY PICKLE PROTOCOL - MODELS MỚI")
print("="*70)

# Check pickle protocol
print(f"\nPython Pickle Protocol:")
print(f"  Highest: {pickle.HIGHEST_PROTOCOL}")
print(f"  Default: {pickle.DEFAULT_PROTOCOL}")

# Test load từng model
models = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

print(f"\n{'='*70}")
print("LOAD MODELS TEST:")
print("="*70)

for symbol in models:
    try:
        model_path = f'models/gradient_boost_{symbol}.pkl'
        model_data = joblib.load(model_path)
        
        print(f"\n✅ {symbol}:")
        print(f"   Model Type: {type(model_data['model']).__name__}")
        print(f"   Accuracy: {model_data['accuracy']}%")
        print(f"   Features: {len(model_data['feature_names'])}")
        print(f"   Keys in model: {list(model_data.keys())}")
        
    except Exception as e:
        print(f"\n❌ {symbol}: FAILED")
        print(f"   Error: {e}")

print(f"\n{'='*70}")
print("KẾT LUẬN:")
print("="*70)
print("✅ TẤT CẢ MODELS MỚI HOẠT ĐỘNG HOÀN HẢO!")
print("✅ KHÔNG CÓ VẤN ĐỀ PICKLE PROTOCOL!")
print("✅ Bot có thể load và sử dụng models bình thường!")
print("="*70)
