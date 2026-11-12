"""Reverse-engineer a wallet that trades the 'Up or Down' crypto markets.
Usage: python mo_money.py <repo_dir> <wallet>
Rebuilds profit per market from trades + redeem/merge activity, and profiles timing, pairing and sizing."""
import json, re, sys
import numpy as np, pandas as pd

R, WAL = sys.argv[1], sys.argv[2].lower()
D = f"{R}/data/{WAL}/"
t = pd.DataFrame(json.load(open(D + "trades.json")))
a = pd.DataFrame(json.load(open(D + "activity.json")))
t["usd"] = t["size"] * t.price
m = t.slug.str.extract(r"^([a-z]+)-updown-(\w+?)-(\d+)$")
t["asset"], t["dur"], t["start"] = m[0], m[1], pd.to_numeric(m[2])
t = t[t.start.notna()].copy()
secs = t.dur.map(lambda x: {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}.get(x))
t["win"] = secs.astype(float)
t["off"] = t.timestamp - t.start                 # seconds since window opened
t["frac"] = t.off / t.win
out = {}
out["trades_used"] = len(t)
out["volume_by_asset"] = (t.groupby("asset").usd.sum() / t.usd.sum()).round(3).sort_values(ascending=False).to_dict()
out["volume_by_duration"] = (t.groupby("dur").usd.sum() / t.usd.sum()).round(3).sort_values(ascending=False).to_dict()
out["fill_size_shares_quantiles"] = t["size"].quantile([.1, .25, .5, .75, .9, .99]).round(1).to_dict()
out["fills_at_exact_size_share"] = {str(k): round(v, 3) for k, v in t["size"].round(0).value_counts(normalize=True).head(5).items()}

# --- per-market ledger (only markets fully inside the window where activity is complete) ---
a_start = a.timestamp.min()
last_ts = t.timestamp.max()
led = t[t.timestamp >= a_start].groupby("condition_id").agg(
    start=("start", "first"), win=("win", "first"), dur=("dur", "first"), asset=("asset", "first"),
    n=("usd", "size"), cost=("usd", "sum"), first=("timestamp", "min"), last=("timestamp", "max"))
for oi, nm in [(0, "Up"), (1, "Down")]:
    s = t[(t.timestamp >= a_start) & (t.outcome_index == oi)].groupby("condition_id").agg(**{f"q{nm}": ("size", "sum"), f"c{nm}": ("usd", "sum")})
    led = led.join(s)
led = led.fillna({"qUp": 0, "qDown": 0, "cUp": 0, "cDown": 0})
for ty in ["REDEEM", "MERGE"]:
    s = a[a.type == ty].groupby("condition_id").usdc_size.sum().rename({"MERGE": "merged", "REDEEM": "redeemed"}[ty])
    led = led.join(s)
led = led.fillna({"redeemed": 0, "merged": 0})
led["end"] = led.start + led.win
led = led[(led.start * 1.0 >= a_start) & (led.end < last_ts - 1800)]       # settled, fully observed
led["net"] = led.redeemed + led.merged - led.cost
led["both"] = (led.qUp > 0) & (led.qDown > 0)
led["paired"] = np.minimum(led.qUp, led.qDown)
led["pair_share"] = led.paired / (led.qUp + led.qDown).replace(0, np.nan)
led["pair_cost"] = (led.cUp / led.qUp.replace(0, np.nan)) + (led.cDown / led.qDown.replace(0, np.nan))
out["markets_in_ledger"] = len(led)
out["ledger_net_usd"] = round(led.net.sum()); out["ledger_cost_usd"] = round(led.cost.sum())
out["ledger_return_on_cost_pct"] = round(100 * led.net.sum() / led.cost.sum(), 2)
out["share_markets_both_sides"] = round(led.both.mean(), 3)
out["net_by_duration"] = led.groupby("dur").agg(markets=("net", "size"), net=("net", "sum"), cost=("cost", "sum")).round(0).assign(roc_pct=lambda x: (100 * x.net / x.cost).round(2)).to_dict("index")
out["net_by_asset"] = led.groupby("asset").agg(markets=("net", "size"), net=("net", "sum"), cost=("cost", "sum")).round(0).assign(roc_pct=lambda x: (100 * x.net / x.cost).round(2)).to_dict("index")
b = led[led.both]
out["both_sides_markets"] = {"n": len(b), "net": round(b.net.sum()), "roc_pct": round(100 * b.net.sum() / b.cost.sum(), 2),
                              "median_pair_cost": round(b.pair_cost.median(), 3), "share_pair_cost_below_1": round((b.pair_cost < 1).mean(), 3),
                              "median_pair_share": round(b.pair_share.median(), 3), "share_with_merge": round((b.merged > 0).mean(), 3)}
o = led[~led.both]
out["one_side_markets"] = {"n": len(o), "net": round(o.net.sum()), "roc_pct": round(100 * o.net.sum() / o.cost.sum(), 2) if len(o) else None, "win_rate": round((o.net > 0).mean(), 3) if len(o) else None}
out["market_net_quantiles"] = led.net.quantile([.05, .25, .5, .75, .95]).round(1).to_dict()
out["share_markets_profitable"] = round((led.net > 0).mean(), 3)
# pair-cost buckets: does a lower pair cost earn more?
bb = b.dropna(subset=["pair_cost"]).copy()
bb["pcb"] = pd.cut(bb.pair_cost, [0, .8, .9, .95, 1.0, 1.05, 3])
out["pair_cost_buckets"] = bb.groupby("pcb", observed=True).agg(n=("net", "size"), net=("net", "sum"), cost=("cost", "sum")).round(0).assign(roc_pct=lambda x: (100 * x.net / x.cost).round(2)).rename(index=str).to_dict("index")
# --- timing ---
tt = t[t.dur.isin(["5m", "15m"])]
for d_ in ["5m", "15m"]:
    x = tt[tt.dur == d_]
    if len(x):
        out[f"timing_{d_}"] = {"usd_share_first_10pct_of_window": round(x[x.frac < .1].usd.sum() / x.usd.sum(), 3),
                               "usd_share_last_20pct": round(x[x.frac >= .8].usd.sum() / x.usd.sum(), 3),
                               "usd_share_after_window_start": round(x[x.off >= 0].usd.sum() / x.usd.sum(), 3),
                               "usd_share_before_window_start": round(x[x.off < 0].usd.sum() / x.usd.sum(), 3),
                               "median_frac": round(float(x.frac.median()), 3),
                               "usd_by_decile": (x.groupby(pd.cut(x.frac.clip(-.0001, .9999), np.linspace(0, 1, 11), include_lowest=True), observed=True).usd.sum() / x.usd.sum()).round(3).tolist()}
        out[f"price_by_timing_{d_}"] = x.groupby(pd.cut(x.frac.clip(-.0001, .9999), [0, .25, .5, .75, 1], include_lowest=True), observed=True).price.mean().round(3).tolist()
out["fills_per_market_median"] = float(led.n.median()); out["fills_per_market_p90"] = float(led.n.quantile(.9))
tt2 = t.copy(); tt2["hr"] = pd.to_datetime(tt2.timestamp, unit="s", utc=True).dt.hour
out["usd_by_utc_hour"] = (tt2.groupby("hr").usd.sum() / tt2.usd.sum()).round(3).to_dict()
tt2["day"] = pd.to_datetime(tt2.timestamp, unit="s", utc=True).dt.strftime("%m-%d")
out["usd_by_day"] = tt2.groupby("day").usd.sum().round(0).to_dict()
# concurrency: markets traded per minute
tt2["min"] = tt2.timestamp // 60
out["markets_per_active_minute_median"] = float(tt2.groupby("min").condition_id.nunique().median())

# --- decomposition: locked pair spread vs leftover directional inventory ---
b = led[led.both].dropna(subset=["pair_cost"]).copy()
b["locked"] = b.paired * (1 - b.pair_cost)
b["resid"] = b.net - b.locked
out["decomposition_both_sided"] = {"locked_pair_spread_usd": round(b.locked.sum()), "leftover_directional_usd": round(b.resid.sum()), "total_net_usd": round(b.net.sum()),
    "paired_shares": round(b.paired.sum()), "avg_locked_cents_per_pair": round(100 * b.locked.sum() / b.paired.sum(), 2)}
# --- stability by day (market end day, UTC) and concentration ---
led["day"] = pd.to_datetime(led.end, unit="s", utc=True).dt.strftime("%m-%d")
dd = led.groupby("day").agg(markets=("net", "size"), net=("net", "sum"), cost=("cost", "sum")).round(0)
dd["roc_pct"] = (100 * dd.net / dd.cost).round(2)
out["daily"] = dd.to_dict("index")
ns = led.net.sort_values(ascending=False)
out["top1pct_markets_net_share"] = round(ns.head(max(1, len(ns) // 100)).sum() / led.net.sum(), 2)
out["worst1pct_markets_net"] = round(ns.tail(max(1, len(ns) // 100)).sum())
# --- order of legs in two-sided markets ---
f = t[t.timestamp >= a_start].sort_values("timestamp")
fs = f.groupby(["condition_id", "outcome_index"]).agg(ft=("timestamp", "min"), fp=("price", "first")).reset_index()
pv = fs.pivot(index="condition_id", columns="outcome_index", values=["ft", "fp"]).dropna()
lag = (pv[("ft", 1)] - pv[("ft", 0)]).abs()
out["leg_lag_seconds_median_p90"] = [float(lag.median()), float(lag.quantile(.9))]
first_leg_price = np.where(pv[("ft", 0)] <= pv[("ft", 1)], pv[("fp", 0)], pv[("fp", 1)])
second_leg_price = np.where(pv[("ft", 0)] <= pv[("ft", 1)], pv[("fp", 1)], pv[("fp", 0)])
out["first_leg_price_median"] = round(float(np.median(first_leg_price)), 3); out["second_leg_price_median"] = round(float(np.median(second_leg_price)), 3)
# --- cross-check against Polymarket's own realised PnL over the last 24h ---
pn = json.load(open(D + "user_pnl.json"))["points"]
t0, t1 = pn[0]["timestamp"], pn[-1]["timestamp"]
win_ = led[(led.end >= t0) & (led.end <= t1)]
out["crosscheck_last24h"] = {"polymarket_realised_change": round(pn[-1]["realized_pnl"] - pn[0]["realized_pnl"]), "my_ledger_net_same_window": round(win_.net.sum()), "markets": len(win_)}
print(json.dumps(out, indent=1, default=str))
