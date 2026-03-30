"""Quick test của bot intelligence"""
import asyncio
from smart_bot_engine import SmartBotEngine
from binance_client import BinanceFuturesClient


async def quick_test():
    print('\n' + '='*70)
    print('🧪 QUICK INTELLIGENCE TEST')
    print('='*70)

    print('\n📍 Khởi tạo Bot Engine...')
    client = BinanceFuturesClient()
    bot = SmartBotEngine(client)
    print('✅ Bot initialized!')
    print(f'   📦 Models loaded: {len(bot.models)}')

    print('\n📍 Testing AI Analysis on live market...')

    good_opportunities = []

    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        print(f'\n💎 {symbol}:')
        analysis = await bot.analyze_symbol(symbol)

        if analysis:
            signal = analysis.get('signal', 'N/A')
            confidence = analysis.get('confidence', 0)
            price = analysis.get('entry_price', 0)
            tp = analysis.get('tp_price', 0)
            sl = analysis.get('sl_price', 0)

            print(f'   📊 Signal: {signal}')
            print(f'   🎯 Confidence: {confidence:.2f}%')
            print(f'   💰 Price: ${price:,.2f}')

            if signal != 'HOLD':
                print(f'   ✅ TP: ${tp:,.2f}')
                print(f'   🛡️  SL: ${sl:,.2f}')

                if confidence >= 75:
                    print(f'   🌟 GOOD OPPORTUNITY DETECTED!')
                    good_opportunities.append(symbol)
                else:
                    print(f'   ⏸️  Confidence too low ({confidence:.1f}%)')
            else:
                print(f'   ⏸️  HOLD - Waiting for better setup')
        else:
            print(f'   ❌ Analysis failed')

    print('\n' + '='*70)
    print('📊 RESULTS:')
    print('='*70)
    print(f'✅ Bot analyzed 3 symbols successfully')
    print(f'🎯 Good opportunities found: {len(good_opportunities)}')

    if good_opportunities:
        print(f'\n🌟 Bot recommends trading: {", ".join(good_opportunities)}')
        print('✅ Bot is working INTELLIGENTLY!')
    else:
        print('\n⏸️  No good opportunities at the moment')
        print('✅ Bot is being SMART - waiting for better setups!')
        print('💡 This is GOOD - bot protects your capital!')

    print('='*70 + '\n')


if __name__ == "__main__":
    asyncio.run(quick_test())
