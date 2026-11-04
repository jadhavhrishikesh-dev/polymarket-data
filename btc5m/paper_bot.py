"""Paper trader for Polymarket BTC 5-minute Up/Down markets (no real orders).

Prices each second with the TWAP fair-value model (btc5m/model.py logic, Binance as the price proxy),
"buys" a side when fair - ask - taker_fee >= EDGE, sizes small, and settles each window from Gamma.
Run it for a few days before risking money:  python btc5m/paper_bot.py
Log: btc5m_paper.jsonl  (one line per signal / fill / settlement)
"""
import json, math, time, urllib.request, collections

EDGE = 0.04            # required edge per share after fee
MAX_SHARES = 20        # per entry
MIN_TAU, MAX_TAU = 240, 285   # live-book test (36 windows): entries before 240s lost ~7% after fees
PMAX = 0.95            # never pay more than this
BASIS_SD = 4.15        # $ noise between Binance TWAP and Chainlink TWAP (measured on 577 windows)
SIG_LOOKBACK = 900     # seconds of 1s returns for volatility
FEE_RATE = 0.07
UA = {"User-Agent": "Mozilla/5.0 btc5m-paper", "Accept": "application/json"}
LOG = open("btc5m_paper.jsonl", "a")


def http(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(UA, **({"Content-Type": "application/json"} if data else {}))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=4) as r:
            return json.load(r)
    except Exception as e:
        print("http err", url[:70], repr(e)[:100]); return None


def btc():
    for u in ("https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT",
              "https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=BTCUSDT"):
        d = http(u)
        if d: return (float(d["bidPrice"]) + float(d["askPrice"])) / 2
    return None


def ncdf(z): return 0.5 * (1 + math.erf(z / math.sqrt(2)))
def fee(p, n): return n * FEE_RATE * p * (1 - p)


def fair_up(tau, prices, start, K, sig):
    x = prices[max(prices)]
    if tau <= 240:
        mu, sd = x, sig * math.sqrt(260 - tau)
    else:
        seg = [v for t, v in prices.items() if start + 240 <= t < start + tau] or [x]
        A = sum(seg) / len(seg); r = 300 - tau
        mu = ((tau - 240) * A + r * x) / 60; sd = sig * math.sqrt(r ** 3 / 3) / 60
    return ncdf((mu - K) / math.sqrt(sd ** 2 + BASIS_SD ** 2))


def log(**k):
    k["ts"] = round(time.time(), 2); LOG.write(json.dumps(k) + "\n"); LOG.flush(); print(k)


prices = collections.OrderedDict()  # second -> BTC price
meta, pos, pnl = {}, collections.defaultdict(list), 0.0
print("warming up volatility estimate (needs ~2 min before first trade, better 15 min)...")
while True:
    t0 = time.time(); now = int(t0); p = btc()
    if p: prices[now] = p
    while prices and next(iter(prices)) < now - 1200: prices.popitem(last=False)
    start = now // 300 * 300; tau = now - start
    # settle finished windows
    for s in [s for s in list(pos) if s + 330 < now]:
        e = http(f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{s}")
        op = json.loads(e["markets"][0]["outcomePrices"]) if e else None
        if op and op[0] in ("0", "1"):
            up = op[0] == "1"
            for side, px, n in pos.pop(s):
                win = up if side == "up" else not up
                d = n * ((1 if win else 0) - px) - fee(px, n); pnl += d
                log(kind="settle", start=s, side=side, price=px, shares=n, win=win, pnl=round(d, 4), total=round(pnl, 4))
    if start not in meta:
        e = http(f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{start}")
        if e: meta[start] = json.loads(e["markets"][0]["clobTokenIds"])
    secs = sorted(prices)
    have_strike = all(q in prices for q in range(start - 60, start, 5))
    if start in meta and have_strike and len(secs) > 120 and MIN_TAU <= tau <= MAX_TAU:
        K = sum(v for t, v in prices.items() if start - 60 <= t < start) / sum(1 for t in prices if start - 60 <= t < start)
        r = [prices[b] - prices[a] for a, b in zip(secs, secs[1:]) if b - a == 1][-SIG_LOOKBACK:]
        sig = math.sqrt(sum(x * x for x in r) / len(r))
        fu = fair_up(tau, prices, start, K, sig)
        books = http("https://clob.polymarket.com/books", [{"token_id": x} for x in meta[start]])
        if books:
            bt = {b["asset_id"]: b for b in books}
            for side, tok, f in (("up", meta[start][0], fu), ("down", meta[start][1], 1 - fu)):
                asks = sorted((float(a["price"]), float(a["size"])) for a in bt.get(tok, {}).get("asks", []))
                if not asks or asks[0][0] > PMAX: continue
                ask, size = asks[0]
                edge = f - ask - fee(ask, 1)
                if edge >= EDGE and not any(sd == side for sd, _, _ in pos[start]):
                    n = min(MAX_SHARES, size)
                    pos[start].append((side, ask, n))
                    log(kind="fill", start=start, tau=tau, side=side, price=ask, shares=n, fair=round(f, 4), edge=round(edge, 4), btc=p, strike=round(K, 2))
    time.sleep(max(0.0, 1 - (time.time() - t0)))
