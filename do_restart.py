#!/usr/bin/env python3
import subprocess, os, time, signal

# Kill existing server
try:
    result = subprocess.run(['pgrep', '-f', 'web_dashboard.py'], capture_output=True, text=True)
    pids = result.stdout.strip().split()
    for pid in pids:
        if pid:
            os.kill(int(pid), signal.SIGTERM)
            print(f"Killed PID {pid}")
    time.sleep(2)
except Exception as e:
    print(f"Kill error (ok): {e}")

# Start new server
bot_dir = os.path.dirname(os.path.abspath(__file__))
log_file = open('/tmp/bot_server.log', 'w')
proc = subprocess.Popen(
    [os.path.join(bot_dir, '.venv/bin/python3'), 'web_dashboard.py'],
    cwd=bot_dir,
    stdout=log_file,
    stderr=log_file,
    start_new_session=True
)
print(f"Bot started PID={proc.pid}")
print("Log: /tmp/bot_server.log")
