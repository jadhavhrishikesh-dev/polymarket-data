"""Download one wallet's complete public Polymarket history (Data API v2) into data/<wallet>/.
Usage: python collect.py <wallet>
Writes slim gzip CSVs so the whole history fits in the repo."""
import csv, gzip, json, os, sys, time, urllib.parse, urllib.request, urllib.error

WALLET = sys.argv[1].lower()
BASE = "https://data-api.polymarket.com/v2"
UA = {"User-Agent": "Mozilla/5.0 polymarket-study", "Accept": "application/json"}
OUT = os.path.join("data", WALLET)
os.makedirs(OUT, exist_ok=True)

def get(path, params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    for i in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} {path}: {e.read()[:200]!r}", flush=True)
            if e.code in (400, 404, 410, 422):
                return None
        except Exception as e:
            print(f"  error {path}: {e!r}"[:200], flush=True)
        time.sleep(3 * (i + 1))
    return None

def pages(path, params):
    cursor, n = None, 0
    while True:
        p = {"cursor": cursor} if cursor else {**params, "limit": 1000}
        if cursor:
            p["user"] = params["user"]
        body = get(path, p)
        if not isinstance(body, dict):
            print(f"  stopped early on {path} after {n} rows", flush=True)
            return
        rows = body.get("data") or []
        yield from rows
        n += len(rows)
        if n % 50000 < 1000:
            print(f"  {path}: {n} rows", flush=True)
        cursor = (body.get("pagination") or {}).get("next_cursor")
        if not cursor or not rows:
            return
        time.sleep(0.15)

def key(t):
    return (t.get("transaction_hash"), t.get("token_id"), round(float(t.get("size") or 0), 4))

# 1. fills where this wallet was the taker (used to flag maker vs taker)
taker = set(key(t) for t in pages("/trades", {"user": WALLET, "taker_only": "true", "start": 1}))
print("taker fills:", len(taker), flush=True)

# 2. every fill, maker and taker
n = 0
with gzip.open(os.path.join(OUT, "trades.csv.gz"), "wt", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts", "slug", "outcome_index", "side", "size", "price", "taker"])
    for t in pages("/trades", {"user": WALLET, "taker_only": "false", "start": 1}):
        w.writerow([t.get("timestamp"), t.get("slug"), t.get("outcome_index"), t.get("side"), t.get("size"), t.get("price"), int(key(t) in taker)])
        n += 1
print("all fills:", n, flush=True)

# 3. everything that is not a trade: merges, redemptions, rebates, deposits, withdrawals
n = 0
with gzip.open(os.path.join(OUT, "activity.csv.gz"), "wt", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts", "type", "slug", "outcome_index", "size", "usdc"])
    types = "SPLIT,MERGE,REDEEM,CONVERSION,REWARD,YIELD,MAKER_REBATE,TAKER_REBATE,REFERRAL_REWARD,DEPOSIT,WITHDRAWAL"
    for a in pages("/activity", {"user": WALLET, "type": types, "start": 1, "exclude_deposits_withdrawals": "false"}):
        w.writerow([a.get("timestamp"), a.get("type"), a.get("slug"), a.get("outcome_index"), a.get("size"), a.get("usdc_size")])
        n += 1
print("activity rows:", n, flush=True)

# 4. summary feeds
for name, path, extra in [("user_stats", "/user-stats", {}), ("user_pnl_max", "/user-pnl", {"interval": "max", "fidelity": "1d"}), ("value", "/value", {})]:
    body = get(path, {"user": WALLET, **extra})
    json.dump(body.get("data") if isinstance(body, dict) and "data" in body else body, open(os.path.join(OUT, name + ".json"), "w"))
open(os.path.join(OUT, "fetched_at.txt"), "w").write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
