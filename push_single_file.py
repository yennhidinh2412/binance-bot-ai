"""
Quick script: push ONLY web_dashboard.py to GitHub
Usage: python3 push_single_file.py
"""
import os, sys, base64, json

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

REPO = "binance-bot-ai"
FILE_PATH = "web_dashboard.py"

token = os.environ.get("GH_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not token:
    token = input("🔑 Paste GitHub Token: ").strip()
if not token:
    print("❌ No token"); sys.exit(1)

s = requests.Session()
s.headers.update({
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json",
})

# Get username
me = s.get("https://api.github.com/user")
if me.status_code != 200:
    print(f"❌ Token invalid: {me.status_code}"); sys.exit(1)
user = me.json()["login"]
print(f"👤 Logged in as: {user}")

# Read local file
with open(FILE_PATH, "rb") as f:
    content_b64 = base64.b64encode(f.read()).decode()

# Get existing SHA
url = f"https://api.github.com/repos/{user}/{REPO}/contents/{FILE_PATH}"
check = s.get(url)
sha = check.json().get("sha") if check.status_code == 200 else None

# Upload
payload = {"message": f"Update {FILE_PATH} - add debug endpoints", "content": content_b64}
if sha:
    payload["sha"] = sha

resp = s.put(url, json=payload)
if resp.status_code in (200, 201):
    print(f"✅ {FILE_PATH} pushed successfully!")
    print(f"   Commit: {resp.json()['commit']['sha'][:8]}")
else:
    print(f"❌ Failed: {resp.status_code} {resp.text[:200]}")
