"""
Push updated files to GitHub
Usage: python3 push_fixes.py
"""
import os, sys, base64

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

REPO = "binance-bot-ai"
FILES = [
    (
        "web_dashboard.py",
        "Fix: Auto-detect hedge/one-way mode, no positionSide error, division by zero, trend-based signals",
    ),
    (
        "smart_bot_engine.py",
        "Fix: Auto-detect hedge/one-way mode, trend-based signals, division by zero, auto get price/SL/TP",
    ),
    (
        "config.py",
        "Fix: min_adx_trend 20→15, min_balance $5→$1",
    ),
    (
        "train_ai_improved.py",
        "Fix: align_features_to_model pad missing features",
    ),
    (
        "templates/dashboard.html",
        "Feat: Long/Short buttons, instant start/stop feedback",
    ),
    (
        "models/closed_trades.json",
        "Reset: clear trade history for fresh start",
    ),
]

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

me = s.get("https://api.github.com/user")
if me.status_code != 200:
    print(f"❌ Token invalid: {me.status_code}"); sys.exit(1)
user = me.json()["login"]
print(f"👤 Logged in as: {user}")

for file_path, msg in FILES:
    print(f"\n📤 Pushing {file_path}...")
    with open(file_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    url = f"https://api.github.com/repos/{user}/{REPO}/contents/{file_path}"
    check = s.get(url)
    sha = check.json().get("sha") if check.status_code == 200 else None

    payload = {"message": msg, "content": content_b64}
    if sha:
        payload["sha"] = sha

    resp = s.put(url, json=payload)
    if resp.status_code in (200, 201):
        print(f"   ✅ OK! Commit: {resp.json()['commit']['sha'][:8]}")
    else:
        print(f"   ❌ Failed: {resp.status_code} {resp.text[:200]}")

print("\n🎉 Done! Render will auto-deploy in ~1-2 minutes.")
