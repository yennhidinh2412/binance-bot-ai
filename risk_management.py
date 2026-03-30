"""
Advanced Risk Management System
Hệ thống quản lý rủi ro chuyên nghiệp cho futures trading
"""

import math
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from loguru import logger
from config import Config

class RiskManager:
    """Hệ thống quản lý rủi ro toàn diện"""
    
    def __init__(self, binance_client):
        self.client = binance_client
        self.config = Config.get_config()
        self.risk_config = self.config["risk_management"]
        
        # Set risk per trade from config
        self.risk_per_trade = self.risk_config["max_position_size_percent"] / 100  # Convert to decimal
        
        # Risk tracking
        self.daily_pnl = 0.0
        self.total_positions = 0
        self.max_daily_loss_reached = False
        self.consecutive_losses = 0
        self.max_consecutive_losses = 5
        
        # Position tracking
        self.open_positions = {}
        self.position_history = []
        
        logger.info("Risk Manager initialized")
    
    def calculate_position_size(self, account_balance: float, entry_price: float, 
                              stop_loss_price: float, symbol: str, risk_percentage: float = None) -> Dict[str, float]:
        """Tính toán kích thước vị thế dựa trên risk management"""
        try:
            # Get symbol info để xác định precision
            symbol_info = self.client.get_symbol_info(symbol)
            quantity_precision = self._get_quantity_precision(symbol_info)
            
            # Risk per trade (% of account)
            # Lấy risk percentage từ parameter hoặc config
            risk_percent = risk_percentage if risk_percentage is not None else self.risk_per_trade
            risk_amount = account_balance * risk_percent
            
            # Calculate risk per unit
            if stop_loss_price == 0:
                # Default stop loss if not provided
                stop_loss_price = entry_price * (1 - self.risk_config["stop_loss_percent"] / 100)
            
            risk_per_unit = abs(entry_price - stop_loss_price)
            
            if risk_per_unit <= 0:
                logger.warning("Invalid risk calculation - using minimum position size")
                quantity = self._get_min_quantity(symbol_info)
            else:
                # Calculate quantity
                quantity = risk_amount / risk_per_unit
                
                # Apply position size limits
                max_position_value = account_balance * 0.1  # Max 10% of account per position
                max_quantity_by_value = max_position_value / entry_price
                quantity = min(quantity, max_quantity_by_value)
                
                # Round to symbol precision
                quantity = self._round_to_precision(quantity, quantity_precision)
                
                # Ensure minimum quantity
                min_quantity = self._get_min_quantity(symbol_info)
                quantity = max(quantity, min_quantity)
            
            # Calculate metrics
            position_value = quantity * entry_price
            risk_amount_actual = quantity * risk_per_unit
            risk_percent_actual = (risk_amount_actual / account_balance) * 100
            
            position_size_info = {
                'quantity': quantity,
                'position_value': position_value,
                'risk_amount': risk_amount_actual,
                'risk_percent': risk_percent_actual,
                'entry_price': entry_price,
                'stop_loss_price': stop_loss_price,
                'risk_reward_ratio': self._calculate_risk_reward_ratio(
                    entry_price, stop_loss_price, self.risk_config["take_profit_percent"]
                )
            }
            
            logger.debug(f"Position size calculated: {quantity} units (Risk: {risk_percent_actual:.2f}%)")
            return position_size_info
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            raise
    
    def validate_trade(
        self,
        signal: str,
        symbol: str,
        quantity: float,
        current_price: float,
        ai_confidence: float
    ) -> Dict[str, Any]:
        """Validate trade trước khi execute"""
        try:
            validation_result = {
                'is_valid': True,
                'reasons': [],
                'warnings': [],
                'risk_score': 0.0
            }
            
            # Check daily loss limit
            if self.max_daily_loss_reached:
                validation_result['is_valid'] = False
                validation_result['reasons'].append("Daily loss limit reached")
            
            # Check maximum positions
            if len(self.open_positions) >= self.risk_config.get("max_open_positions", 5):
                validation_result['is_valid'] = False
                validation_result['reasons'].append("Maximum open positions reached")
            
            # Check consecutive losses
            if self.consecutive_losses >= self.max_consecutive_losses:
                validation_result['is_valid'] = False
                validation_result['reasons'].append("Maximum consecutive losses reached")
            
            # Check AI confidence
            min_confidence = self.config["ai_config"]["confidence_threshold"]
            if ai_confidence < min_confidence:
                validation_result['is_valid'] = False
                validation_result['reasons'].append(f"AI confidence too low: {ai_confidence:.3f} < {min_confidence}")
            
            # Check if opposite position exists
            if symbol in self.open_positions:
                existing_side = self.open_positions[symbol]['side']
                new_side = 'BUY' if signal == 'BUY' else 'SELL'
                
                if existing_side != new_side:
                    validation_result['warnings'].append("Opposite position exists - will close existing first")
            
            # Calculate risk score
            risk_factors = [
                self.daily_pnl < 0,  # Negative daily PnL
                self.consecutive_losses > 2,  # Multiple losses
                ai_confidence < 0.8,  # Low confidence
                len(self.open_positions) > 3  # Many open positions
            ]
            
            validation_result['risk_score'] = sum(risk_factors) / len(risk_factors)
            
            # Add warning for high risk
            if validation_result['risk_score'] > 0.5:
                validation_result['warnings'].append(f"High risk score: {validation_result['risk_score']:.2f}")
            
            logger.debug(f"Trade validation: {'VALID' if validation_result['is_valid'] else 'INVALID'}")
            return validation_result
        except Exception as e:
            logger.error(f"Error validating trade: {e}")
            return {'is_valid': False, 'reasons': [f"Validation error: {e}"], 'warnings': [], 'risk_score': 1.0}
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        side: str,
        atr: float = None,
        support_resistance: Dict[str, List[float]] = None
    ) -> float:
        """Tính toán stop loss thông minh"""
        try:
            stop_loss_percent = self.risk_config["stop_loss_percent"] / 100
            
            if side.upper() == 'BUY':
                # For long positions
                basic_stop = entry_price * (1 - stop_loss_percent)
                
                # ATR-based stop loss
                if atr:
                    atr_stop = entry_price - (atr * 2)
                    basic_stop = max(basic_stop, atr_stop)  # Use the closer stop
                
                # Support level based stop loss
                if support_resistance and 'support' in support_resistance:
                    nearest_support = self._find_nearest_level(
                        entry_price, support_resistance['support'], 'below'
                    )
                    if nearest_support:
                        support_stop = nearest_support * 0.99  # Slight buffer below support
                        basic_stop = max(basic_stop, support_stop)
            
            else:  # SELL
                # For short positions
                basic_stop = entry_price * (1 + stop_loss_percent)
                
                # ATR-based stop loss
                if atr:
                    atr_stop = entry_price + (atr * 2)
                    basic_stop = min(basic_stop, atr_stop)  # Use the closer stop
                
                # Resistance level based stop loss
                if support_resistance and 'resistance' in support_resistance:
                    nearest_resistance = self._find_nearest_level(
                        entry_price, support_resistance['resistance'], 'above'
                    )
                    if nearest_resistance:
                        resistance_stop = nearest_resistance * 1.01  # Slight buffer above resistance
                        basic_stop = min(basic_stop, resistance_stop)
            
            logger.debug(f"Stop loss calculated: {basic_stop} for {side} at {entry_price}")
            return basic_stop
        except Exception as e:
            logger.error(f"Error calculating stop loss: {e}")
            return entry_price * (0.98 if side.upper() == 'BUY' else 1.02)
    
    def calculate_take_profit(
        self,
        entry_price: float,
        stop_loss_price: float,
        side: str,
        risk_reward_ratio: float = None
    ) -> List[float]:
        """Tính toán multiple take profit levels"""
        try:
            if risk_reward_ratio is None:
                risk_reward_ratio = self.risk_config["take_profit_percent"] / self.risk_config["stop_loss_percent"]
            
            risk_amount = abs(entry_price - stop_loss_price)
            
            take_profit_levels = []
            
            if side.upper() == 'BUY':
                # Multiple TP levels for long
                tp1 = entry_price + (risk_amount * risk_reward_ratio * 0.5)  # 50% of target
                tp2 = entry_price + (risk_amount * risk_reward_ratio)        # 100% of target
                tp3 = entry_price + (risk_amount * risk_reward_ratio * 1.5)  # 150% of target
                take_profit_levels = [tp1, tp2, tp3]
            else:
                # Multiple TP levels for short
                tp1 = entry_price - (risk_amount * risk_reward_ratio * 0.5)
                tp2 = entry_price - (risk_amount * risk_reward_ratio)
                tp3 = entry_price - (risk_amount * risk_reward_ratio * 1.5)
                take_profit_levels = [tp1, tp2, tp3]
            
            logger.debug(f"Take profit levels: {take_profit_levels}")
            return take_profit_levels
        except Exception as e:
            logger.error(f"Error calculating take profit: {e}")
            return []
    
    def update_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        position_info: Dict[str, Any]
    ) -> Optional[float]:
        """Cập nhật trailing stop loss"""
        try:
            if symbol not in self.open_positions:
                return None
            
            position = self.open_positions[symbol]
            side = position['side']
            entry_price = position['entry_price']
            current_stop = position.get('stop_loss_price', 0)
            
            trailing_percent = self.risk_config["trailing_stop_percent"] / 100
            
            new_stop = None
            
            if side == 'BUY':
                # For long positions, move stop up
                if current_price > entry_price:
                    potential_stop = current_price * (1 - trailing_percent)
                    if potential_stop > current_stop:
                        new_stop = potential_stop
            else:
                # For short positions, move stop down
                if current_price < entry_price:
                    potential_stop = current_price * (1 + trailing_percent)
                    if potential_stop < current_stop or current_stop == 0:
                        new_stop = potential_stop
            
            if new_stop:
                self.open_positions[symbol]['stop_loss_price'] = new_stop
                logger.debug(f"Trailing stop updated for {symbol}: {new_stop}")
            
            return new_stop
        except Exception as e:
            logger.error(f"Error updating trailing stop: {e}")
            return None
    
    def check_drawdown(self, account_balance: float, peak_balance: float) -> Dict[str, Any]:
        """Kiểm tra drawdown và risk limits"""
        try:
            current_drawdown = (peak_balance - account_balance) / peak_balance * 100 if peak_balance > 0 else 0
            max_drawdown = self.risk_config["max_drawdown_percent"]
            
            drawdown_info = {
                'current_drawdown': current_drawdown,
                'max_drawdown': max_drawdown,
                'is_critical': current_drawdown > max_drawdown,
                'action_required': False
            }
            
            if current_drawdown > max_drawdown * 0.8:  # 80% of max drawdown
                drawdown_info['action_required'] = True
                drawdown_info['action'] = 'reduce_position_sizes'
            
            if current_drawdown > max_drawdown:
                drawdown_info['action_required'] = True
                drawdown_info['action'] = 'stop_trading'
                self.max_daily_loss_reached = True
            
            logger.debug(f"Drawdown check: {current_drawdown:.2f}% (Max: {max_drawdown}%)")
            return drawdown_info
        except Exception as e:
            logger.error(f"Error checking drawdown: {e}")
            return {'current_drawdown': 0, 'max_drawdown': max_drawdown, 'is_critical': False, 'action_required': False}
    
    def update_position_tracking(self, symbol: str, position_data: Dict[str, Any]):
        """Cập nhật tracking positions"""
        try:
            self.open_positions[symbol] = position_data
            logger.debug(f"Position tracking updated for {symbol}")
        except Exception as e:
            logger.error(f"Error updating position tracking: {e}")
    
    def close_position_tracking(self, symbol: str, pnl: float):
        """Đóng position tracking và cập nhật statistics"""
        try:
            if symbol in self.open_positions:
                position = self.open_positions.pop(symbol)
                
                # Update PnL tracking
                self.daily_pnl += pnl
                
                # Track consecutive losses
                if pnl < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
                
                # Add to history
                position['close_pnl'] = pnl
                position['close_time'] = pd.Timestamp.now()
                self.position_history.append(position)
                
                logger.info(f"Position closed: {symbol}, PnL: {pnl:.4f}")
            
        except Exception as e:
            logger.error(f"Error closing position tracking: {e}")
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """Lấy risk metrics tổng quan"""
        try:
            total_positions = len(self.position_history)
            winning_positions = sum(1 for pos in self.position_history if pos.get('close_pnl', 0) > 0)
            
            metrics = {
                'daily_pnl': self.daily_pnl,
                'open_positions': len(self.open_positions),
                'total_positions_today': total_positions,
                'win_rate': (winning_positions / total_positions * 100) if total_positions > 0 else 0,
                'consecutive_losses': self.consecutive_losses,
                'max_daily_loss_reached': self.max_daily_loss_reached,
                'risk_score': self._calculate_overall_risk_score()
            }
            
            return metrics
        except Exception as e:
            logger.error(f"Error getting risk metrics: {e}")
            return {}
    
    def _calculate_overall_risk_score(self) -> float:
        """Tính toán risk score tổng thể"""
        try:
            risk_factors = []
            
            # Daily PnL factor
            if self.daily_pnl < 0:
                risk_factors.append(min(abs(self.daily_pnl) / 1000, 1.0))  # Normalize to account size
            
            # Open positions factor
            risk_factors.append(len(self.open_positions) / 10)  # Normalize to max positions
            
            # Consecutive losses factor
            risk_factors.append(self.consecutive_losses / self.max_consecutive_losses)
            
            return sum(risk_factors) / len(risk_factors) if risk_factors else 0.0
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 0.5
    
    def _get_quantity_precision(self, symbol_info: Dict[str, Any]) -> int:
        """Lấy precision cho quantity"""
        try:
            for filter_info in symbol_info.get('filters', []):
                if filter_info['filterType'] == 'LOT_SIZE':
                    step_size = float(filter_info['stepSize'])
                    return len(str(step_size).split('.')[-1].rstrip('0'))
            return 3  # Default precision
        except Exception:
            return 3
    
    def _get_min_quantity(self, symbol_info: Dict[str, Any]) -> float:
        """Lấy minimum quantity"""
        try:
            for filter_info in symbol_info.get('filters', []):
                if filter_info['filterType'] == 'LOT_SIZE':
                    return float(filter_info['minQty'])
            return 0.001  # Default minimum
        except Exception:
            return 0.001
    
    def _round_to_precision(self, value: float, precision: int) -> float:
        """Round value theo precision"""
        return round(value, precision)
    
    def _calculate_risk_reward_ratio(self, entry_price: float, stop_loss: float, take_profit_percent: float) -> float:
        """Tính toán risk reward ratio"""
        try:
            risk = abs(entry_price - stop_loss)
            reward = entry_price * (take_profit_percent / 100)
            return reward / risk if risk > 0 else 1.0
        except Exception:
            return 1.0
    
    def _find_nearest_level(self, price: float, levels: List[float], direction: str) -> Optional[float]:
        """Tìm support/resistance level gần nhất"""
        try:
            if direction == 'below':
                below_levels = [level for level in levels if level < price]
                return max(below_levels) if below_levels else None
            else:  # above
                above_levels = [level for level in levels if level > price]
                return min(above_levels) if above_levels else None
        except Exception:
            return None
