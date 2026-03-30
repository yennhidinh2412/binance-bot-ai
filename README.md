# 🤖 Binance Futures Trading Bot - AI Powered

Bot AI trading futures Binance chuyên nghiệp với độ chính xác cao, tập trung phân tích kỹ thuật, quản lý rủi ro thông minh và chiến lược long/short tự động.

## 🌟 Tính năng chính

### 📊 Phân tích kỹ thuật cao cấp
- **Phân tích nến (Candlestick Analysis)**: Nhận diện 15+ mô hình nến chuyên nghiệp
- **Chỉ báo kỹ thuật**: RSI, MACD, Bollinger Bands, EMA, SMA, Stochastic, Williams %R, ADX, CCI, MFI, ATR
- **Phát hiện xu hướng**: Xác định xu hướng đa timeframe với độ chính xác cao
- **Support/Resistance**: Tự động xác định các mức hỗ trợ và kháng cự quan trọng

### 🧠 AI Engine thông minh
- **Machine Learning Models**: Gradient Boosting, Random Forest cho dự đoán giá
- **Feature Engineering**: 40+ features từ dữ liệu thị trường
- **Confidence Scoring**: Hệ thống đánh giá độ tin cậy của tín hiệu
- **Auto Retraining**: Tự động huấn luyện lại model để duy trì hiệu suất

### ⚡ Chiến lược trading tự động
- **Long/Short positions**: Hỗ trợ cả hai hướng giao dịch
- **Multiple timeframes**: Phân tích đa khung thời gian (1m, 5m, 15m, 1h, 4h, 1d)
- **Smart Entry/Exit**: Tín hiệu vào/ra lệnh thông minh dựa trên AI
- **Position Sizing**: Tính toán kích thước vị thế tối ưu

### 🛡️ Quản lý rủi ro toàn diện
- **Stop Loss thông minh**: Dựa trên ATR, Support/Resistance
- **Take Profit đa cấp**: 3 mức chốt lời để tối ưu hóa lợi nhuận
- **Trailing Stop**: Tự động điều chỉnh stop loss theo xu hướng
- **Risk Limits**: Giới hạn rủi ro theo ngày, drawdown, vị thế

### 📈 Theo dõi hiệu suất
- **Real-time Monitoring**: Theo dõi PnL, win rate, risk metrics
- **Performance Analytics**: Sharpe ratio, max drawdown, profit factor
- **Trade History**: Lịch sử giao dịch chi tiết với phân tích

## 🚀 Cài đặt và sử dụng

### Yêu cầu hệ thống
- Python 3.9+
- macOS/Linux (khuyến nghị)
- 4GB RAM tối thiểu
- Kết nối internet ổn định

### Cài đặt dependencies

```bash
# Clone project
cd "/Users/vuthanhtrung/Documents/Bot AI"

# Activate virtual environment
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt

# Install TA-Lib (if not already installed)
brew install ta-lib
pip install TA-Lib
```

### Cấu hình

1. **API Keys**: Đã được cấu hình trong `config.py`
   - API Key: `d18mxjZan7k7OW28oZccILaWc4kjo62HA65PVYwBIxbMrkF3BLQXGM0p1mZsKXoW`
   - Secret Key: `hf9rNEpNanue6EPoRU6wB6GQfBjTASiPCtojAF71hUOSmqDdledNjAaUxcuBlSFM`
   - Trusted IPs: `34.2.147.137` (Google Cloud VM), `115.79.215.63` (MacBook)

2. **Risk Management**: Điều chỉnh trong `config.py`
   - Max position size: 2% của tài khoản
   - Stop loss: 1.5%
   - Take profit: 3.0%
   - Max daily loss: 5%

3. **Trading Settings**:
   - Default leverage: 10x
   - Symbols: BTC, ETH, ADA, SOL
   - Timeframes: 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d

### Chạy bot

```bash
# Run main trading bot
python main.py
```

### Chế độ testing (Paper Trading)

Để test bot mà không rủi ro:

```python
# Trong config.py, thay đổi:
TRADING_CONFIG = {
    "testnet": True,  # Enable paper trading
    # ... other settings
}
```

## 📁 Cấu trúc project

```
Bot AI/
├── main.py                 # Main trading bot
├── config.py              # Cấu hình và settings
├── binance_client.py      # Binance API client
├── technical_analysis.py  # Engine phân tích kỹ thuật
├── ai_engine.py           # AI trading engine
├── risk_management.py     # Hệ thống quản lý rủi ro
├── utils.py               # Utility functions
├── requirements.txt       # Python dependencies
├── logs/                  # Log files
├── models/                # Saved AI models
└── .github/
    └── copilot-instructions.md
```

## 🎯 Chiến lược trading

### Entry Signals
- **AI Confidence > 75%**: Tín hiệu từ AI model
- **Technical Confirmation**: RSI, MACD, Bollinger Bands alignment
- **Candlestick Patterns**: Hammer, Doji, Engulfing, etc.
- **Trend Alignment**: Tín hiệu phải phù hợp với xu hướng chính

### Exit Strategy
- **Take Profit**: 3 mức (50%, 100%, 150% risk-reward)
- **Stop Loss**: Smart stop dựa trên ATR và S/R levels
- **Trailing Stop**: 1% trailing stop để bảo vệ lợi nhuận
- **Opposite Signal**: Đóng vị thế khi có tín hiệu ngược lại

### Risk Management
- **Position Sizing**: Kelly Criterion + Fixed Fractional
- **Maximum Risk**: 2% mỗi trade, 5% mỗi ngày
- **Diversification**: Tối đa 5 vị thế cùng lúc
- **Drawdown Protection**: Dừng trading khi drawdown > 10%

## 📊 Metrics và Performance

Bot tracking các metrics sau:

- **Win Rate**: Tỷ lệ thắng/thua
- **Profit Factor**: Tỷ lệ lợi nhuận/thua lỗ
- **Sharpe Ratio**: Risk-adjusted returns
- **Maximum Drawdown**: Drawdown tối đa
- **Average RR**: Risk-Reward ratio trung bình

## ⚙️ Tối ưu hóa

### AI Model Tuning
```python
# Điều chỉnh confidence threshold
AI_CONFIG = {
    "confidence_threshold": 0.75,  # Tăng để trade ít hơn nhưng chính xác hơn
    "lookback_periods": 200,       # Tăng để model học nhiều data hơn
}
```

### Risk Parameters
```python
RISK_MANAGEMENT = {
    "max_position_size_percent": 1.0,  # Giảm xuống 1% để bảo thủ hơn
    "stop_loss_percent": 1.0,          # Stop loss chặt hơn
    "take_profit_percent": 2.0,        # Target lợi nhuận thấp hơn
}
```

## 🔧 Troubleshooting

### Lỗi thường gặp

1. **API Connection Error**
   ```bash
   # Kiểm tra API keys và IP whitelist
   # Đảm bảo IP được thêm vào Binance
   ```

2. **Insufficient Balance**
   ```bash
   # Kiểm tra số dư USDT trong Futures wallet
   # Transfer từ Spot sang Futures nếu cần
   ```

3. **Model Not Found**
   ```bash
   # Bot sẽ tự train model lần đầu chạy
   # Hoặc chạy retrain_models() manually
   ```

### Logs và Monitoring

```bash
# Xem logs real-time
tail -f logs/trading_bot.log

# Kiểm tra performance
grep "Performance Update" logs/trading_bot.log
```

## 🚨 Cảnh báo bảo mật

- **Không share API keys** với bất kỳ ai
- **Sử dụng IP whitelist** cho bảo mật tối đa
- **Bắt đầu với số tiền nhỏ** để test
- **Monitor bot thường xuyên** trong những ngày đầu

## 📞 Hỗ trợ

Nếu gặp vấn đề:

1. Kiểm tra logs trong thư mục `logs/`
2. Verify API keys và permissions
3. Đảm bảo đủ balance trong Futures wallet
4. Test với paper trading trước

## ⚡ Performance Tips

1. **Chạy trên VPS** để đảm bảo uptime 24/7
2. **Monitor latency** - đặt bot gần server Binance
3. **Regular retraining** - retrain models hàng tuần
4. **Backup settings** - lưu config và models định kỳ

---

**⚠️ Disclaimer**: Trading futures có rủi ro cao. Bot này chỉ là công cụ hỗ trợ, không đảm bảo lợi nhuận. Luôn trade với số tiền bạn có thể chấp nhận mất.
