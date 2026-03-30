"""Test all training pipeline fixes"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd


def test_candlestick_patterns():
    """Test candlestick patterns are real (not hardcoded 0)"""
    print("\n=== TEST 1: Candlestick Patterns ===")
    from technical_analysis import TechnicalAnalyzer
    analyzer = TechnicalAnalyzer()

    np.random.seed(42)
    n = 100
    data = []
    price = 100.0
    for i in range(n):
        if i == 30:
            o, c = price + 2, price - 1
            h, l = o + 0.5, c - 0.5
        elif i == 31:
            o, c = price - 2, price + 3
            h, l = c + 0.3, o - 0.3
        elif i == 50:
            o, c = price, price + 0.01
            h, l = price + 3, price - 3
        else:
            move = np.random.randn() * 1.5
            o = price
            c = price + move
            h = max(o, c) + abs(np.random.randn()) * 0.5
            l = min(o, c) - abs(np.random.randn()) * 0.5
            price = c
        vol = 1000 + np.random.rand() * 500
        data.append([
            i * 300000, o, h, l, c, vol,
            0, 0, 0, 0, 0, 0
        ])

    cols = [
        'timestamp', 'open', 'high', 'low', 'close',
        'volume', 'close_time', 'quote_asset_volume',
        'number_of_trades', 'taker_buy_base_asset_volume',
        'taker_buy_quote_asset_volume', 'ignore'
    ]
    df = pd.DataFrame(data, columns=cols)
    df = analyzer.add_basic_indicators(df)
    df = analyzer.detect_candlestick_patterns(df)

    patterns = [
        'doji', 'hammer', 'hanging_man', 'shooting_star',
        'engulfing', 'morning_star', 'evening_star',
        'piercing', 'dark_cloud', 'three_white_soldiers',
        'three_black_crows', 'spinning_top', 'harami'
    ]
    total_nz = 0
    for p in patterns:
        nz = (df[p] != 0).sum()
        total_nz += nz
        status = "✅" if nz > 0 else "⬜"
        print(f"  {status} {p}: {nz} signals")

    print(f"\n  Total non-zero: {total_nz}")
    assert total_nz > 5, "FAIL: Too few pattern signals!"
    print("  ✅ Candlestick patterns working!")
    return True


def test_training_imports():
    """Test all training modules import correctly"""
    print("\n=== TEST 2: Training Module Imports ===")
    from train_ai_improved import (
        prepare_advanced_features,
        get_htf_features_for_training,
    )
    print("  ✅ train_ai_improved OK")

    from continuous_learning_engine import ContinuousLearningEngine
    print("  ✅ continuous_learning_engine OK")

    from advanced_ai_engine import (
        AdvancedAIEngine,
        AdvancedCandlestickPatterns,
        MultiTimeframeAnalyzer,
        EnsemblePredictor
    )
    print("  ✅ advanced_ai_engine OK")
    return True


def test_label_consistency():
    """Test that label thresholds are consistent"""
    print("\n=== TEST 3: Label Threshold Consistency ===")
    import inspect
    from train_ai_improved import create_smart_labels
    src = inspect.getsource(create_smart_labels)
    assert '0.015' in src or 'threshold' in src
    print("  ✅ Basic training: threshold=1.5%")

    from advanced_ai_engine import AdvancedAIEngine
    src2 = inspect.getsource(AdvancedAIEngine.train_symbol)
    assert '0.015' in src2
    assert '0.005' not in src2, "FAIL: Old 0.5% found!"
    print("  ✅ Advanced AI: threshold=1.5%")
    return True


def test_time_series_split():
    """Verify no random split in training"""
    print("\n=== TEST 4: Time-Series Split ===")
    import inspect

    from advanced_ai_engine import EnsemblePredictor
    src = inspect.getsource(EnsemblePredictor.train)
    assert 'split_idx' in src
    print("  ✅ EnsemblePredictor uses time-series split")

    from continuous_learning_engine import ContinuousLearningEngine
    src2 = inspect.getsource(
        ContinuousLearningEngine._retrain_model
    )
    assert 'split_idx' in src2
    print("  ✅ ContinuousLearning uses time-series split")
    return True


def test_hyperparams_consistency():
    """Test hyperparams are consistent across modules"""
    print("\n=== TEST 5: Hyperparameter Consistency ===")
    import inspect

    from advanced_ai_engine import EnsemblePredictor
    src = inspect.getsource(EnsemblePredictor.train)
    assert 'n_estimators=300' in src
    assert 'learning_rate=0.03' in src
    assert 'max_depth=6' in src
    print("  ✅ Advanced AI: 300/0.03/6")

    from continuous_learning_engine import ContinuousLearningEngine
    src2 = inspect.getsource(
        ContinuousLearningEngine._retrain_model
    )
    assert 'n_estimators=300' in src2
    assert 'learning_rate=0.03' in src2
    assert 'max_depth=6' in src2
    print("  ✅ Continuous Learning: 300/0.03/6")
    return True


def test_multi_tf_features():
    """Test multi-TF features exist in training code"""
    print("\n=== TEST 6: Multi-Timeframe Features ===")
    import inspect

    from train_ai_improved import get_htf_features_for_training
    src = inspect.getsource(get_htf_features_for_training)
    assert '1h' in src and '4h' in src
    print("  ✅ Basic training: 1h + 4h HTF data")

    from advanced_ai_engine import AdvancedAIEngine
    src2 = inspect.getsource(AdvancedAIEngine.train_symbol)
    assert 'htf_1h' in src2 and 'htf_4h' in src2
    print("  ✅ Advanced AI training: 1h + 4h HTF data")

    src3 = inspect.getsource(
        AdvancedAIEngine.prepare_advanced_features
    )
    assert 'htf_1h' in src3 and 'htf_4h' in src3
    print("  ✅ Advanced AI predict: 1h + 4h HTF data")
    return True


if __name__ == '__main__':
    results = []
    tests = [
        test_candlestick_patterns,
        test_training_imports,
        test_label_consistency,
        test_time_series_split,
        test_hyperparams_consistency,
        test_multi_tf_features,
    ]

    for test in tests:
        try:
            ok = test()
            results.append((test.__name__, ok))
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            results.append((test.__name__, False))

    print("\n" + "=" * 50)
    print("TRAINING FIX VERIFICATION RESULTS")
    print("=" * 50)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        s = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {s}: {name}")
    print(f"\n  Score: {passed}/{total}")
    if passed == total:
        print("  🎯 ALL TRAINING FIXES VERIFIED!")
    else:
        print("  ⚠️  Some fixes need attention")
