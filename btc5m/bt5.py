"""Taker backtest: buy Up/Down when TWAP fair value exceeds the traded ask by fee + threshold.
Executable prices = prices at which real takers lifted that side (proof an ask existed there)."""
import pickle, numpy as np, sys
from model import taker_fee
rows = pickle.load(open('/tmp/claude-0/rows.pkl', 'rb'))
def run(thr, lo, hi, pmin=0.05, pmax=0.95, max_usd=50, one_per_mkt=True):
    pnl = []; seen = set(); stake = 0
    for s, tau, up_px, lift_up, p, oi, side, size, pu, pn, d, sig, up in rows:
        if not (lo <= tau < hi) or side != 'BUY': continue
        # a taker BUY of outcome oi at price p => ask for that outcome was p
        fair = pu if oi == 0 else 1 - pu
        if not (pmin <= p <= pmax): continue
        edge = fair - p - taker_fee(p, 1)
        if edge < thr: continue
        key = (s, oi)
        if one_per_mkt and key in seen: continue
        seen.add(key)
        sh = min(size, max_usd / p)
        win = up if oi == 0 else (not up)
        pnl.append(sh * ((1.0 if win else 0.0) - p) - taker_fee(p, sh)); stake += sh * p
    pnl = np.array(pnl)
    return len(pnl), pnl.sum(), stake, (pnl > 0).mean() if len(pnl) else 0
if __name__ == '__main__':
    for lo, hi in [(0, 60), (60, 200), (200, 240), (240, 270), (270, 300), (0, 300)]:
        for thr in [0.02, 0.05, 0.10]:
            n, P, st, wr = run(thr, lo, hi)
            print(f"tau {lo:3d}-{hi:3d} thr {thr:.2f}: trades {n:4d} pnl ${P:8.1f} staked ${st:8.0f} ROI {P/st if st else 0:6.1%} winrate {wr:.2f}")
