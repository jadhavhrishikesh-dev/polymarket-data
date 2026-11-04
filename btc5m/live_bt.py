"""Backtest on recorded live order books (true timestamps, true asks) with real outcomes.
Decision at second s uses Binance up to s-1 and the book recorded at s (no look-ahead)."""
import json, glob, math, sys, numpy as np
sys.path.insert(0, "btc5m")
from model import taker_fee
M = {json.loads(l)["start"]: json.loads(l) for l in open("data/_btc5m/markets.jsonl")}
BASIS = 4.15
def N(z): return 0.5 * (1 + math.erf(z / math.sqrt(2)))
ticks = {}
for f in sorted(glob.glob("data/_btc5m/live/*.jsonl")):
    for l in open(f):
        r = json.loads(l)
        if r["type"] == "tick" and r.get("spot") and r.get("up"):
            ticks[int(round(r["t"]))] = r
secs = sorted(ticks); spot = {}; last = None
for s in range(secs[0], secs[-1] + 1):
    if s in ticks: last = sum(ticks[s]["spot"]) / 2
    spot[s] = last
def sig_at(s, look=600):
    v = [spot[q] - spot[q - 1] for q in range(max(secs[0] + 1, s - look), s)]
    return math.sqrt(sum(x * x for x in v) / len(v)) if len(v) > 60 else None
rows = []
for s in secs:
    r = ticks[s]; st = r["start"]; tau = s - st; m = M.get(st)
    if not m or not m.get("final_price") or st - 60 < secs[0] or tau < 1: continue
    sig = sig_at(st)
    if not sig: continue
    up = m["outcome_prices"][0] in ("1", "1.0")
    K = np.mean([spot[q] for q in range(st - 60, st)]); x = spot[s - 1]
    if tau <= 240: mu, sd = x, sig * math.sqrt(260 - tau)
    else:
        A = np.mean([spot[q] for q in range(st + 240, s)]); mu = ((tau - 240) * A + (300 - tau) * x) / 60
        sd = sig * math.sqrt((300 - tau) ** 3 / 3) / 60
    fu = N((mu - K) / math.sqrt(sd ** 2 + BASIS ** 2))
    au = r["up"]["asks"][0][0] if r["up"]["asks"] else None
    ad = r["down"]["asks"][0][0] if r["down"]["asks"] else None
    bu = r["up"]["bids"][0][0] if r["up"]["bids"] else None
    rows.append((st, tau, up, fu, au, ad, bu))
W = sorted({r[0] for r in rows})
print(f"windows with outcome: {len(W)}  seconds: {len(rows)}")
# 1) calibration of the book mid and of the model, per window-second (clustered by window)
def brier(pred, y): return np.mean((np.array(pred) - np.array(y)) ** 2)
for lo, hi in ((0, 120), (120, 240), (240, 270), (270, 300)):
    sel = [r for r in rows if lo <= r[1] < hi and r[4] and r[6]]
    mid = [(r[4] + r[6]) / 2 for r in sel]; y = [r[2] for r in sel]
    print(f"tau {lo:3d}-{hi:3d}: n={len(sel):5d} brier book-mid {brier(mid, y):.4f}  model {brier([r[3] for r in sel], y):.4f}")
# 2) taker strategy: first qualifying entry per side per window
for thr in (0.02, 0.04, 0.08):
    for lo, hi in ((0, 240), (240, 300), (0, 300)):
        res = []; done = set()
        for st, tau, up, fu, au, ad, bu in rows:
            if not (lo <= tau < hi): continue
            for side, ask, f in (("u", au, fu), ("d", ad, 1 - fu)):
                if ask is None or ask > 0.97 or (st, side) in done: continue
                if f - ask - taker_fee(ask, 1) >= thr:
                    done.add((st, side)); win = up if side == "u" else not up
                    res.append((st, (1 if win else 0) - ask - taker_fee(ask, 1), ask))
        if not res: print(f"thr {thr} tau {lo}-{hi}: no trades"); continue
        a = np.array([(x[1], x[2]) for x in res])
        # window-clustered t-stat
        byw = {}
        for st_, pl, _ in res: byw[st_] = byw.get(st_, 0) + pl
        v = np.array(list(byw.values())); t = v.mean() / (v.std() / math.sqrt(len(v))) if len(v) > 1 and v.std() > 0 else 0
        print(f"thr {thr:.2f} tau {lo:3d}-{hi:3d}: entries {len(a):4d} windows {len(v):3d} pnl/share-sum {a[:,0].sum():+7.2f} ROI {a[:,0].sum()/a[:,1].sum():+6.1%} win% {np.mean(a[:,0]>0):.2f} t(clustered) {t:+.1f}")
