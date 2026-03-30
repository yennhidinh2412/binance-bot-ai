"""
Test Binance Testnet Connection
"""
from binance_client import BinanceFuturesClient
from config import Config

print("="*70)
print("🧪 TESTING BINANCE TESTNET CONNECTION")
print("="*70)

# Initialize client
print("\n📡 Connecting to Binance Testnet...")
client = BinanceFuturesClient()

print(f"\n✅ Client initialized!")
print(f"   Testnet: {client.config['trading']['testnet']}")
print(f"   Demo Mode: {client.is_demo_mode}")

# Test API connection
try:
    print("\n📊 Fetching account info...")
    account = client.get_account_info()
    
    print("\n💰 TESTNET ACCOUNT INFO:")
    print(f"   Total Balance: ${float(account['totalWalletBalance']):.2f} USDT")
    print(f"   Available: ${float(account['availableBalance']):.2f} USDT")
    print(f"   Unrealized PnL: ${float(account['totalUnrealizedProfit']):.2f} USDT")
    
    # Test getting positions
    print("\n📈 Fetching open positions...")
    positions = client.get_open_positions()
    print(f"   Open Positions: {len(positions)}")
    
    if positions:
        for pos in positions:
            print(f"\n   {pos['symbol']}:")
            print(f"      Side: {pos['side']}")
            print(f"      Size: {pos['quantity']}")
            print(f"      Entry: ${pos['entry_price']:.2f}")
            print(f"      PnL: ${pos['pnl']:.2f} ({pos['pnl_percent']:.2f}%)")
    
    # Test getting market data
    print("\n📊 Fetching BTC price...")
    klines = client.get_klines('BTCUSDT', '5m', limit=1)
    if klines and len(klines) > 0:
        latest = klines[0]  # List of lists
        close_price = float(latest[4])  # Index 4 is close price
        print(f"   BTCUSDT: ${close_price:.2f}")
    
    print("\n" + "="*70)
    print("✅ TESTNET CONNECTION SUCCESSFUL!")
    print("🚀 Bot ready to trade on Binance Testnet!")
    print("="*70)
    
except Exception as e:
    print("\n" + "="*70)
    print("❌ CONNECTION FAILED!")
    print(f"Error: {e}")
    print("="*70)
    print("\nPlease check:")
    print("1. API Key and Secret Key are correct")
    print("2. API keys have 'Enable Futures' permission")
    print("3. IP whitelist is configured (if required)")
    print("="*70)
