"""
GitHub Auto-Upload Script
Tạo repo và upload toàn bộ project lên GitHub qua API (không cần git/Xcode)
Usage: python upload_to_github.py
"""
import os
import sys
import base64

try:
    import requests
except ImportError:
    print("❌ Missing requests. Run: pip install requests")
    sys.exit(1)

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
REPO_NAME   = "binance-bot-ai"
REPO_DESC   = "Binance Futures Trading Bot with AI"
PRIVATE     = True   # Private repo (important - has API keys in history)

# Files/dirs to skip (same as .gitignore)
SKIP_PATTERNS = {
    ".env", ".venv", "venv", "__pycache__", ".git",
    "__MACOSX", ".DS_Store", ".idea", ".vscode",
    "upload_to_github.py",   # skip this script itself
    "node_modules",
}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".log"}

# Skip any dir that starts with these prefixes (handles .venv-1, .venv_old, etc.)
SKIP_PREFIXES = (".venv", "venv")

# ─── HELPERS ────────────────────────────────────────────────────────────────
def should_skip(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        if part in SKIP_PATTERNS:
            return True
        # Skip .venv-1, .venv_old, venv_old, etc.
        if part.startswith(SKIP_PREFIXES):
            return True
        _, ext = os.path.splitext(part)
        if ext in SKIP_EXTENSIONS:
            return True
    # Skip logs directory contents but not the dir itself
    if "logs" in parts and len(parts) > parts.index("logs") + 1:
        return True
    return False

def encode_file(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def create_repo(session: requests.Session, username: str) -> bool:
    print(f"\n📦 Creating repo '{REPO_NAME}'...")
    resp = session.post("https://api.github.com/user/repos", json={
        "name": REPO_NAME,
        "description": REPO_DESC,
        "private": PRIVATE,
        "auto_init": False,
    })
    if resp.status_code == 201:
        print(f"✅ Repo created: https://github.com/{username}/{REPO_NAME}")
        return True
    elif resp.status_code == 422:
        data = resp.json()
        if any("already exists" in e.get("message","") for e in data.get("errors",[])):
            print(f"ℹ️  Repo already exists — uploading files to existing repo")
            return True
    print(f"❌ Failed to create repo: {resp.status_code} {resp.text[:200]}")
    return False

def upload_file(session: requests.Session, username: str, rel_path: str, content_b64: str) -> bool:
    url  = f"https://api.github.com/repos/{username}/{REPO_NAME}/contents/{rel_path}"
    # Check if file already exists (get its SHA for update)
    sha = None
    check = session.get(url)
    if check.status_code == 200:
        sha = check.json().get("sha")

    payload = {
        "message": f"Update {rel_path}",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    resp = session.put(url, json=payload)
    return resp.status_code in (200, 201)

# ─── MAIN ───────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  GitHub Auto-Upload - Binance Bot AI")
    print("=" * 60)

    # Accept token from env var, CLI arg, or interactive prompt
    token = (
        os.environ.get("GH_TOKEN")
        or (sys.argv[1] if len(sys.argv) > 1 else None)
        or input("\n🔑 Paste your GitHub Personal Access Token: ").strip()
    )

    if not token:
        print("❌ Token is required")
        sys.exit(1)

    username = ""  # will be auto-detected from API

    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "BotAI-Uploader/1.0",
    })

    # Verify token
    me = session.get("https://api.github.com/user")
    if me.status_code != 200:
        print(f"❌ Invalid token: {me.status_code}")
        sys.exit(1)
    actual_username = me.json()["login"]
    print(f"✅ Authenticated as: {actual_username}")
    username = actual_username  # use actual username from API

    # Create repo
    if not create_repo(session, username):
        sys.exit(1)

    # Collect all files
    project_dir = os.path.dirname(os.path.abspath(__file__))
    all_files = []
    for root, dirs, files in os.walk(project_dir):
        # Filter dirs in-place to skip recursion into ignored dirs
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_PATTERNS and not d.startswith(SKIP_PREFIXES)
        ]
        for fname in files:
            fpath = os.path.join(root, fname)
            rel   = os.path.relpath(fpath, project_dir).replace("\\", "/")
            if not should_skip(rel):
                all_files.append((rel, fpath))

    print(f"\n📁 Found {len(all_files)} files to upload")

    # Sort: small text files first, large binaries last
    def sort_key(item):
        size = os.path.getsize(item[1])
        return size

    all_files.sort(key=sort_key)

    # Upload
    success = 0
    failed  = []
    for i, (rel, fpath) in enumerate(all_files, 1):
        size_kb = os.path.getsize(fpath) / 1024
        size_str = f"{size_kb:.0f}KB" if size_kb < 1024 else f"{size_kb/1024:.1f}MB"
        print(f"[{i:3d}/{len(all_files)}] {rel} ({size_str})", end=" ... ", flush=True)

        try:
            content_b64 = encode_file(fpath)
            if upload_file(session, username, rel, content_b64):
                print("✅")
                success += 1
            else:
                print("❌ FAILED")
                failed.append(rel)
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed.append(rel)

    # Summary
    print("\n" + "=" * 60)
    print(f"✅ Uploaded: {success}/{len(all_files)} files")
    if failed:
        print(f"❌ Failed:   {len(failed)} files")
        for f in failed:
            print(f"   - {f}")
    print(f"\n🌐 Repo URL: https://github.com/{username}/{REPO_NAME}")
    print("=" * 60)

    if success > 0:
        print("\n✅ DONE! Now go to render.com and connect this GitHub repo")

if __name__ == "__main__":
    main()
