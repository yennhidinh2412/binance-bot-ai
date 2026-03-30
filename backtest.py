"""
BACKTEST MODULE v1.0
Kiểm tra chiến lược trên dữ liệu lịch sử
Tính toán win rate, profit factor, max drawdown, Sharpe ratio
"""
import json
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from loguru import logger

from binance_client import BinanceFuturesClient
from technical_analysis import TechnicalAnalyzer
from train_ai_improved import prepare_advanced_features

try:
    from advanced_ai_engine import AdvancedAIEngine, EnsemblePredictor
    HAS_ADVANCED_AI = True
except ImportError:
    HAS_ADVANCED_AI = False


class Backtester:
    """
    Backtester cho AI Trading Bot
    - Simulate trading trên dữ liệu lịch sử
    - Tính metrics: win rate, profit factor, max DD, Sharpe
    - Hỗ trợ trailing stop, breakeven, partial TP
    """

    def __init__(self, initial_balance=10000.0):
        self.client = BinanceFuturesClient()
        self.analyzer = TechnicalAnalyzer()
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.peak_balance = initial_balance

        # Load models
        self.models = {}
        self._load_models()

        # Results tracking
        self.trades = []
        self.equity_curve = []
        self.max_drawdown = 0
        self.max_drawdown_pct = 0

    def _load_models(self):
        """Load trained models"""
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        for symbol in symbols:
            try:
                path = f'models/gradient_boost_{symbol}.pkl'
                if os.path.exists(path):
                    self.models[symbol] = joblib.load(path)
                    logger.info(f"Loaded model: {symbol}")
            except Exception as e:
                logger.warning(f"No model for {symbol}: {e}")

    def run_backtest(
        self,
        symbol='BTCUSDT',
        interval='5m',
        num_candles=500,
        leverage=15,
        sl_pct=1.5,
        tp_pct=3.0,
        trailing_pct=0.8,
        breakeven_pct=1.0,
        min_confidence=70,
        min_adx=20,
        position_size_pct=30,
    ):
        """
        Chạy backtest cho 1 symbol

        Args:
            symbol: Trading pair
            interval: Timeframe
            num_candles: Số nến lịch sử
            leverage: Đòn bẩy
            sl_pct: Stop loss %
            tp_pct: Take profit %
            trailing_pct: Trailing stop %
            breakeven_pct: Breakeven trigger %
            min_confidence: Min AI confidence
            min_adx: Min ADX for trending
            position_size_pct: % balance mỗi lệnh
        """
        logger.info(f"\n{'='*50}")
        logger.info(f"BACKTEST: {symbol} | {interval}")
        logger.info(f"Leverage: {leverage}x | SL: {sl_pct}%")
        logger.info(f"TP: {tp_pct}% | Trail: {trailing_pct}%")
        logger.info(f"{'='*50}")

        if symbol not in self.models:
            logger.error(f"No model for {symbol}")
            return None

        # Get historical data
        klines = self.client.get_klines(
            symbol, interval, num_candles
        )
        if not klines or len(klines) < 100:
            logger.error("Not enough data")
            return None

        df = self.analyzer.prepare_dataframe(klines)
        df = self.analyzer.add_basic_indicators(df)
        df = self.analyzer.add_advanced_indicators(df)

        # Prepare features
        try:
            X, _ = prepare_advanced_features(df)
        except Exception as e:
            logger.error(f"Feature prep error: {e}")
            return None

        model = self.models[symbol]['model']

        # Reset state
        self.balance = self.initial_balance
        self.peak_balance = self.initial_balance
        self.trades = []
        self.equity_curve = [self.initial_balance]
        self.max_drawdown = 0
        self.max_drawdown_pct = 0

        # Simulate
        position = None  # Current position
        lookback = 50  # Skip first N candles

        for i in range(lookback, len(X)):
            row = df.iloc[i + (len(df) - len(X))]
            price = float(row['close'])
            high = float(row['high'])
            low = float(row['low'])

            # Check ADX filter
            adx = float(row.get('adx', 30))
            if adx < min_adx:
                # If in position, still manage it
                if position:
                    position = self._manage_position(
                        position, price, high, low,
                        trailing_pct, breakeven_pct
                    )
                self.equity_curve.append(self.balance)
                continue

            # If in position, manage it
            if position:
                position = self._manage_position(
                    position, price, high, low,
                    trailing_pct, breakeven_pct
                )

                # Check if closed
                if position is None:
                    self.equity_curve.append(self.balance)
                    continue

                self.equity_curve.append(self.balance)
                continue

            # Get prediction
            try:
                features = X[i].reshape(1, -1)
                pred = model.predict(features)[0]
                proba = model.predict_proba(features)[0]
                class_idx = int(pred) + 1
                confidence = proba[class_idx] * 100
            except Exception:
                self.equity_curve.append(self.balance)
                continue

            # Signal
            signal_map = {-1: 'SHORT', 0: 'HOLD', 1: 'LONG'}
            signal = signal_map.get(pred, 'HOLD')

            if signal == 'HOLD' or confidence < min_confidence:
                self.equity_curve.append(self.balance)
                continue

            # Open position
            pos_value = self.balance * (
                position_size_pct / 100
            )
            qty = (pos_value * leverage) / price

            if signal == 'LONG':
                sl = price * (1 - sl_pct / 100)
                tp = price * (1 + tp_pct / 100)
            else:
                sl = price * (1 + sl_pct / 100)
                tp = price * (1 - tp_pct / 100)

            position = {
                'signal': signal,
                'entry_price': price,
                'quantity': qty,
                'stop_loss': sl,
                'take_profit': tp,
                'entry_idx': i,
                'highest': price,
                'lowest': price,
                'breakeven_moved': False,
                'leverage': leverage,
                'confidence': confidence,
            }

            self.equity_curve.append(self.balance)

        # Close any open position at end
        if position:
            last_price = float(df['close'].iloc[-1])
            self._close_position(
                position, last_price, 'END'
            )

        return self._generate_report(symbol, interval)

    def _manage_position(
        self, pos, price, high, low,
        trailing_pct, breakeven_pct
    ):
        """Manage open position: check SL/TP/trailing"""
        entry = pos['entry_price']
        signal = pos['signal']
        sl = pos['stop_loss']
        tp = pos['take_profit']

        # Update tracking
        pos['highest'] = max(pos['highest'], high)
        pos['lowest'] = min(pos['lowest'], low)

        if signal == 'LONG':
            profit_pct = (price - entry) / entry * 100

            # Check SL hit
            if low <= sl:
                self._close_position(pos, sl, 'SL')
                return None

            # Check TP hit
            if high >= tp:
                self._close_position(pos, tp, 'TP')
                return None

            # Breakeven
            if (
                not pos['breakeven_moved']
                and profit_pct >= breakeven_pct
            ):
                pos['stop_loss'] = entry * 1.001
                pos['breakeven_moved'] = True

            # Trailing stop
            if pos['breakeven_moved']:
                new_trail = price * (1 - trailing_pct / 100)
                if new_trail > pos['stop_loss']:
                    pos['stop_loss'] = new_trail

        else:  # SHORT
            profit_pct = (entry - price) / entry * 100

            # Check SL hit
            if high >= sl:
                self._close_position(pos, sl, 'SL')
                return None

            # Check TP hit
            if low <= tp:
                self._close_position(pos, tp, 'TP')
                return None

            # Breakeven
            if (
                not pos['breakeven_moved']
                and profit_pct >= breakeven_pct
            ):
                pos['stop_loss'] = entry * 0.999
                pos['breakeven_moved'] = True

            # Trailing stop
            if pos['breakeven_moved']:
                new_trail = price * (1 + trailing_pct / 100)
                if new_trail < pos['stop_loss']:
                    pos['stop_loss'] = new_trail

        return pos

    def _close_position(self, pos, exit_price, reason):
        """Close position and record result"""
        entry = pos['entry_price']
        signal = pos['signal']
        leverage = pos['leverage']
        qty = pos['quantity']

        if signal == 'LONG':
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        # PnL in dollars (with leverage)
        pnl_dollar = (
            qty * abs(exit_price - entry)
            * (1 if pnl_pct > 0 else -1)
        )
        self.balance += pnl_dollar

        # Track drawdown
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        dd = self.peak_balance - self.balance
        dd_pct = (
            dd / self.peak_balance * 100
            if self.peak_balance > 0 else 0
        )
        if dd_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = dd_pct
            self.max_drawdown = dd

        self.trades.append({
            'signal': signal,
            'entry': entry,
            'exit': exit_price,
            'pnl_pct': pnl_pct,
            'pnl_dollar': pnl_dollar,
            'reason': reason,
            'confidence': pos.get('confidence', 0),
            'breakeven_hit': pos.get('breakeven_moved', False),
        })

    def _generate_report(self, symbol, interval):
        """Generate backtest report"""
        if not self.trades:
            logger.warning("No trades executed")
            return {
                'symbol': symbol,
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'avg_win_pct': 0,
                'avg_loss_pct': 0,
                'profit_factor': 0,
                'net_pnl': 0,
                'net_pnl_pct': 0,
                'max_drawdown_pct': 0,
                'sharpe_ratio': 0,
                'final_balance': self.balance,
                'message': 'No trades'
            }

        wins = [t for t in self.trades if t['pnl_pct'] > 0]
        losses = [t for t in self.trades if t['pnl_pct'] <= 0]

        total = len(self.trades)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = win_count / total * 100

        total_profit = sum(
            t['pnl_dollar'] for t in wins
        )
        total_loss = abs(sum(
            t['pnl_dollar'] for t in losses
        ))
        profit_factor = (
            total_profit / total_loss
            if total_loss > 0 else float('inf')
        )

        avg_win = (
            np.mean([t['pnl_pct'] for t in wins])
            if wins else 0
        )
        avg_loss = (
            np.mean([t['pnl_pct'] for t in losses])
            if losses else 0
        )

        # Sharpe ratio (simplified)
        returns = [t['pnl_pct'] for t in self.trades]
        if len(returns) > 1:
            sharpe = (
                np.mean(returns) / np.std(returns)
                * np.sqrt(252)
                if np.std(returns) > 0 else 0
            )
        else:
            sharpe = 0

        # Net PnL
        net_pnl = self.balance - self.initial_balance
        net_pnl_pct = net_pnl / self.initial_balance * 100

        # SL/TP breakdown
        sl_count = sum(
            1 for t in self.trades if t['reason'] == 'SL'
        )
        tp_count = sum(
            1 for t in self.trades if t['reason'] == 'TP'
        )
        be_count = sum(
            1 for t in self.trades
            if t.get('breakeven_hit', False)
        )

        report = {
            'symbol': symbol,
            'interval': interval,
            'total_trades': total,
            'wins': win_count,
            'losses': loss_count,
            'win_rate': round(win_rate, 1),
            'avg_win_pct': round(avg_win, 2),
            'avg_loss_pct': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'net_pnl': round(net_pnl, 2),
            'net_pnl_pct': round(net_pnl_pct, 2),
            'max_drawdown_pct': round(
                self.max_drawdown_pct, 2
            ),
            'sharpe_ratio': round(sharpe, 2),
            'sl_hits': sl_count,
            'tp_hits': tp_count,
            'breakeven_activations': be_count,
            'final_balance': round(self.balance, 2),
        }

        # Print report
        logger.info(f"\n{'='*50}")
        logger.info(f"📊 BACKTEST REPORT: {symbol}")
        logger.info(f"{'='*50}")
        logger.info(f"Total Trades: {total}")
        logger.info(
            f"Win/Loss: {win_count}/{loss_count} "
            f"({win_rate:.1f}%)"
        )
        logger.info(
            f"Avg Win: +{avg_win:.2f}% | "
            f"Avg Loss: {avg_loss:.2f}%"
        )
        logger.info(
            f"Profit Factor: {profit_factor:.2f}"
        )
        logger.info(
            f"Net PnL: ${net_pnl:+.2f} "
            f"({net_pnl_pct:+.1f}%)"
        )
        logger.info(
            f"Max Drawdown: {self.max_drawdown_pct:.1f}%"
        )
        logger.info(f"Sharpe Ratio: {sharpe:.2f}")
        logger.info(
            f"SL hits: {sl_count} | "
            f"TP hits: {tp_count} | "
            f"Breakeven: {be_count}"
        )
        logger.info(
            f"Final Balance: ${self.balance:,.2f}"
        )
        logger.info(f"{'='*50}")

        return report

    def run_full_backtest(self, **kwargs):
        """Run backtest for all 3 symbols"""
        symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        results = {}

        for symbol in symbols:
            if symbol in self.models:
                result = self.run_backtest(
                    symbol=symbol, **kwargs
                )
                if result:
                    results[symbol] = result

        # Summary
        if results:
            logger.info(f"\n{'='*50}")
            logger.info("📊 FULL BACKTEST SUMMARY")
            logger.info(f"{'='*50}")

            total_trades = sum(
                r['total_trades'] for r in results.values()
            )
            total_wins = sum(
                r['wins'] for r in results.values()
            )
            avg_wr = (
                total_wins / total_trades * 100
                if total_trades > 0 else 0
            )
            avg_pf = np.mean([
                r['profit_factor']
                for r in results.values()
                if r['profit_factor'] < float('inf')
            ]) if results else 0
            max_dd = max(
                r['max_drawdown_pct']
                for r in results.values()
            )

            logger.info(f"Total Trades: {total_trades}")
            logger.info(f"Overall Win Rate: {avg_wr:.1f}%")
            logger.info(f"Avg Profit Factor: {avg_pf:.2f}")
            logger.info(f"Max Drawdown: {max_dd:.1f}%")

            for sym, r in results.items():
                logger.info(
                    f"  {sym}: WR={r['win_rate']}% "
                    f"PF={r['profit_factor']} "
                    f"PnL={r['net_pnl_pct']:+.1f}%"
                )

        return results


if __name__ == '__main__':
    bt = Backtester(initial_balance=10000)
    results = bt.run_full_backtest(
        num_candles=500,
        leverage=15,
        sl_pct=1.5,
        tp_pct=3.0,
        trailing_pct=0.8,
        breakeven_pct=1.0,
        min_confidence=70,
        min_adx=20,
        position_size_pct=30,
    )

    # Save results
    if results:
        with open('models/backtest_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        logger.info("Results saved to backtest_results.json")
