"""Extra data for strategy analysis: taker-only trades and price histories of the most-traded tokens."""
import json, os, sys, time, urllib.parse, urllib.request, collections

WALLET = sys.argv[1].lower()
TOP = int(sys.argv[2]) if len(sys.argv) > 2 else 300
BASE = "https://data-api.polymarket.com/v2"
UA = {"User-Agent": "Mozilla/5.0 polymarket-data-fetcher", "Accept": "application/json"}
W = os.path.join("data", WALLET)

def get(path, params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            print("  HTTP", e.code, path, e.read()[:200], flush=True)
            if e.code in (400, 404, 410, 422): return None
        except Exception as e:
            print("  err", path, repr(e)[:120], flush=True)
        time.sleep(2 * (i + 1))
    return None

def pages(path, params, key_limit="limit", lim=1000):
    rows, cur = [], None
    while True:
        p = dict(params)
        if cur: p["cursor"] = cur
        elif key_limit: p[key_limit] = lim
        b = get(path, p)
        if not isinstance(b, dict): break
        data = b.get("data")
        if isinstance(data, dict):  # price history may nest points
            data = data.get("points") or data.get("history") or []
        rows += data or []
        cur = (b.get("pagination") or {}).get("next_cursor") or b.get("next_cursor")
        if not cur or not data: break
        time.sleep(0.2)
    return rows

taker = pages("/trades", {"user": WALLET, "taker_only": "true"})
json.dump(taker, open(f"{W}/trades_taker.json", "w"))
print("taker trades", len(taker), flush=True)

tr = json.load(open(f"{W}/trades.json"))
usd = collections.Counter()
for t in tr:
    usd[t["token_id"]] += t["size"] * t["price"]
os.makedirs(f"{W}/prices", exist_ok=True)
sample = None
for k, (tok, _) in enumerate(usd.most_common(TOP)):
    fn = f"{W}/prices/{tok}.json"
    if os.path.exists(fn): continue
    pts = pages("/prices-history", {"token_id": tok, "interval": "max", "bucket_seconds": 1800}, key_limit=None)
    if sample is None and pts: sample = pts[0]; print("sample point", json.dumps(sample)[:300], flush=True)
    json.dump(pts, open(fn, "w"))
    if k % 25 == 0: print(f"prices {k}: {len(pts)} pts", flush=True)
    time.sleep(0.15)
print("done", flush=True)
