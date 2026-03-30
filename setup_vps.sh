#!/bin/bash
# ============================================
# Bot AI Trading - VPS Setup (NO Docker)
# ============================================
# Nhẹ hơn Docker ~200MB RAM, phù hợp VM 1GB
#
# Chạy:
#   chmod +x setup_vps.sh && ./setup_vps.sh
# ============================================

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================"
echo "🚀 Bot AI Trading - VPS Setup (Lite)"
echo "========================================"

# 1. Update system
echo ""
echo "📦 [1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# 2. Install Python 3.12 + pip
echo ""
echo "🐍 [2/6] Installing Python..."
sudo apt install -y python3 python3-pip python3-venv curl

PYTHON_VERSION=$(python3 --version 2>&1)
echo "✅ $PYTHON_VERSION"

# 3. Create virtual environment & install dependencies
echo ""
echo "📚 [3/6] Installing Python packages..."
if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
"$APP_DIR/.venv/bin/pip" install gunicorn
echo "✅ Dependencies installed"

# 4. Add swap (important for 1GB RAM VMs)
echo ""
echo "💾 [4/6] Setting up swap..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✅ 2GB swap created"
else
    echo "✅ Swap already exists"
fi

# 5. Open port 8080 (Oracle Cloud iptables)
echo ""
echo "🔓 [5/6] Opening port 8080..."
if ! sudo iptables -C INPUT -m state --state NEW -p tcp --dport 8080 -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT
fi
if command -v netfilter-persistent &> /dev/null; then
    sudo netfilter-persistent save
else
    sudo DEBIAN_FRONTEND=noninteractive apt install -y iptables-persistent
    sudo netfilter-persistent save
fi
echo "✅ Port 8080 opened"

# 6. Create systemd service (auto-start on boot + auto-restart on crash)
echo ""
echo "⚙️  [6/6] Creating systemd service..."

sudo tee /etc/systemd/system/bot-ai.service > /dev/null << EOF
[Unit]
Description=Bot AI Trading Dashboard
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/gunicorn \\
    --bind 0.0.0.0:8080 \\
    --workers 1 \\
    --timeout 120 \\
    --keep-alive 5 \\
    --access-logfile - \\
    --error-logfile - \\
    web_dashboard:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bot-ai
echo "✅ Systemd service created (auto-start on boot)"

# Setup .env
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "⚠️  Edit .env with your API keys: nano .env"
fi

# Show public IP
PUBLIC_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo 'YOUR_IP')

echo ""
echo "========================================"
echo "✅ Setup complete!"
echo "========================================"
echo ""
echo "Các lệnh quản lý bot:"
echo "  nano .env                          ← Điền API keys"
echo "  sudo systemctl start bot-ai        ← Chạy bot"
echo "  sudo systemctl stop bot-ai         ← Dừng bot"
echo "  sudo systemctl restart bot-ai      ← Restart bot"
echo "  sudo systemctl status bot-ai       ← Xem trạng thái"
echo "  journalctl -u bot-ai -f            ← Xem logs realtime"
echo ""
echo "Dashboard: http://$PUBLIC_IP:8080"
echo ""
