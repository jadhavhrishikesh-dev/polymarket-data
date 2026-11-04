"""How fast must you be? Take each real taker BUY fill as an available ask at its timestamp ts,
decide using spot known k seconds BEFORE ts. Edge vs k shows how quickly Polymarket catches up with Binance."""
import numpy as np, math
from feat import P, twap, sig_at, t0, px, BASIS_SD
from load import markets, trades
from model import taker_fee
def fair(s, tau, x, sig):
    K = twap(s - 60, s)
    if tau <= 240: mu, sd = x, sig * math.sqrt(260 - tau)
    else:
        A = twap(s + 240, s + tau); mu = ((tau - 240) * A + (300 - tau) * x) / 60
        sd = sig * math.sqrt((300 - tau) ** 3 / 3) / 60
    return 0.5 * (1 + math.erf((mu - K) / math.sqrt(2 * (sd ** 2 + BASIS_SD ** 2))))
ms = [m for m in markets() if m["start"] - 1000 >= t0 and m["start"] + 301 - t0 <= len(px)]
mid = sorted(m["start"] for m in ms)[len(ms) // 2]
for k in (1, 2, 3, 5, 10):
    for lo, hi in ((0, 240), (240, 300)):
        out = {0: [], 1: []}
        for m in ms:
            s = m["start"]; up = m["outcome_prices"][0] in ("1", "1.0"); sig = sig_at(s); last = {}
            for ts, side, oi, p, size in trades(s):
                tau = ts - s
                if side != "BUY" or not (lo <= tau < hi) or tau - k < 1 or p > 0.97: continue
                if ts - last.get(oi, -99) < 10: continue  # at most one entry per side per 10s
                f = fair(s, tau - k + 1, P(ts - k), sig) if tau - k + 1 > 0 else None
                if f is None: continue
                f = f if oi == 0 else 1 - f
                if f - p - taker_fee(p, 1) < 0.05: continue
                last[oi] = ts
                win = up if oi == 0 else not up
                out[int(s >= mid)].append((win - p - taker_fee(p, 1), p))
        line = f"spot age {k:2d}s tau {lo:3d}-{hi:3d}"
        for h in (0, 1):
            a = np.array(out[h]); n = len(a)
            line += f" | H{h+1} n={n:5d} ROI {a[:,0].sum()/a[:,1].sum():+6.1%} t={a[:,0].sum()/(a[:,0].std()*math.sqrt(n)):+.1f}"
        print(line, flush=True)
