"""
Demo Trading Account - Simulated trading for testing
"""

from datetime import datetime
from typing import Dict, List


class DemoTradingAccount:
    """Demo account for paper trading"""

    def __init__(self, initial_balance: float = 10000):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.positions: Dict = {}
        self.trade_history: List = []
        self.prices: Dict[str, float] = {}

    def update_price(self, symbol: str, price: float):
        """Update current price for a symbol"""
        self.prices[symbol] = price

    def get_balance(self) -> float:
        """Get current balance"""
        return self.balance
    
    def get_account_info(self) -> Dict:
        """Get account information"""
        total_wallet_balance = self.balance
        total_unrealized_pnl = 0
        
        # Calculate unrealized PnL from positions
        for pos in self.get_positions():
            total_unrealized_pnl += pos['pnl']
        
        return {
            'totalWalletBalance': total_wallet_balance,
            'totalUnrealizedProfit': total_unrealized_pnl,
            'availableBalance': total_wallet_balance + total_unrealized_pnl,
            'totalMarginBalance': total_wallet_balance + total_unrealized_pnl
        }
    
    def get_open_positions(self) -> List[Dict]:
        """Alias for get_positions"""
        return self.get_positions()

    def get_positions(self) -> List[Dict]:
        """Get all open positions"""
        positions_list = []
        for symbol, pos in self.positions.items():
            current_price = self.prices.get(symbol, pos['entry_price'])
            if pos['side'] == 'LONG':
                pnl = (current_price - pos['entry_price']) * pos['quantity']
                pnl_percent = ((current_price / pos['entry_price']) - 1) * 100
            else:  # SHORT
                pnl = (pos['entry_price'] - current_price) * pos['quantity']
                pnl_percent = ((pos['entry_price'] / current_price) - 1) * 100

            positions_list.append({
                'symbol': symbol,
                'side': pos['side'],
                'quantity': pos['quantity'],
                'entry_price': pos['entry_price'],
                'current_price': current_price,
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'leverage': pos['leverage']
            })
        return positions_list

    def open_position(self, symbol: str, side: str, quantity: float,
                      entry_price: float, leverage: int = 10) -> Dict:
        """Open a new position"""
        if symbol in self.positions:
            return {'success': False, 'error': 'Position already exists'}

        cost = (quantity * entry_price) / leverage
        if cost > self.balance:
            return {'success': False, 'error': 'Insufficient balance'}

        self.positions[symbol] = {
            'side': side,
            'quantity': quantity,
            'entry_price': entry_price,
            'leverage': leverage,
            'opened_at': datetime.now().isoformat()
        }

        self.balance -= cost

        trade = {
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': entry_price,
            'type': 'OPEN',
            'timestamp': datetime.now().isoformat()
        }
        self.trade_history.append(trade)

        return {'success': True, 'position': self.positions[symbol]}

    def close_position(self, symbol: str) -> Dict:
        """Close an existing position"""
        if symbol not in self.positions:
            return {'success': False, 'error': 'Position not found'}

        pos = self.positions[symbol]
        current_price = self.prices.get(symbol, pos['entry_price'])

        if pos['side'] == 'LONG':
            pnl = (current_price - pos['entry_price']) * pos['quantity']
        else:  # SHORT
            pnl = (pos['entry_price'] - current_price) * pos['quantity']

        # Return initial cost + PnL
        cost = (pos['quantity'] * pos['entry_price']) / pos['leverage']
        self.balance += cost + pnl

        trade = {
            'symbol': symbol,
            'side': 'CLOSE_' + pos['side'],
            'quantity': pos['quantity'],
            'price': current_price,
            'pnl': pnl,
            'type': 'CLOSE',
            'timestamp': datetime.now().isoformat()
        }
        self.trade_history.append(trade)

        del self.positions[symbol]

        return {'success': True, 'pnl': pnl, 'trade': trade}

    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get recent trade history"""
        return self.trade_history[-limit:]

    def get_total_pnl(self) -> float:
        """Calculate total PnL including open positions"""
        total_pnl = self.balance - self.initial_balance

        # Add unrealized PnL from open positions
        for symbol, pos in self.positions.items():
            current_price = self.prices.get(symbol, pos['entry_price'])
            if pos['side'] == 'LONG':
                pnl = (current_price - pos['entry_price']) * pos['quantity']
            else:
                pnl = (pos['entry_price'] - current_price) * pos['quantity']
            total_pnl += pnl

        return total_pnl

    def reset(self):
        """Reset account to initial state"""
        self.balance = self.initial_balance
        self.positions = {}
        self.trade_history = []
        self.prices = {}
