"""Download a Polymarket wallet's public data into data/<wallet>/."""
import json, os, sys, time, urllib.request, urllib.error

WALLET = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WALLET", "")).lower()
BASE = "https://data-api.polymarket.com"
ENDPOINTS = {
    "positions": ("/positions", {"sizeThreshold": "0"}, 500),
    "closed_positions": ("/closed-positions", {}, 50),
    "trades": ("/trades", {"takerOnly": "false"}, 500),
    "activity": ("/activity", {}, 500),
}

def get(path, params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{BASE}{path}?{q}", headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) polymarket-data-fetcher", "Accept": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} on {path}: {e.read()[:300]!r}", flush=True)
            if e.code in (400, 404):
                return None  # offset past the API's limit
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            print(f"  error on {path}: {e!r}", flush=True)
            time.sleep(2 * (attempt + 1))
    return None

def fetch_all(path, extra, page):
    rows, offset = [], 0
    while True:
        data = get(path, {"user": WALLET, "limit": page, "offset": offset, **extra})
        if isinstance(data, dict):  # some endpoints wrap results
            data = data.get("data") or data.get("results") or []
        if not data:
            break
        rows.extend(data)
        print(f"  {path}: {len(rows)} rows")
        if len(data) < page:
            break
        offset += page
        time.sleep(0.3)
    return rows

if __name__ == "__main__":
    if not WALLET.startswith("0x"):
        sys.exit("Usage: python fetch.py <wallet address>")
    out = os.path.join("data", WALLET)
    os.makedirs(out, exist_ok=True)
    for name, (path, extra, page) in ENDPOINTS.items():
        rows = fetch_all(path, extra, page)
        with open(os.path.join(out, f"{name}.json"), "w") as f:
            json.dump(rows, f)
        print(f"{name}: {len(rows)} rows saved")
    with open(os.path.join(out, "fetched_at.txt"), "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
