"""Hourly spot candles for the underlyings into data/_spot/<SYM>.json as [[ts, open, high, low, close], ...]."""
import json, os, time, urllib.request, urllib.parse
from datetime import datetime, timezone

START = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
END = int(time.time())
UA = {"User-Agent": "Mozilla/5.0 polymarket-data-fetcher", "Accept": "application/json"}
os.makedirs("data/_spot", exist_ok=True)

def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.load(r)
        except Exception as e:
            print("  fail", url[:90], repr(e)[:150], flush=True)
            time.sleep(2 * (i + 1))
    return None

def coinbase(product):
    rows, t = {}, START
    while t < END:
        e = min(t + 300 * 3600, END)
        iso = lambda x: datetime.fromtimestamp(x, timezone.utc).isoformat()
        d = get(f"https://api.exchange.coinbase.com/products/{product}/candles?granularity=3600&start={urllib.parse.quote(iso(t))}&end={urllib.parse.quote(iso(e))}")
        for ts, lo, hi, op, cl, _v in d or []:
            rows[ts] = [ts, op, hi, lo, cl]
        t = e
        time.sleep(0.4)
    return [rows[k] for k in sorted(rows)]

def yahoo(sym):
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1h&period1={START}&period2={END}")
    try:
        r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]
        return [[ts, o, h, l, c] for ts, o, h, l, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]) if c is not None]
    except Exception as e:
        print("  yahoo parse fail", sym, repr(e)[:100]); return []

for name, fn, arg, fb in [("BTC", coinbase, "BTC-USD", "BTC-USD"), ("ETH", coinbase, "ETH-USD", "ETH-USD"),
                          ("SOL", coinbase, "SOL-USD", "SOL-USD"), ("WTI", yahoo, "CL=F", None)]:
    rows = fn(arg)
    if not rows and fb:
        rows = yahoo(fb)
    json.dump(rows, open(f"data/_spot/{name}.json", "w"))
    print(f"{name}: {len(rows)} hourly candles", flush=True)
