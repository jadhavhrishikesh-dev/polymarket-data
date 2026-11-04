"""Live book vs model: which pricing rule do market makers follow, and does model-vs-mid gap predict the next move?"""
import json, glob, math, numpy as np, sys
sys.path.insert(0, "btc5m")
L = [json.loads(l) for l in open(sorted(glob.glob("data/_btc5m/live/*.jsonl"))[0])]
T = [r for r in L if r["type"] == "tick" and r.get("up") and r.get("spot") and r["up"]["bids"] and r["up"]["asks"]]
g = {}
for r in T:
    g[int(round(r["t"]))] = r
secs = sorted(g); lo, hi = secs[0], secs[-1]
spot = {}
last = None
for s in range(lo, hi + 1):
    if s in g: last = sum(g[s]["spot"]) / 2
    spot[s] = last
rets = np.diff([spot[s] for s in range(lo, hi + 1)])
SIG = float(np.sqrt(np.mean(rets ** 2))); BASIS = 4.15
print("live sigma $/sqrt(s)", round(SIG, 2))
def N(z): return 0.5 * (1 + math.erf(z / math.sqrt(2)))
rows = []
for s in secs:
    r = g[s]; st = r["start"]; tau = s - st
    if st - 60 < lo or tau < 0: continue
    K = np.mean([spot[q] for q in range(st - 60, st)]); x = spot[s - 1] if (s - 1) in spot else spot[s]
    if tau <= 240: mu, sd = x, SIG * math.sqrt(260 - tau)
    else:
        A = np.mean([spot[q] for q in range(st + 240, s)]); mu = ((tau - 240) * A + (300 - tau) * x) / 60
        sd = SIG * math.sqrt((300 - tau) ** 3 / 3) / 60
    twap = N((mu - K) / math.sqrt(sd ** 2 + BASIS ** 2))
    naive = N((x - K) / (SIG * math.sqrt(max(300 - tau, 1))))
    mid = (r["up"]["bids"][0][0] + r["up"]["asks"][0][0]) / 2
    rows.append((s, st, tau, mid, twap, naive, r["up"]["asks"][0][0], r["down"]["asks"][0][0] if r["down"]["asks"] else None))
a = np.array([x[:7] for x in rows], float)
s, st, tau, mid, tw, nv, ask = a.T
for lo_, hi_ in ((0, 120), (120, 240), (240, 300)):
    m = (tau >= lo_) & (tau < hi_) & (mid > 0.03) & (mid < 0.97)
    print(f"tau {lo_}-{hi_}: n={m.sum()} mean|mid-twap| {np.mean(abs(mid[m]-tw[m])):.3f}  mean|mid-naive| {np.mean(abs(mid[m]-nv[m])):.3f}")
# does the gap predict the next move?
idx = {int(x): i for i, x in enumerate(s)}
for h in (5, 15, 30):
    gx, gy = [], []
    for i in range(len(s)):
        j = idx.get(int(s[i]) + h)
        if j is None or st[j] != st[i] or not (0.05 < mid[i] < 0.95): continue
        gx.append(tw[i] - mid[i]); gy.append(mid[j] - mid[i])
    gx, gy = np.array(gx), np.array(gy)
    b = np.polyfit(gx, gy, 1)[0]
    print(f"horizon {h:2d}s: corr(gap, future mid change) {np.corrcoef(gx, gy)[0,1]:+.3f}  slope {b:+.2f}  n={len(gx)}  ticks with |gap|>0.05: {np.mean(abs(gx)>0.05):.2f}")
