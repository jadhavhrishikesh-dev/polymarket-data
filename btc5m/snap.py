"""Per-market snapshots at fixed times: best recent executable ask for Up and Down (from taker buys
in the previous LOOK seconds), TWAP fair value, outcome. Equal weight per market."""
import numpy as np, math, pickle
from feat import P, twap, sig_at, t0, px, BASIS_SD
from load import markets, trades
LOOK = 3
DELAY = 1
def fair(s, tau, sig):
    K = twap(s - 60, s); x = P(s + tau - 1)
    if tau <= 240: mu, sd = x, sig * math.sqrt(260 - tau)
    else:
        A = twap(s + 240, s + tau); mu = ((tau - 240) * A + (300 - tau) * x) / 60
        sd = sig * math.sqrt((300 - tau) ** 3 / 3) / 60
    return 0.5 * (1 + math.erf((mu - K) / math.sqrt(2 * (sd ** 2 + BASIS_SD ** 2)))), x - K
def build(taus=range(5, 300, 5)):
    out = []
    for m in markets():
        s = m["start"]
        if s - 1000 < t0 or s + 301 - t0 > len(px): continue
        up = m["outcome_prices"][0] in ("1", "1.0"); sig = sig_at(s)
        tr = [t for t in trades(s) if t[1] == "BUY"]
        for tau in taus:
            t = s + tau
            # decision at t uses spot up to t-1; execution = FIRST real taker buy at/after t+DELAY (no look-ahead, no cherry-pick)
            w = sorted((x for x in tr if t + DELAY <= x[0] < t + DELAY + LOOK), key=lambda x: x[0])
            ask_u = next((x[3] for x in w if x[2] == 0), None)
            ask_d = next((x[3] for x in w if x[2] == 1), None)
            pu, d = fair(s, tau, sig)
            out.append(dict(s=s, tau=tau, up=up, pu=pu, d=d, sig=sig, ask_u=ask_u, ask_d=ask_d))
    return out
if __name__ == "__main__":
    o = build(); pickle.dump(o, open("/tmp/claude-0/snap.pkl", "wb")); print(len(o))
