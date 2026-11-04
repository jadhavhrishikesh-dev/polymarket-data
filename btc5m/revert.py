"""Is there short-term overreaction? Regress (win - price) of real fills on the recent BTC move toward that side."""
import numpy as np, math
from feat import P, sig_at, t0, px
from load import markets, trades
ms = [m for m in markets() if m["start"] - 1000 >= t0 and m["start"] + 301 - t0 <= len(px)]
mid = sorted(m["start"] for m in ms)[len(ms) // 2]
for W in (5, 10, 20, 30):
    for lo, hi in ((0, 240), (240, 300)):
        res = {0: [], 1: []}
        for m in ms:
            s = m["start"]; up = m["outcome_prices"][0] in ("1", "1.0"); sig = sig_at(s); last = -99
            for ts, side, oi, p, size in trades(s):
                tau = ts - s
                if side != "BUY" or not (lo <= tau < hi) or not (0.1 <= p <= 0.9) or ts - last < 15: continue
                last = ts
                mv = (P(ts - 3) - P(ts - 3 - W)) / (sig * math.sqrt(W))  # z-score of recent move, ending ~before the true match
                mv = mv if oi == 0 else -mv
                win = up if oi == 0 else not up
                res[int(s >= mid)].append((mv, win - p))
        line = f"move window {W:2d}s tau {lo}-{hi}"
        for h in (0, 1):
            a = np.array(res[h]); x, y = a[:, 0], a[:, 1]
            b = np.polyfit(x, y, 1)[0]; se = y.std() / (x.std() * math.sqrt(len(x)))
            big = x < -1.5
            line += f" | H{h+1} n={len(a)} slope {b:+.4f} (t={b/se:+.1f}) after big adverse move: mean(win-px) {y[big].mean():+.3f} n={big.sum()}"
        print(line, flush=True)
