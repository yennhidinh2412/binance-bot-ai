"""
Binance Futures API Client
Quản lý kết nối và giao dịch với Binance Futures
"""

import asyncio
import hmac
import hashlib
import time
import json
from typing import Dict, List, Optional, Any
from binance.client import Client
from binance.exceptions import BinanceAPIException
from binance import AsyncClient, BinanceSocketManager
import aiohttp
import websockets
from loguru import logger
from config import Config
from demo_trading import DemoTradingAccount

class BinanceFuturesClient:
    """Client chuyên nghiệp cho Binance Futures API"""
    
    def __init__(self):
        self.config = Config.get_config()
        self.api_key = self.config["api_keys"]["binance_api_key"]
        self.secret_key = self.config["api_keys"]["binance_secret_key"]
        
        # Check if demo mode
        self.is_demo_mode = self.config["trading"].get("demo_mode", False)
        
        if self.is_demo_mode:
            demo_balance = self.config["trading"].get("demo_balance", 10000)
            self.demo_account = DemoTradingAccount(demo_balance)
            logger.warning(f"🎮 DEMO MODE: Using virtual balance {demo_balance} USDT")
        else:
            self.demo_account = None
        
        # ping=False → KHÔNG gọi API nào trong constructor
        # Mặc định Client() gọi ping() → gây ban IP nếu restart nhiều
        self.client = Client(
            api_key=self.api_key,
            api_secret=self.secret_key,
            testnet=self.config["trading"]["testnet"],
            requests_params={'timeout': 10},
            ping=False,
        )

        # Time sync: 1 API call nhẹ duy nhất (weight=1)
        import time as time_module
        import requests as _requests
        self.time_offset = -1500  # safe default
        base_url = (
            "https://testnet.binancefuture.com"
            if self.config["trading"]["testnet"]
            else "https://fapi.binance.com"
        )
        try:
            resp = _requests.get(
                f"{base_url}/fapi/v1/time", timeout=5
            )
            data = resp.json()
            if 'serverTime' in data:
                local_time = int(time_module.time() * 1000)
                self.time_offset = data['serverTime'] - local_time
                logger.info(
                    f"Time sync OK: offset={self.time_offset}ms"
                )
            elif data.get('code') == -1003:
                msg = data.get('msg', 'IP banned')
                logger.warning(f"Time sync: IP banned - {msg}")
                raise Exception(msg)
            else:
                logger.warning(f"Time sync skipped: {data}")
        except _requests.exceptions.RequestException as e:
            logger.warning(
                f"Time sync network error (using default): {e}"
            )
        self.client.timestamp_offset = self.time_offset
        
        # Async client for real-time operations
        self.async_client = None
        self.socket_manager = None
        
        # Connection status
        self.is_connected = False
        self.last_ping = None
        
        logger.info("Binance Futures Client initialized")
    
    async def initialize_async_client(self):
        """Khởi tạo async client"""
        try:
            self.async_client = await AsyncClient.create(
                api_key=self.api_key,
                api_secret=self.secret_key,
                testnet=self.config["trading"]["testnet"]
            )
            self.socket_manager = BinanceSocketManager(self.async_client)
            self.is_connected = True
            logger.info("Async client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize async client: {e}")
            raise
    
    async def close_connections(self):
        """Đóng các kết nối"""
        try:
            if self.socket_manager:
                try:
                    await self.socket_manager.close()
                except AttributeError:
                    # BinanceSocketManager may not have close method
                    logger.debug("Socket manager close not available")
            if self.async_client:
                await self.async_client.close_connection()
            logger.info("Connections closed")
        except Exception as e:
            logger.warning(f"Error closing connections: {e}")
    
    def _sync_timestamp(self):
        """Sync timestamp offset with Binance server"""
        # Timestamp offset already set during initialization
        # Just ensure it's still applied
        pass
    
    def get_account_info(self) -> Dict[str, Any]:
        """Lấy thông tin tài khoản"""
        try:
            if self.is_demo_mode:
                logger.debug("Getting demo account info")
                return self.demo_account.get_account_info()
            
            self._sync_timestamp()
            account_info = self.client.futures_account(recvWindow=60000)
            logger.info("Account info retrieved successfully")
            return account_info
        except BinanceAPIException as e:
            logger.error(f"Error getting account info: {e}")
            raise
    
    def get_24hr_ticker(self, symbol: str) -> Dict[str, Any]:
        """Lấy thống kê 24h của symbol"""
        try:
            ticker = self.client.get_24hr_ticker(symbol=symbol)
            logger.debug(f"24h ticker retrieved for {symbol}")
            return ticker
        except Exception as e:
            logger.error(f"Error getting 24h ticker for {symbol}: {e}")
            raise

    def get_balance(self) -> Dict[str, Any]:
        """Lấy số dư tài khoản"""
        try:
            account = self.get_account_info()
            balance = {}
            
            for asset in account['assets']:
                if float(asset['walletBalance']) > 0:
                    balance[asset['asset']] = {
                        'wallet_balance': float(asset['walletBalance']),
                        'unrealized_pnl': float(asset['unrealizedProfit']),
                        'margin_balance': float(asset['marginBalance'])
                    }
            
            return balance
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            raise
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Lấy danh sách positions đang mở"""
        try:
            if self.is_demo_mode:
                logger.debug("Getting demo positions")
                return self.demo_account.get_open_positions()
            
            self._sync_timestamp()
            positions = self.client.futures_position_information(recvWindow=60000)
            open_positions = [
                pos for pos in positions 
                if float(pos['positionAmt']) != 0
            ]
            
            logger.info(f"Found {len(open_positions)} open positions")
            return open_positions
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            if self.is_demo_mode:
                return []
            raise
    
    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> List[List]:
        """Lấy dữ liệu nến"""
        try:
            self._sync_timestamp()
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            logger.debug(f"Retrieved {len(klines)} klines for {symbol} {interval}")
            return klines
        except Exception as e:
            logger.error(f"Error getting klines: {e}")
            raise
    
    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = 'GTC'
    ) -> Dict[str, Any]:
        """Đặt lệnh futures"""
        # Safety check: should not reach here in demo mode
        if self.is_demo_mode:
            logger.warning(f"DEMO MODE: Attempted to call place_order directly - using simulation")
            order_id = self.demo_account.order_id_counter
            self.demo_account.order_id_counter += 1
            return {
                'orderId': order_id,
                'symbol': symbol,
                'status': 'FILLED' if order_type == 'MARKET' else 'NEW',
                'type': order_type,
                'side': side,
                'avgPrice': str(self.demo_account.get_simulated_price(symbol)) if order_type == 'MARKET' else None,
                'price': str(price) if price else None,
                'stopPrice': str(stop_price) if stop_price else None,
                'origQty': str(quantity)
            }
        
        try:
            self._sync_timestamp()
            order_params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity,
                'recvWindow': 60000
            }
            
            # Only add timeInForce for LIMIT orders, not MARKET
            if order_type != 'MARKET' and time_in_force:
                order_params['timeInForce'] = time_in_force
            
            if price:
                order_params['price'] = price
            if stop_price:
                order_params['stopPrice'] = stop_price
            
            order = self.client.futures_create_order(**order_params)
            logger.info(f"Order placed successfully: {order['orderId']}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Error placing order: {e}")
            raise
    
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float
    ) -> Dict[str, Any]:
        """Đặt lệnh market"""
        if self.is_demo_mode:
            # Use simulated price from demo account (no API call needed)
            current_price = self.demo_account.get_simulated_price(symbol)
            return self.demo_account.place_market_order(
                symbol, side, quantity, current_price
            )
        
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type='MARKET',
            quantity=quantity
        )
    
    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Dict[str, Any]:
        """Đặt lệnh limit"""
        if self.is_demo_mode:
            # Demo mode: simulate limit order
            order_id = self.demo_account.order_id_counter
            self.demo_account.order_id_counter += 1
            logger.info(f"DEMO LIMIT ORDER: {side} {quantity} {symbol} @ {price}")
            return {
                'orderId': order_id,
                'symbol': symbol,
                'status': 'NEW',
                'type': 'LIMIT',
                'side': side,
                'price': str(price),
                'origQty': str(quantity)
            }
            
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type='LIMIT',
            quantity=quantity,
            price=price
        )
    
    def place_stop_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float
    ) -> Dict[str, Any]:
        """Đặt lệnh stop market"""
        if self.is_demo_mode:
            # Demo mode: simulate stop loss order
            order_id = self.demo_account.order_id_counter
            self.demo_account.order_id_counter += 1
            logger.info(f"DEMO STOP LOSS: {side} {quantity} {symbol} @ {stop_price}")
            return {
                'orderId': order_id,
                'symbol': symbol,
                'status': 'NEW',
                'type': 'STOP_MARKET',
                'side': side,
                'stopPrice': str(stop_price),
                'origQty': str(quantity)
            }
            
        return self.place_order(
            symbol=symbol,
            side=side,
            order_type='STOP_MARKET',
            quantity=quantity,
            stop_price=stop_price
        )
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Hủy lệnh"""
        if self.is_demo_mode:
            logger.info(f"DEMO: Order {order_id} cancelled for {symbol}")
            return {'orderId': order_id, 'status': 'CANCELED'}
            
        try:
            result = self.client.futures_cancel_order(
                symbol=symbol,
                orderId=order_id
            )
            logger.info(f"Order {order_id} cancelled successfully")
            return result
        except BinanceAPIException as e:
            logger.error(f"Error cancelling order: {e}")
            raise
    
    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Hủy tất cả lệnh của symbol"""
        if self.is_demo_mode:
            logger.info(f"DEMO: All orders cancelled for {symbol}")
            return {'symbol': symbol, 'status': 'success'}
            
        try:
            result = self.client.futures_cancel_all_open_orders(symbol=symbol)
            logger.info(f"All orders for {symbol} cancelled")
            return result
        except BinanceAPIException as e:
            logger.error(f"Error cancelling all orders: {e}")
            raise
    
    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Thiết lập đòn bẩy"""
        if self.is_demo_mode:
            logger.info(f"DEMO: Leverage set to {leverage}x for {symbol}")
            return {'leverage': leverage, 'symbol': symbol}
            
        try:
            result = self.client.futures_change_leverage(
                symbol=symbol,
                leverage=leverage
            )
            logger.info(f"Leverage set to {leverage}x for {symbol}")
            return result
        except BinanceAPIException as e:
            logger.error(f"Error setting leverage: {e}")
            raise
    
    def set_margin_type(self, symbol: str, margin_type: str) -> Dict[str, Any]:
        """Thiết lập loại margin (ISOLATED/CROSSED)"""
        if self.is_demo_mode:
            logger.info(f"DEMO: Margin type set to {margin_type} for {symbol}")
            return {'marginType': margin_type, 'symbol': symbol}
            
        try:
            result = self.client.futures_change_margin_type(
                symbol=symbol,
                marginType=margin_type
            )
            logger.info(f"Margin type set to {margin_type} for {symbol}")
            return result
        except BinanceAPIException as e:
            logger.error(f"Error setting margin type: {e}")
            raise
    
    async def start_kline_socket(self, symbol: str, interval: str, callback):
        """Bắt đầu WebSocket cho dữ liệu nến real-time"""
        if not self.socket_manager:
            await self.initialize_async_client()
        
        try:
            socket = self.socket_manager.kline_futures_socket(
                symbol=symbol,
                interval=interval
            )
            
            async with socket as stream:
                while True:
                    data = await stream.recv()
                    await callback(data)
        except Exception as e:
            logger.error(f"Error in kline socket: {e}")
            raise
    
    async def start_user_socket(self, callback):
        """Bắt đầu WebSocket cho dữ liệu user (orders, positions)"""
        if not self.socket_manager:
            await self.initialize_async_client()
        
        try:
            socket = self.socket_manager.futures_user_socket()
            
            async with socket as stream:
                while True:
                    data = await stream.recv()
                    await callback(data)
        except Exception as e:
            logger.error(f"Error in user socket: {e}")
            raise
    
    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Lấy thông tin chi tiết về symbol"""
        try:
            exchange_info = self.client.futures_exchange_info()
            
            for symbol_info in exchange_info['symbols']:
                if symbol_info['symbol'] == symbol:
                    return symbol_info
            
            raise ValueError(f"Symbol {symbol} not found")
        except Exception as e:
            logger.error(f"Error getting symbol info: {e}")
            raise
