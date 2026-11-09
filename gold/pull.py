"""Gold (XAU) Up/Down history: rules, outcomes, taker trades, and Binance PAXGUSDT 1s as a live gold proxy.
Usage: python gold/pull.py <hours_back> <step_seconds> <slug_prefix>"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
HOURS, STEP, PREF = float(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
OUT = f"data/_gold/{PREF}"; os.makedirs(f"{OUT}/trades", exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 polymarket-data-fetcher", "Accept": "application/json"}
def get(url, params=None, tries=4):
    if params: url += "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 410, 422): return None
            if e.code == 429: time.sleep(5)
        except Exception as e: print("  err", url[:120], repr(e)[:120], flush=True)
        time.sleep(1.5 * (i + 1))
now = int(time.time()); last = now // STEP * STEP - STEP
starts = list(range(last - int(HOURS * 3600) // STEP * STEP, last + 1, STEP))
# 5-minute check across several slug spellings over the last 2 hours
for p in ("xau-updown-5m", "gold-updown-5m", "xauusd-updown-5m", "xag-updown-5m"):
    hits = [t for t in range(now // 300 * 300 - 7200, now, 300) if get(f"https://gamma-api.polymarket.com/events/slug/{p}-{t}")]
    print("5m check", p, "hits", len(hits), flush=True)
mfile = f"{OUT}/markets.jsonl"; seen = {json.loads(l)["start"] for l in open(mfile)} if os.path.exists(mfile) else set()
full_saved = os.path.exists(f"{OUT}/sample_event.json")
with open(mfile, "a") as mf:
    for t in starts:
        if t in seen: continue
        e = get(f"https://gamma-api.polymarket.com/events/slug/{PREF}-{t}")
        if not e or not e.get("markets"): continue
        if not full_saved: json.dump(e, open(f"{OUT}/sample_event.json", "w"), indent=1); full_saved = True
        m = e["markets"][0]; md = e.get("eventMetadata") or {}
        rec = dict(slug=e["slug"], start=t, condition=m["conditionId"], tokens=json.loads(m["clobTokenIds"]),
                   outcomes=json.loads(m["outcomes"]), price_to_beat=md.get("priceToBeat"), final_price=md.get("finalPrice"),
                   outcome_prices=json.loads(m.get("outcomePrices") or "[]"), closed=m.get("closed"), volume=m.get("volumeNum"),
                   fee=m.get("feeSchedule"), cfg=m.get("cryptoMarketConfig") or m.get("equityMarketConfig"), meta=md)
        mf.write(json.dumps(rec) + "\n"); mf.flush(); seen.add(t); time.sleep(0.1)
print("markets", len(seen), flush=True)
for m in [json.loads(l) for l in open(mfile)]:
    fn = f"{OUT}/trades/{m['start']}.json"
    if os.path.exists(fn) or m["start"] not in starts: continue
    rows, cur = [], None
    for _ in range(10):
        p = {"condition": m["condition"], "taker_only": "true", "limit": 1000}
        if cur: p["cursor"] = cur
        b = get("https://data-api.polymarket.com/v2/trades", p)
        if not isinstance(b, dict): break
        page = b.get("data") or []
        rows += [[r["timestamp"], r["side"], r["outcome_index"], r["price"], r["size"]] for r in page]
        cur = (b.get("pagination") or {}).get("next_cursor")
        if not cur or not page: break
    json.dump(rows, open(fn, "w"))
# PAXG 1s klines (tokenised gold, trades 24/7 on Binance)
os.makedirs("data/_gold/paxg_1s", exist_ok=True)
t, t1, rows = (starts[0] - 600) * 1000, (last + STEP + 300) * 1000, {}
while t < t1:
    d = get("https://data-api.binance.vision/api/v3/klines", {"symbol": "PAXGUSDT", "interval": "1s", "startTime": t, "limit": 1000})
    if not d: t += 1000 * 1000; continue
    for r in d: rows[r[0]] = [r[0], float(r[4]), float(r[5])]
    t = d[-1][0] + 1000; time.sleep(0.05)
fn = "data/_gold/paxg_1s/paxg.json"
old = {r[0]: r for r in json.load(open(fn))} if os.path.exists(fn) else {}
old.update(rows); json.dump([old[k] for k in sorted(old)], open(fn, "w")); print("paxg rows", len(old), flush=True)
