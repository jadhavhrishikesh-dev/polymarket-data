"""Build per-trade feature table: market price vs TWAP fair value."""
import numpy as np, math
from load import spot, markets, trades
from model import p_up, p_up_spot_naive
t0, px = spot()
def P(t): return px[t - t0]
def twap(a, b): return px[a - t0:b - t0].mean()
ret = np.diff(px)
def sig_at(t, look=900):
    r = ret[t - t0 - look:t - t0]
    return float(np.sqrt(np.mean(r * r)))
BASIS_SD = 4.15  # Binance-vs-Chainlink TWAP-difference noise ($), measured
def build():
    rows = []
    for m in markets():
        s = m["start"]
        if s - 1000 < t0 or s + 301 - t0 > len(px): continue
        up = m["outcome_prices"][0] in ("1", "1.0")
        K = twap(s - 60, s)
        sig = sig_at(s)
        for ts, side, oi, p, size in trades(s):
            tau = ts - s
            if tau < 0 or tau >= 300: continue
            x = P(ts - 1)  # last completed second (no look-ahead)
            A = twap(s + 240, ts) if tau > 240 else None
            # add basis noise to variance via effective sigma inflation
            pu = p_up(tau, x, K, sig, A)
            # inflate: combine model sd with basis sd
            if tau <= 240: sd = sig * math.sqrt(260 - tau)
            else: sd = sig * math.sqrt((300 - tau) ** 3 / 3) / 60
            mu = (x if tau <= 240 else ((tau - 240) * A + (300 - tau) * x) / 60)
            pu_b = 0.5 * (1 + math.erf((mu - K) / math.sqrt(2 * (sd ** 2 + BASIS_SD ** 2))))
            pn = p_up_spot_naive(tau, x, K, sig)
            up_px = p if oi == 0 else 1 - p
            # taker buys Up / sells Down => lifting Up ask ; else hitting Up bid
            lift_up = (side == "BUY") == (oi == 0)
            rows.append((s, tau, up_px, lift_up, p, oi, side, size, pu_b, pn, x - K, sig, up))
    return rows
