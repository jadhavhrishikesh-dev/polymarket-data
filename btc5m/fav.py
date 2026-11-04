"""Model-free check: buy whichever side trades in a price band late in the window (first such fill per market)."""
import numpy as np, sys
from load import markets, trades
from model import taker_fee
ms = markets(); mid = sorted(m["start"] for m in ms)[len(ms)//2]
def run(lo, hi, plo, phi):
    out = {0: [], 1: []}
    for m in ms:
        s = m["start"]; up = m["outcome_prices"][0] in ("1", "1.0")
        for ts, side, oi, p, size in sorted(trades(s)):
            tau = ts - s
            if side == "BUY" and lo <= tau < hi and plo <= p < phi:
                win = up if oi == 0 else not up
                out[int(s >= mid)].append((win, p)); break
    return out
print("first fill per market in band | win rate vs avg price | ROI after taker fee  (H1 / H2)")
for lo, hi in ((150, 200), (200, 240), (240, 270), (270, 290), (290, 300)):
    for plo, phi in ((0.60, 0.75), (0.75, 0.85), (0.85, 0.92), (0.92, 0.97)):
        o = run(lo, hi, plo, phi); line = f"tau {lo}-{hi} px {plo:.2f}-{phi:.2f}"
        for h in (0, 1):
            a = np.array(o[h], float)
            if len(a) < 5: line += " | n<5"; continue
            w, p = a[:, 0], a[:, 1]; pnl = w - p - taker_fee(p, 1)
            line += f" | n={len(a):3d} win {w.mean():.3f} px {p.mean():.3f} ROI {pnl.sum()/p.sum():+6.1%} t={pnl.mean()/pnl.std()*np.sqrt(len(a)):+.1f}"
        print(line)
