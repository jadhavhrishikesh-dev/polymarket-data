import json, glob, os, numpy as np
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "_btc5m")
def spot():
    rows = []
    for f in sorted(glob.glob(f"{D}/spot_1s/*.json")): rows += json.load(open(f))
    a = np.array(rows); ts = (a[:,0]//1000).astype(int)
    t0 = ts[0]; px = np.full(ts[-1]-t0+1, np.nan); px[ts-t0] = a[:,4]
    # forward fill gaps
    m = np.isnan(px); idx = np.where(~m, np.arange(len(px)), 0); np.maximum.accumulate(idx, out=idx)
    return t0, px[idx]
def markets():
    ms = [json.loads(l) for l in open(f"{D}/markets.jsonl")]
    return [m for m in ms if m.get("price_to_beat") and m.get("final_price")]
def trades(start):
    f = f"{D}/trades/{start}.json"
    return json.load(open(f)) if os.path.exists(f) else []
