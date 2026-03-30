#!/bin/bash
pkill -f web_dashboard.py 2>/dev/null
sleep 2
cd "$(dirname "$0")"
nohup .venv/bin/python3 web_dashboard.py > /tmp/bot_server.log 2>&1 &
echo "Bot started PID=$!"
