"""Download a Polymarket wallet's public data (Data API v2) into data/<wallet>/."""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

WALLET = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WALLET", "")).lower()
BASE = "https://data-api.polymarket.com/v2"
MAX_ROWS = 50000  # safety cap per feed

# name -> (path, extra params, paginated)
FEEDS = {
    "positions_open": ("/positions", {"status": "OPEN"}, True),
    "positions_redeemable": ("/positions", {"status": "REDEEMABLE"}, True),
    "positions_redeemable_lost": ("/positions", {"status": "REDEEMABLE_LOST"}, True),
    "positions_closed": ("/positions", {"status": "CLOSED"}, True),
    "trades": ("/trades", {"taker_only": "false"}, True),
    "activity": ("/activity", {}, True),
    "user_stats": ("/user-stats", {}, False),
    "value": ("/value", {}, False),
    "user_volume": ("/user-volume", {}, False),
    "user_pnl": ("/user-pnl", {}, False),
}

def get(path, params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 polymarket-data-fetcher", "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} on {path} {params.get('status','')}: {e.read()[:300]!r}", flush=True)
            if e.code in (400, 404, 410, 422):
                return None
        except Exception as e:
            print(f"  error on {path}: {e!r}", flush=True)
        time.sleep(2 * (attempt + 1))
    return None

def fetch(path, extra, paginated):
    params = {"user": WALLET, **extra}
    if not paginated:
        body = get(path, params)
        return body.get("data") if isinstance(body, dict) else body
    rows, cursor = [], None
    while True:
        p = {**params, "limit": 1000}
        if cursor:
            p["cursor"] = cursor
        body = get(path, p)
        if not isinstance(body, dict):
            break
        page = body.get("data") or []
        rows.extend(page)
        cursor = (body.get("pagination") or {}).get("next_cursor")
        print(f"  {path} {extra}: {len(rows)} rows", flush=True)
        if not cursor or not page or len(rows) >= MAX_ROWS:
            break
        time.sleep(0.25)
    return rows

if __name__ == "__main__":
    if not WALLET.startswith("0x"):
        sys.exit("Usage: python fetch.py <wallet address>")
    out = os.path.join("data", WALLET)
    os.makedirs(out, exist_ok=True)
    for name, (path, extra, paginated) in FEEDS.items():
        rows = fetch(path, extra, paginated)
        with open(os.path.join(out, f"{name}.json"), "w") as f:
            json.dump(rows, f)
        n = len(rows) if isinstance(rows, list) else ("1 object" if rows else 0)
        print(f"{name}: {n} saved", flush=True)
    with open(os.path.join(out, "fetched_at.txt"), "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
