"""Live recorder: every ~1s, the order book of the current BTC 5m window (Up and Down tokens)
plus the Binance BTCUSDT price. Writes data/_btc5m/live/<run_start>.jsonl
Usage: python btc5m/live.py <minutes>
"""
import json, os, sys, time, urllib.request

MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 30
UA = {"User-Agent": "Mozilla/5.0 polymarket-data-fetcher", "Accept": "application/json"}
os.makedirs("data/_btc5m/live", exist_ok=True)
T0 = int(time.time())
out = open(f"data/_btc5m/live/{T0}.jsonl", "w")


def req(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(UA, **({"Content-Type": "application/json"} if data else {}))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=5) as r:
            return json.load(r)
    except Exception as e:
        print("err", url[:80], repr(e)[:120], flush=True)
        return None


meta = {}
def market(start):
    if start not in meta:
        e = req(f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{start}")
        if not e:
            return None
        m = e["markets"][0]
        meta[start] = dict(tokens=json.loads(m["clobTokenIds"]), md=e.get("eventMetadata"))
        out.write(json.dumps({"type": "market", "start": start, **meta[start]}) + "\n")
    return meta[start]


def top(levels, n=6, rev=False):
    lv = sorted(((float(l["price"]), float(l["size"])) for l in levels or []), reverse=rev)
    return lv[:n]


while time.time() < T0 + MIN * 60:
    t = time.time()
    start = int(t) // 300 * 300
    m = market(start)
    spot = req("https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=BTCUSDT")
    books = req("https://clob.polymarket.com/books", [{"token_id": x} for x in m["tokens"]]) if m else None
    rec = {"type": "tick", "t": round(t, 3), "start": start,
           "spot": [float(spot["bidPrice"]), float(spot["askPrice"])] if spot else None}
    if books:
        bt = {b["asset_id"]: b for b in books}
        for name, tok in zip(("up", "down"), m["tokens"]):
            b = bt.get(tok, {})
            rec[name] = {"bids": top(b.get("bids"), rev=True), "asks": top(b.get("asks"))}
    out.write(json.dumps(rec) + "\n")
    out.flush()
    # previous window's resolution metadata once it lands
    prev = start - 300
    if prev in meta and not (meta[prev].get("md") or {}).get("finalPrice") and t - start > 20 and int(t) % 10 == 0:
        e = req(f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{prev}")
        if e and (e.get("eventMetadata") or {}).get("finalPrice"):
            meta[prev]["md"] = e["eventMetadata"]
            out.write(json.dumps({"type": "resolved", "start": prev, "md": e["eventMetadata"],
                                  "outcome_prices": e["markets"][0].get("outcomePrices")}) + "\n")
    time.sleep(max(0, 1 - (time.time() - t)))
print("done", flush=True)
