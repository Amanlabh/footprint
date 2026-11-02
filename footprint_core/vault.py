"""Personal environment: GitHub-backed API keys + context sync.

Your GitHub account is the identity, a private `footprint-vault` repo is the
storage. No footprint server, no footprint database — keys.json holds sha256
hashes of your API keys; data/ + adapters/ sync through the repo so every
device shares the same context.

  footprint login fp_…         sign in with the API key from the website (one time per device)
  footprint login              GitHub device-flow sign in (sync only)
  footprint key list           list keys
  footprint key revoke PREFIX  revoke by prefix
  footprint sync push|pull     sync training data + adapters via the vault
"""
import base64, json, os, shutil, subprocess, sys, time, urllib.request

from . import config, context

VAULT = "footprint-vault"
HOME = os.path.expanduser("~/.footprint")
TOKEN_FILE = os.path.join(HOME, "github_token")
KEY_FILE = os.path.join(HOME, "key")
CLONE = os.path.join(HOME, "vault")
API = os.environ.get("FOOTPRINT_API", "https://www.tracefootprint.space").rstrip("/")  # www: apex 308-redirects
# footprint's public OAuth app id (device flow needs no secret); override if self-hosting
CLIENT_ID = os.environ.get("FOOTPRINT_GITHUB_CLIENT_ID", "")


def _http(url, data=None, token=None, method=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(data).encode() if data is not None else None)
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or "{}")
        except json.JSONDecodeError:  # HTML error page
            return e.code, {}


def _token():
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    sys.exit("not signed in. run: footprint login")


def login(argv=()):
    if argv and argv[0].startswith("fp_"):
        return key_login(argv[0])
    if not CLIENT_ID:
        sys.exit("set FOOTPRINT_GITHUB_CLIENT_ID (OAuth app client id with device flow enabled)")
    _, d = _http("https://github.com/login/device/code",
                 {"client_id": CLIENT_ID, "scope": "repo read:user"})
    print(f"open  {d['verification_uri']}\ncode  {d['user_code']}")
    while True:
        time.sleep(d.get("interval", 5))
        _, t = _http("https://github.com/login/oauth/access_token",
                     {"client_id": CLIENT_ID, "device_code": d["device_code"],
                      "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if "access_token" in t:
            break
        if t.get("error") not in ("authorization_pending", "slow_down"):
            sys.exit(f"login failed: {t.get('error')}")
    os.makedirs(HOME, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(t["access_token"])
    os.chmod(TOKEN_FILE, 0o600)
    login_name = _user(t["access_token"])
    _ensure_vault(t["access_token"], login_name)
    print(f"signed in as {login_name}; vault: github.com/{login_name}/{VAULT} (private)")


def key_login(key):
    """Website key -> verified by the footprint server -> saved; handover installed."""
    try:
        code, r = _http(f"{API}/api/me", token=key)
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach {API}: {e.reason}")
    if code != 200:
        sys.exit(f"key rejected ({code}): {r.get('error', 'generate a new one on the website')}")
    os.makedirs(HOME, exist_ok=True)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    context.install()
    print(f"signed in as {r['login']} · handover installed for Claude Code + OpenCode")


def _user(token):
    code, u = _http("https://api.github.com/user", token=token)
    if code != 200:
        sys.exit(f"github auth failed ({code}); re-run: footprint login")
    return u["login"]


def _ensure_vault(token, login_name):
    code, _ = _http(f"https://api.github.com/repos/{login_name}/{VAULT}", token=token)
    if code == 404:
        code, r = _http("https://api.github.com/user/repos", token=token, data={
            "name": VAULT, "private": True, "auto_init": True,
            "description": "footprint personal environment — API keys + synced context. Keep private."})
        if code not in (200, 201):
            sys.exit(f"could not create vault repo: {r.get('message')}")


def _keys_file(token, login_name):
    code, d = _http(f"https://api.github.com/repos/{login_name}/{VAULT}/contents/keys.json",
                    token=token)
    if code == 404:
        return [], None
    return json.loads(base64.b64decode(d["content"])), d["sha"]


def _write_keys(token, login_name, keys, sha, message):
    body = {"message": message,
            "content": base64.b64encode(json.dumps(keys, indent=2).encode()).decode()}
    if sha:
        body["sha"] = sha
    code, r = _http(f"https://api.github.com/repos/{login_name}/{VAULT}/contents/keys.json",
                    token=token, data=body, method="PUT")
    if code not in (200, 201):
        sys.exit(f"could not write keys.json: {r.get('message')}")


def keys_cmd(argv):
    token = _token()
    login_name = _user(token)
    _ensure_vault(token, login_name)
    sub = argv[0] if argv else "list"
    keys, sha = _keys_file(token, login_name)
    if sub == "new":
        sys.exit("generate keys on the footprint website (Account → Generate API key)")
    if sub == "revoke" and len(argv) > 1:
        left = [k for k in keys if not k["prefix"].startswith(argv[1])]
        if len(left) == len(keys):
            sys.exit(f"no key with prefix {argv[1]}")
        _write_keys(token, login_name, left, sha, f"footprint: revoke API key {argv[1]}…")
        print("revoked")
    else:
        for k in keys:
            print(f"{k['prefix']}…  {k['label']:<16} {k['created']}")
        if not keys:
            print("no keys. generate one on the footprint website")


def _clone(token, login_name):
    url = f"https://x-access-token:{token}@github.com/{login_name}/{VAULT}.git"
    if os.path.exists(os.path.join(CLONE, ".git")):
        subprocess.run(["git", "-C", CLONE, "remote", "set-url", "origin", url], check=True)
        subprocess.run(["git", "-C", CLONE, "pull", "-q"], check=True)
    else:
        os.makedirs(HOME, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, CLONE], check=True)


def sync_cmd(argv):
    direction = argv[0] if argv else ""
    if direction not in ("push", "pull"):
        sys.exit("usage: footprint sync push|pull")
    token = _token()
    login_name = _user(token)
    _ensure_vault(token, login_name)
    _clone(token, login_name)
    pairs = [(config.DATA, os.path.join(CLONE, "data")),
             (config.ADAPTERS, os.path.join(CLONE, "adapters"))]
    if direction == "push":
        for src, dst in pairs:
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
        subprocess.run(["git", "-C", CLONE, "add", "-A"], check=True)
        if subprocess.run(["git", "-C", CLONE, "diff", "--cached", "--quiet"]).returncode:
            subprocess.run(["git", "-C", CLONE, "commit", "-q", "-m", "footprint sync"], check=True)
            subprocess.run(["git", "-C", CLONE, "push", "-q"], check=True)
            print("pushed data/ + adapters/ to your vault (private repo)")
        else:
            print("nothing to push")
    else:
        for src, dst in pairs:
            if os.path.isdir(dst):
                shutil.copytree(dst, src, dirs_exist_ok=True)
        print("pulled data/ + adapters/ from your vault")
