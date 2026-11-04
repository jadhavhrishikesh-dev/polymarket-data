import pickle, numpy as np
from model import taker_fee
S = pickle.load(open("/tmp/claude-0/snap.pkl", "rb"))
starts = sorted({r["s"] for r in S}); mid = starts[len(starts)//2]
def run(lo, hi, thr, half=None, one=True, pmax=0.97):
    taken = set(); res = []
    for r in S:
        if not (lo <= r["tau"] < hi): continue
        if half == 0 and r["s"] >= mid: continue
        if half == 1 and r["s"] < mid: continue
        if one and r["s"] in taken: continue
        for side, ask, f in (("u", r["ask_u"], r["pu"]), ("d", r["ask_d"], 1 - r["pu"])):
            if ask is None or ask > pmax: continue
            e = f - ask - taker_fee(ask, 1)
            if e >= thr:
                win = r["up"] if side == "u" else not r["up"]
                res.append((win - ask - taker_fee(ask, 1), ask)); taken.add(r["s"]); break
    a = np.array(res) if res else np.zeros((0, 2))
    n = len(a); pnl = a[:, 0].sum() if n else 0; st = a[:, 1].sum() if n else 0
    se = a[:, 0].std() * np.sqrt(n) if n > 1 else 0
    return n, pnl, st, se
if __name__ == "__main__":
    print("per-share PnL, one entry per market; ROI on stake; t = pnl/se")
    for lo, hi in [(0, 30), (30, 120), (120, 200), (200, 240), (240, 270), (270, 290), (290, 300)]:
        for thr in (0.03, 0.08):
            line = f"tau {lo:3d}-{hi:3d} thr {thr:.2f}"
            for h in (0, 1, None):
                n, p, st, se = run(lo, hi, thr, h)
                line += f" | {'H1' if h==0 else 'H2' if h==1 else 'ALL'} n={n:3d} ROI {p/st if st else 0:+6.1%} t={p/se if se else 0:+.1f}"
            print(line)
