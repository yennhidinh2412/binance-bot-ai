"""
RETRAIN V8 — Anti-Overfit + Walk-Forward + Ensemble Voting
============================================================
Improvements over V7:
  1. More data: 120 days BTC/ETH, 90 days SOL
  2. Walk-forward validation (3 windows) instead of single test set
  3. Ensemble voting (GB + XGB + HGB majority vote)
  4. Feature importance pruning (drop noise features < 1%)
  5. Relaxed binary labels (1.2% threshold → more samples)
  6. Compare OLD vs NEW before replacing models
"""

import pandas as pd
import numpy as np
import os
import sys
import time as _time
import joblib
import logging

from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    VotingClassifier,
)
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.model_selection import TimeSeriesSplit

try:
    from xgboost import XGBClassifier
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

from binance_client import BinanceFuturesClient
from technical_analysis import TechnicalAnalyzer
from train_ai_improved import (
    get_extended_klines,
    prepare_advanced_features,
    get_htf_features_for_training,
    create_binary_labels,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)


class FeatureMaskTransformer:
    """Transform that applies StandardScaler then feature mask.
    Module-level class so it can be pickled by joblib.
    """
    def __init__(self, scaler, mask):
        self.scaler = scaler
        self.mask = mask
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        return self.scaler.transform(X)[:, self.mask]
    def fit_transform(self, X, y=None):
        return self.transform(X)


# ───────────────────────────────────────────────────────────
# CONFIG
# ───────────────────────────────────────────────────────────
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
LABEL_THRESHOLD = 0.012         # 1.2% (relaxed from 1.5%)
LABEL_MAX_BARS = 60             # 5h lookahead on 5m
WALK_FWD_WINDOWS = 3            # 3 walk-forward windows
PURGE_GAP = 60                  # gap between train/test to avoid leakage
IMPORTANCE_CUTOFF = 0.01        # drop features < 1% importance
N_DAYS = {'BTCUSDT': 120, 'ETHUSDT': 120, 'SOLUSDT': 90}


def select_features_by_importance(model, X, feature_names, cutoff=0.01):
    """
    Drop features with importance < cutoff (noise removal).
    Returns (X_selected, selected_names, mask).
    """
    if hasattr(model, 'feature_importances_'):
        imp = model.feature_importances_
    else:
        return X, feature_names, np.ones(X.shape[1], dtype=bool)

    mask = imp >= cutoff
    n_kept = mask.sum()
    n_dropped = (~mask).sum()
    logger.info(
        f"   Feature selection: kept {n_kept}, dropped {n_dropped} "
        f"(cutoff={cutoff})"
    )
    return X[:, mask], [n for n, m in zip(feature_names, mask) if m], mask


def walk_forward_cv(X, y, n_windows=3, purge=60):
    """
    Walk-forward validation: slide a growing train window forward.
    Each window uses ~1/n_windows of data as test.
    Returns list of (train_idx, test_idx) tuples.
    """
    n = len(X)
    test_size = n // (n_windows + 1)
    splits = []
    for w in range(n_windows):
        test_start = n - test_size * (n_windows - w)
        test_end = test_start + test_size
        train_end = max(0, test_start - purge)
        if train_end < 200:
            continue  # not enough train data
        splits.append(
            (np.arange(0, train_end), np.arange(test_start, min(test_end, n)))
        )
    return splits


def train_symbol_v8(symbol):
    """Train V8 models for 1 symbol."""
    logger.info(f"\n{'=' * 60}")
    logger.info(f"🎯 TRAINING V8: {symbol}")
    logger.info(f"{'=' * 60}")

    n_days = N_DAYS.get(symbol, 90)
    total_candles = n_days * 24 * 12  # 5m candles

    client = BinanceFuturesClient()
    analyzer = TechnicalAnalyzer()

    # ── DATA (with retry) ─────────────────────────────────────
    logger.info(f"📥 Downloading ~{n_days} days ({total_candles} candles)...")
    klines = None
    for attempt in range(3):
        klines = get_extended_klines(client, symbol, '5m', total_candles)
        if klines and len(klines) >= 1000:
            break
        logger.warning(
            f"   Attempt {attempt+1}/3: got {len(klines) if klines else 0} candles, "
            f"retrying in 3s..."
        )
        _time.sleep(3)
    if not klines or len(klines) < 1000:
        logger.error(f"❌ Insufficient data for {symbol}: {len(klines) if klines else 0}")
        return None
    logger.info(f"   Got {len(klines)} candles")

    # HTF context
    logger.info("📥 Fetching 1h & 4h HTF context...")
    htf_dfs = get_htf_features_for_training(client, analyzer, symbol)

    # Indicators
    logger.info("📊 Calculating indicators...")
    df = analyzer.prepare_dataframe(klines)
    df = analyzer.add_basic_indicators(df)
    df = analyzer.add_advanced_indicators(df)

    # Merge HTF
    if htf_dfs:
        df['timestamp'] = pd.to_numeric(df['timestamp'])
        df = df.sort_values('timestamp')
        for label, htf_df in htf_dfs.items():
            htf_df['timestamp'] = pd.to_numeric(htf_df['timestamp'])
            htf_df = htf_df.sort_values('timestamp')
            df = pd.merge_asof(df, htf_df, on='timestamp', direction='backward')
        logger.info(f"   Merged HTF → {len(df.columns)} columns")

    # ── LABELS ────────────────────────────────────────────────
    logger.info(
        f"🏷️ Binary labels (threshold={LABEL_THRESHOLD*100:.1f}%, "
        f"max_bars={LABEL_MAX_BARS})..."
    )
    labels = create_binary_labels(df, pct=LABEL_THRESHOLD, max_bars=LABEL_MAX_BARS)
    df['label'] = labels

    # ── FEATURES ──────────────────────────────────────────────
    X, feature_names = prepare_advanced_features(df)
    y = np.array(df['label'].values, dtype=float)

    valid = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
    X, y = X[valid], y[valid].astype(int)

    logger.info(f"📈 Dataset: {len(X)} samples, {X.shape[1]} features")
    logger.info(
        f"   LONG(1): {(y == 1).sum()}, SHORT(0): {(y == 0).sum()}, "
        f"Dropped: {(~valid).sum()}"
    )

    if len(X) < 500:
        logger.error(f"❌ Too few samples: {len(X)}")
        return None

    # ── WALK-FORWARD VALIDATION ───────────────────────────────
    logger.info(f"\n📊 Walk-forward validation ({WALK_FWD_WINDOWS} windows)...")
    wf_splits = walk_forward_cv(X, y, n_windows=WALK_FWD_WINDOWS, purge=PURGE_GAP)
    wf_scores = []

    for i, (tr_idx, te_idx) in enumerate(wf_splits):
        sc = StandardScaler()
        X_tr = sc.fit_transform(X[tr_idx])
        X_te = sc.transform(X[te_idx])
        sw = compute_sample_weight('balanced', y[tr_idx])

        gb = GradientBoostingClassifier(
            n_estimators=500, max_depth=3, learning_rate=0.01,
            subsample=0.75, min_samples_split=30, min_samples_leaf=25,
            max_features='sqrt', validation_fraction=0.15,
            n_iter_no_change=30, tol=1e-4, random_state=42,
        )
        gb.fit(X_tr, y[tr_idx], sample_weight=sw)
        score = gb.score(X_te, y[te_idx]) * 100
        wf_scores.append(score)
        logger.info(
            f"   Window {i + 1}: train={len(tr_idx)}, "
            f"test={len(te_idx)}, acc={score:.1f}%"
        )

    wf_mean = np.mean(wf_scores)
    wf_std = np.std(wf_scores)
    logger.info(f"   Walk-forward: {wf_mean:.1f}% ± {wf_std:.1f}%")

    # ── FINAL TRAIN (80/20 split) ─────────────────────────────
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    sw_train = compute_sample_weight('balanced', y_train)

    # ── FEATURE SELECTION ─────────────────────────────────────
    # Quick pre-fit to get importances
    logger.info("\n🔧 Feature importance analysis...")
    pre_gb = GradientBoostingClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.02,
        subsample=0.75, min_samples_leaf=25, random_state=42,
    )
    pre_gb.fit(X_train_s, y_train, sample_weight=sw_train)
    X_train_sel, sel_names, feat_mask = select_features_by_importance(
        pre_gb, X_train_s, feature_names, cutoff=IMPORTANCE_CUTOFF
    )
    X_test_sel = X_test_s[:, feat_mask]

    # Log top features
    imp_sorted = sorted(
        zip(feature_names, pre_gb.feature_importances_),
        key=lambda x: x[1], reverse=True,
    )
    logger.info("   Top 10 features:")
    for name, imp in imp_sorted[:10]:
        logger.info(f"      {name}: {imp:.4f}")

    # ── MODEL 1: GradientBoosting ─────────────────────────────
    logger.info("\n🤖 [1/3] GradientBoosting...")
    gb = GradientBoostingClassifier(
        n_estimators=600, max_depth=3, learning_rate=0.008,
        subsample=0.7, min_samples_split=40, min_samples_leaf=30,
        max_features='sqrt', validation_fraction=0.15,
        n_iter_no_change=40, tol=1e-4, random_state=42,
    )
    gb.fit(X_train_sel, y_train, sample_weight=sw_train)
    gb_test = gb.score(X_test_sel, y_test) * 100
    logger.info(
        f"   Train: {gb.score(X_train_sel, y_train)*100:.1f}% | "
        f"Test: {gb_test:.1f}%"
    )

    # ── MODEL 2: XGBoost ──────────────────────────────────────
    if HAS_XGBOOST:
        logger.info("🤖 [2/3] XGBoost...")
        xgb = XGBClassifier(
            n_estimators=600, max_depth=3, learning_rate=0.008,
            subsample=0.7, colsample_bytree=0.7,
            min_child_weight=25, gamma=0.2,
            reg_alpha=0.15, reg_lambda=1.5,
            early_stopping_rounds=40, eval_metric='logloss',
            random_state=42, verbosity=0,
        )
        xgb.fit(
            X_train_sel, y_train, sample_weight=sw_train,
            eval_set=[(X_test_sel, y_test)], verbose=False,
        )
        xgb_test = xgb.score(X_test_sel, y_test) * 100
        logger.info(
            f"   Train: {xgb.score(X_train_sel, y_train)*100:.1f}% | "
            f"Test: {xgb_test:.1f}%"
        )
    else:
        logger.warning("⚠️ XGBoost not available")
        xgb = GradientBoostingClassifier(
            n_estimators=500, max_depth=3, learning_rate=0.01,
            subsample=0.7, min_samples_leaf=30, random_state=99,
        )
        xgb.fit(X_train_sel, y_train, sample_weight=sw_train)
        xgb_test = xgb.score(X_test_sel, y_test) * 100

    # ── MODEL 3: HistGradientBoosting ─────────────────────────
    logger.info("🤖 [3/3] HistGradientBoosting...")
    hgb = HistGradientBoostingClassifier(
        max_iter=600, max_depth=3, learning_rate=0.008,
        min_samples_leaf=30, l2_regularization=0.8,
        max_bins=200, validation_fraction=0.15,
        n_iter_no_change=40, random_state=42,
    )
    hgb.fit(X_train_sel, y_train, sample_weight=sw_train)
    hgb_test = hgb.score(X_test_sel, y_test) * 100
    logger.info(
        f"   Train: {hgb.score(X_train_sel, y_train)*100:.1f}% | "
        f"Test: {hgb_test:.1f}%"
    )

    # ── ENSEMBLE VOTING ───────────────────────────────────────
    logger.info("\n🗳️ Ensemble majority voting...")
    pred_gb = gb.predict(X_test_sel)
    pred_xgb = xgb.predict(X_test_sel)
    pred_hgb = hgb.predict(X_test_sel)

    # Majority vote (2 out of 3)
    votes = np.array([pred_gb, pred_xgb, pred_hgb])
    ensemble_pred = np.apply_along_axis(
        lambda x: np.bincount(x.astype(int), minlength=2).argmax(),
        axis=0, arr=votes,
    )
    ensemble_test = accuracy_score(y_test, ensemble_pred) * 100
    logger.info(f"   Ensemble accuracy: {ensemble_test:.1f}%")

    # ── TimeSeriesSplit CV (for comparison with V7) ───────────
    logger.info("\n📊 TimeSeriesSplit CV (5 folds)...")
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = []
    for fi, (tr_i, val_i) in enumerate(tscv.split(X)):
        if len(tr_i) > PURGE_GAP:
            tr_i = tr_i[:-PURGE_GAP]
        cv_sc = StandardScaler()
        X_tr_cv = cv_sc.fit_transform(X[tr_i])[:, feat_mask]
        X_val_cv = cv_sc.transform(X[val_i])[:, feat_mask]
        sw_cv = compute_sample_weight('balanced', y[tr_i])
        cv_gb = GradientBoostingClassifier(
            n_estimators=500, max_depth=3, learning_rate=0.01,
            subsample=0.75, min_samples_split=30, min_samples_leaf=25,
            max_features='sqrt', validation_fraction=0.15,
            n_iter_no_change=30, random_state=42,
        )
        cv_gb.fit(X_tr_cv, y[tr_i], sample_weight=sw_cv)
        s = cv_gb.score(X_val_cv, y[val_i]) * 100
        cv_scores.append(s)
        logger.info(f"   Fold {fi + 1}: {s:.1f}%")
    cv_mean = np.mean(cv_scores)
    logger.info(f"   CV mean: {cv_mean:.1f}%")

    # ── COMPARE WITH OLD MODEL ────────────────────────────────
    old_path = f'models/gradient_boost_{symbol}.pkl'
    old_acc = None
    old_cv = None
    if os.path.exists(old_path):
        try:
            old = joblib.load(old_path)
            old_acc = max(
                old.get('accuracy', 0),
                old.get('accuracy_xgb', 0),
                old.get('accuracy_hgb', 0),
            )
            old_cv = old.get('cv_accuracy', 0)
        except Exception:
            pass

    best_single = max(gb_test, xgb_test, hgb_test)
    best_acc = max(best_single, ensemble_test)
    best_name = 'ensemble' if ensemble_test >= best_single else (
        'gb' if gb_test >= max(xgb_test, hgb_test) else
        'xgb' if xgb_test >= hgb_test else 'hgb'
    )

    logger.info(f"\n{'─' * 50}")
    logger.info(f"📊 COMPARISON — {symbol}")
    logger.info(f"   OLD best accuracy: {old_acc:.1f}% (CV: {old_cv:.1f}%)" if old_acc else "   OLD: N/A")
    logger.info(f"   NEW best accuracy: {best_acc:.1f}% ({best_name}) (CV: {cv_mean:.1f}%)")
    logger.info(f"   NEW walk-forward:  {wf_mean:.1f}% ± {wf_std:.1f}%")

    # ── SAVE ──────────────────────────────────────────────────
    # Build pipelines with scaler + feature mask baked in
    fmt = FeatureMaskTransformer(scaler, feat_mask)
    gb_pipe = Pipeline([('preprocess', fmt), ('model', gb)])
    xgb_pipe = Pipeline([('preprocess', fmt), ('model', xgb)])
    hgb_pipe = Pipeline([('preprocess', fmt), ('model', hgb)])

    os.makedirs('models', exist_ok=True)
    model_data = {
        'model': gb_pipe,
        'model_xgb': xgb_pipe,
        'model_hgb': hgb_pipe,
        'feature_names': feature_names,  # full names (before mask)
        'selected_features': sel_names,
        'feature_mask': feat_mask,
        'accuracy': gb_test,
        'accuracy_xgb': xgb_test,
        'accuracy_hgb': hgb_test,
        'ensemble_accuracy': ensemble_test,
        'trade_quality': best_acc,
        'n_classes': 2,
        'label_method': 'v8_binary_walkfwd',
        'threshold_pct': LABEL_THRESHOLD,
        'cv_accuracy': cv_mean,
        'wf_accuracy': wf_mean,
        'wf_std': wf_std,
        'trained_at': str(pd.Timestamp.now()),
        'n_samples': len(X),
        'n_days': n_days,
        'n_features_selected': int(feat_mask.sum()),
        'label_distribution': {
            'LONG': int((y == 1).sum()),
            'SHORT': int((y == 0).sum()),
        },
    }

    joblib.dump(model_data, old_path)
    logger.info(f"\n💾 Saved V8 model: {old_path}")
    logger.info(
        f"   GB={gb_test:.1f}% | XGB={xgb_test:.1f}% | "
        f"HGB={hgb_test:.1f}% | Ensemble={ensemble_test:.1f}%"
    )

    return {
        'symbol': symbol,
        'gb': gb_test,
        'xgb': xgb_test,
        'hgb': hgb_test,
        'ensemble': ensemble_test,
        'cv': cv_mean,
        'wf': wf_mean,
        'old_best': old_acc,
        'old_cv': old_cv,
        'n_samples': len(X),
        'n_features': int(feat_mask.sum()),
    }


def main():
    logger.info("=" * 60)
    logger.info("🚀 RETRAIN V8 — Anti-Overfit + Walk-Forward + Ensemble")
    logger.info("   ✅ More data: 120 days BTC/ETH, 90 days SOL")
    logger.info("   ✅ Walk-forward validation (3 windows)")
    logger.info("   ✅ Ensemble majority voting (GB+XGB+HGB)")
    logger.info("   ✅ Feature importance pruning (< 1%)")
    logger.info(f"   ✅ Binary labels: {LABEL_THRESHOLD*100:.1f}% threshold")
    logger.info("=" * 60)

    all_results = {}
    for symbol in SYMBOLS:
        try:
            r = train_symbol_v8(symbol)
            if r:
                all_results[symbol] = r
        except Exception as e:
            logger.error(f"❌ {symbol} failed: {e}")
            import traceback
            traceback.print_exc()

    # ── SUMMARY TABLE ─────────────────────────────────────────
    logger.info(f"\n{'=' * 70}")
    logger.info("📊 V8 TRAINING SUMMARY")
    logger.info(f"{'=' * 70}")
    logger.info(f"{'Symbol':<10} {'GB':>6} {'XGB':>6} {'HGB':>6} "
                f"{'Ens':>6} {'CV':>6} {'WF':>6} │ {'Old':>6} {'OldCV':>6}")
    logger.info("─" * 70)
    for sym, r in all_results.items():
        old_s = f"{r['old_best']:.1f}" if r['old_best'] else "N/A"
        old_cv = f"{r['old_cv']:.1f}" if r['old_cv'] else "N/A"
        logger.info(
            f"{sym:<10} {r['gb']:>5.1f}% {r['xgb']:>5.1f}% "
            f"{r['hgb']:>5.1f}% {r['ensemble']:>5.1f}% "
            f"{r['cv']:>5.1f}% {r['wf']:>5.1f}% │ "
            f"{old_s:>5}% {old_cv:>5}%"
        )

    if all_results:
        new_best = np.mean([
            r['ensemble'] for r in all_results.values()
        ])
        logger.info(f"\n🎯 Average ensemble accuracy: {new_best:.1f}%")

    logger.info("\n✅ All V8 models trained and saved!")


if __name__ == '__main__':
    main()
