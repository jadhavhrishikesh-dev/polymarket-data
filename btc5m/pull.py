"""Historical pull for BTC 5-minute Up/Down markets.

data/_btc5m/markets.jsonl : one line per window (slug, start, tokens, priceToBeat, finalPrice, winner, fees, volume)
data/_btc5m/trades/<start>.json : taker trades for that window (Data API v2)
data/_btc5m/spot_1s/<day>.json : Binance BTCUSDT 1-second klines [ts_ms, o, h, l, c, vol]
Usage: python btc5m/pull.py <hours_back> [max_trade_pages]
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 24
MAXP = int(sys.argv[2]) if len(sys.argv) > 2 else 15
OUT = "data/_btc5m"
UA = {"User-Agent": "Mozilla/5.0 polymarket-data-fetcher", "Accept": "application/json"}
os.makedirs(f"{OUT}/trades", exist_ok=True)
os.makedirs(f"{OUT}/spot_1s", exist_ok=True)


def get(url, params=None, tries=4):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            print("  HTTP", e.code, url[:140], e.read()[:200], flush=True)
            if e.code in (400, 404, 410, 422):
                return None
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After") or 5))
        except Exception as e:
            print("  err", url[:140], repr(e)[:150], flush=True)
        time.sleep(1.5 * (i + 1))
    return None


now = int(time.time())
last_closed = now // 300 * 300 - 600
starts = list(range(last_closed - int(HOURS * 3600) // 300 * 300, last_closed + 1, 300))

# ---- markets
seen = set()
mfile = f"{OUT}/markets.jsonl"
if os.path.exists(mfile):
    for line in open(mfile):
        seen.add(json.loads(line)["start"])
with open(mfile, "a") as mf:
    for k, t in enumerate(starts):
        if t in seen:
            continue
        e = get(f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{t}")
        if not e or not e.get("markets"):
            continue
        m = e["markets"][0]
        md = e.get("eventMetadata") or {}
        prices = json.loads(m.get("outcomePrices") or "[]")
        rec = dict(slug=e["slug"], start=t, condition=m["conditionId"],
                   tokens=json.loads(m["clobTokenIds"]), outcomes=json.loads(m["outcomes"]),
                   price_to_beat=md.get("priceToBeat"), final_price=md.get("finalPrice"),
                   outcome_prices=prices, closed=m.get("closed"), volume=m.get("volumeNum"),
                   fee=m.get("feeSchedule"), twap=m.get("cryptoMarketConfig"))
        mf.write(json.dumps(rec) + "\n")
        mf.flush()
        seen.add(t)
        if k % 50 == 0:
            print("market", k, len(starts), rec["slug"], rec["price_to_beat"], rec["final_price"], prices, flush=True)
        time.sleep(0.1)

# ---- trades
mk = [json.loads(l) for l in open(mfile)]
for k, m in enumerate(mk):
    fn = f"{OUT}/trades/{m['start']}.json"
    if os.path.exists(fn) or m["start"] not in starts:
        continue
    rows, cur = [], None
    for _ in range(MAXP):
        p = {"condition": m["condition"], "taker_only": "true", "limit": 1000}
        if cur:
            p["cursor"] = cur
        b = get("https://data-api.polymarket.com/v2/trades", p)
        if not isinstance(b, dict):
            break
        page = b.get("data") or []
        rows += [[r["timestamp"], r["side"], r["outcome_index"], r["price"], r["size"]] for r in page]
        cur = (b.get("pagination") or {}).get("next_cursor")
        if not cur or not page:
            break
        time.sleep(0.15)
    json.dump(rows, open(fn, "w"))
    if k % 50 == 0:
        print("trades", k, len(mk), len(rows), flush=True)

# ---- 1s spot (Binance via data-api.binance.vision, reachable from US runners)
t0, t1 = (starts[0] - 600) * 1000, (last_closed + 900) * 1000
by_day = {}
t = t0
while t < t1:
    d = get("https://data-api.binance.vision/api/v3/klines",
            {"symbol": "BTCUSDT", "interval": "1s", "startTime": t, "limit": 1000})
    if not d:
        t += 1000 * 1000
        continue
    for r in d:
        day = time.strftime("%Y-%m-%d", time.gmtime(r[0] / 1000))
        by_day.setdefault(day, {})[r[0]] = [r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
    t = d[-1][0] + 1000
    time.sleep(0.05)
for day, rows in by_day.items():
    fn = f"{OUT}/spot_1s/{day}.json"
    old = {r[0]: r for r in json.load(open(fn))} if os.path.exists(fn) else {}
    old.update(rows)
    json.dump([old[k] for k in sorted(old)], open(fn, "w"))
    print("spot", day, len(old), flush=True)
print("done", flush=True)
