# 🚀 HƯỚNG DẪN DEPLOY BOT AI TRADING (MIỄN PHÍ)

## Tổng quan

Bot AI sẽ chạy trên **Oracle Cloud Free Tier** — VPS miễn phí **vĩnh viễn**, đủ mạnh cho trading bot:

| Nhà cung cấp | Miễn phí | RAM | CPU | Phù hợp bot |
|---|---|---|---|---|
| **Oracle Cloud** ✅ | **Vĩnh viễn** | **1GB** (AMD) / **24GB** (ARM) | 1 / 4 | ✅ Tốt nhất |
| Google Cloud | Vĩnh viễn | 1GB | 0.25 vCPU | ⚠️ Quá yếu |
| AWS | 12 tháng rồi hết | 1GB | 1 | ⚠️ Phải trả sau |
| Render/Railway | Vĩnh viễn | 512MB | Shared | ❌ Sleep sau 15p |

> 💡 Oracle Cloud Free Tier **KHÔNG cần thẻ tín dụng** với VM AMD. Với VM ARM (mạnh hơn) cần verify thẻ nhưng **không bao giờ bị charge**.

---

## 📋 Bước 1: Tạo tài khoản Oracle Cloud

1. Truy cập [cloud.oracle.com/free](https://www.oracle.com/cloud/free/)
2. Click **"Start for Free"**
3. Điền thông tin:
   - **Country**: Vietnam
   - **Home Region**: chọn **Singapore** hoặc **Japan East (Tokyo)** (gần VN nhất)
   - Email sinh viên hoặc email thường đều OK
4. Verify email → hoàn tất đăng ký
5. Đợi khoảng 5-10 phút để tài khoản kích hoạt

---

## 📋 Bước 2: Tạo VM miễn phí

### Option A: VM AMD (Dễ tạo — khuyên dùng cho lần đầu)

1. Vào **Oracle Cloud Console** → Menu ☰ → **Compute** → **Instances**
2. Click **"Create Instance"**
3. Cấu hình:
   - **Name**: `bot-ai-trading`
   - **Image**: **Ubuntu 24.04** (Canonical)
   - **Shape**: Click "Change Shape" → **Specialty and previous generation** → **VM.Standard.E2.1.Micro**
     - (1 OCPU, 1GB RAM — **Always Free**)
   - **Networking**: Để mặc định (tạo VCN mới)
   - **Add SSH keys**: 
     - Chọn **"Generate a key pair"** → **Download** cả 2 file (private + public key)
     - Hoặc paste SSH public key từ Mac: `cat ~/.ssh/id_rsa.pub`
4. Click **"Create"** → đợi status chuyển sang **RUNNING**
5. Copy **Public IP Address** (ví dụ: `152.67.xxx.xxx`)

### Option B: VM ARM Ampere (Mạnh hơn nhiều — miễn phí)

> VM ARM cho 4 OCPU + 24GB RAM miễn phí, nhưng thường hết slot. Thử tạo, nếu báo "Out of capacity" thì dùng Option A.

1. Cùng bước như trên, nhưng chọn Shape: **VM.Standard.A1.Flex**
   - **OCPU**: 1 (có thể dùng tới 4)
   - **RAM**: 6GB (có thể dùng tới 24GB)
2. Nếu báo **"Out of host capacity"** → thử lại sau vài giờ, hoặc dùng Option A

### Mở port 8080 (QUAN TRỌNG!)

Oracle Cloud mặc định **block mọi port** trừ SSH. Phải mở port 8080:

**Bước 2a: Mở trên Oracle Cloud Console**
1. Vào instance → click **Subnet** (trong phần Networking)
2. Click **Security List** (Default Security List)
3. Click **"Add Ingress Rules"**:
   - **Source CIDR**: `0.0.0.0/0` (hoặc IP nhà bạn nếu muốn bảo mật hơn)
   - **Destination Port Range**: `8080`
   - **Description**: Bot AI Dashboard
4. Click **"Add Ingress Rules"**

**Bước 2b: Mở trên Ubuntu firewall** (sau khi SSH vào)
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT
sudo netfilter-persistent save
```

---

## 📋 Bước 3: Cài đặt VPS

SSH vào VPS từ Mac:
```bash
# Nếu dùng SSH key download từ Oracle:
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@152.67.xxx.xxx

# Nếu dùng SSH key có sẵn trên Mac:
ssh ubuntu@152.67.xxx.xxx
```

> ⚠️ Oracle Cloud dùng user `ubuntu` (không phải `root`)

Chạy script setup tự động (cài Python, tạo swap, tạo systemd service):
```bash
# Upload file setup_vps.sh lên VPS (từ Mac)
# scp setup_vps.sh ubuntu@152.67.xxx.xxx:/home/ubuntu/

# Hoặc trên VPS, tạo thủ công:
cd /home/ubuntu/bot-ai
chmod +x setup_vps.sh
sudo ./setup_vps.sh
```

Script này sẽ tự động:
- Cài Python 3 + pip + venv
- Tạo virtual environment `.venv` và cài requirements
- Thêm 2GB swap (quan trọng cho VM 1GB RAM)
- Mở port 8080 qua iptables
- Tạo systemd service `bot-ai` (tự start khi VPS khởi động)

---

## 📋 Bước 4: Upload code lên VPS

### Cách 1: SCP (đơn giản nhất)

Từ **máy Mac** của bạn, chạy:
```bash
# Nén folder Bot AI
cd "/Users/vuthanhtrung/Downloads"
tar -czf bot-ai.tar.gz -C "Bot AI" "Bot AI"

# Upload lên VPS
scp bot-ai.tar.gz ubuntu@152.67.xxx.xxx:/home/ubuntu/

# SSH vào VPS và giải nén
ssh ubuntu@152.67.xxx.xxx
mkdir -p /home/ubuntu/bot-ai
tar -xzf /home/ubuntu/bot-ai.tar.gz -C /home/ubuntu/bot-ai --strip-components=1
cd /home/ubuntu/bot-ai
```

### Cách 2: Git (recommended cho sau này)
```bash
# Trên máy Mac - push code lên GitHub private repo
cd "/Users/vuthanhtrung/Downloads/Bot AI/Bot AI"
git init
git add .
git commit -m "Initial commit"
# Tạo repo PRIVATE trên github.com trước, rồi:
git remote add origin git@github.com:YOUR_USERNAME/bot-ai-trading.git
git push -u origin main

# Trên VPS - clone về
ssh ubuntu@152.67.xxx.xxx
cd /home/ubuntu
git clone https://github.com/YOUR_USERNAME/bot-ai-trading.git bot-ai
cd /home/ubuntu/bot-ai
```

---

## 📋 Bước 5: Cấu hình

Trên VPS, tạo file `.env`:
```bash
cd /home/ubuntu/bot-ai
cp .env.example .env
nano .env
```

Điền API keys:
```env
BINANCE_API_KEY=bKB0TeDnFtDLh1yc7zEQWv0egLJbT1PoxGexmTzRAsMRueZOm62hOjFIc7nXyHgD
BINANCE_SECRET_KEY=FbRdzXolQmMndEgwGX4oM1aapSk9r5z8XSPOTSdhEQh2YrgXunEzFsVXdbAlhLnq
BINANCE_TESTNET=true
BOT_PORT=8080
FLASK_SECRET_KEY=thay-bang-chuoi-ngau-nhien-cua-ban
```

> ⚠️ Khi chuyển sang **REAL trading**, đổi `BINANCE_TESTNET=false` và dùng API keys thật từ binance.com

---

## 📋 Bước 6: Chạy Bot

```bash
cd /home/ubuntu/bot-ai

# Start bot
sudo systemctl start bot-ai

# Kiểm tra trạng thái
sudo systemctl status bot-ai

# Xem logs realtime
sudo journalctl -u bot-ai -f
```

**Truy cập Dashboard**: Mở browser → `http://152.67.xxx.xxx:8080`

---

## 📋 Bước 7: Bảo mật

Bảo mật đã được xử lý ở Bước 2 (Oracle Security List).

Nếu muốn thêm lớp bảo mật trên Ubuntu:
```bash
# Chỉ cho IP nhà bạn truy cập dashboard
sudo ufw allow 22/tcp
sudo ufw allow from YOUR_IP to any port 8080
sudo ufw enable
```

Thay `YOUR_IP` bằng IP nhà bạn (kiểm tra tại [whatismyip.com](https://www.whatismyip.com/)).

### Optional: HTTPS với domain
Nếu có domain (ví dụ: `bot.example.com`):
```bash
apt install -y nginx certbot python3-certbot-nginx

# Config nginx
cat > /etc/nginx/sites-available/bot-ai << 'EOF'
server {
    listen 80;
    server_name bot.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
EOF

ln -s /etc/nginx/sites-available/bot-ai /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

# SSL certificate (free)
certbot --nginx -d bot.example.com
```

---

## 🔧 Quản lý hàng ngày

### Các lệnh thường dùng
```bash
# Xem trạng thái
sudo systemctl status bot-ai

# Xem logs realtime
sudo journalctl -u bot-ai -f

# Xem 50 dòng log cuối
sudo journalctl -u bot-ai --no-pager -n 50

# Restart bot
sudo systemctl restart bot-ai

# Stop bot
sudo systemctl stop bot-ai

# Start lại
sudo systemctl start bot-ai
```

### Update code mới
```bash
cd /home/ubuntu/bot-ai

# Cách 1: SCP file mới
# (từ Mac) scp smart_bot_engine.py ubuntu@152.67.xxx.xxx:/home/ubuntu/bot-ai/

# Cách 2: Git pull
git pull origin main

# Cài lại dependencies (nếu requirements.txt thay đổi)
.venv/bin/pip install -r requirements.txt

# Restart bot
sudo systemctl restart bot-ai
```

---

## 🔍 Troubleshooting

### Bot không start
```bash
# Xem error logs
sudo journalctl -u bot-ai --no-pager -n 50

# Check file .env có đúng không
cat /home/ubuntu/bot-ai/.env

# Thử chạy thủ công để debug
cd /home/ubuntu/bot-ai
.venv/bin/python -c "from config import Config; print(Config.BINANCE_API_KEY[:10])"
.venv/bin/gunicorn --bind 0.0.0.0:8080 --workers 1 --timeout 120 web_dashboard:app
```

### Dashboard không truy cập được
```bash
# Check bot có đang chạy không
sudo systemctl status bot-ai

# Check port 8080 có đang listen không
sudo ss -tlnp | grep 8080

# Kiểm tra iptables
sudo iptables -L INPUT -n --line-numbers | grep 8080
```

### Out of memory (1GB RAM)
Swap đã được thêm ở Bước 3. Nếu vẫn thiếu RAM:
```bash
# Kiểm tra memory
free -h

# Tăng swap lên 4GB
sudo swapoff /swapfile
sudo fallocate -l 4G /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## 💰 Chi phí

| Mục | Chi phí/tháng |
|-----|--------------|
| Oracle Cloud VM (Always Free) | **$0 (MIỄN PHÍ)** |
| Domain (optional) | ~$1/tháng (~25k VNĐ) |
| **Tổng** | **$0/tháng** |

> 🎓 Hoàn toàn miễn phí, phù hợp sinh viên!

---

## 📱 Truy cập mọi lúc mọi nơi

Sau khi deploy:
1. Mở browser trên **điện thoại/máy tính** → `http://IP_VPS:8080`
2. **Start Bot** từ dashboard
3. Bot chạy 24/7 trên server, bạn chỉ cần mở web để monitor
4. Nếu VPS restart (hiếm), systemd tự khởi động lại bot (đã enable auto-start)

> 💡 Tip: Bookmark URL dashboard trên điện thoại, thêm vào Home Screen để dùng như app!

---

## ⚡ Tóm tắt nhanh (cho lần sau)

```bash
# SSH vào VPS
ssh ubuntu@152.67.xxx.xxx

# Xem bot đang chạy không
sudo systemctl status bot-ai

# Xem logs
sudo journalctl -u bot-ai -f

# Restart bot
sudo systemctl restart bot-ai

# Update code + restart
cd /home/ubuntu/bot-ai && git pull && sudo systemctl restart bot-ai
```
