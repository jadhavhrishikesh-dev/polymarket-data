"""Full-history study of an Up/Down wallet. Usage: python history.py <repo_dir> <wallet>"""
import json, sys
import numpy as np, pandas as pd
R, WAL = sys.argv[1], sys.argv[2].lower(); D = f"{R}/data/{WAL}/"
a = pd.read_csv(D + "activity.csv.gz"); tk = pd.read_csv(D + "trades.csv.gz")
t = a[a.type == "TRADE"].copy(); t["price"] = t.usdc / t["size"]
# flag taker fills by matching the taker feed on (ts, slug, outcome, size)
k = lambda df: df.ts.astype(str) + "|" + df.slug.astype(str) + "|" + df.outcome_index.astype(str) + "|" + df["size"].round(3).astype(str)
t["taker"] = k(t).isin(set(k(tk[tk.taker == 1])))
m = t.slug.str.extract(r"^([a-z]+)-updown-(\w+?)-(\d+)$")
t["asset"], t["dur"], t["start"] = m[0], m[1], pd.to_numeric(m[2])
t["win"] = t.dur.map({"5m": 300, "15m": 900, "1h": 3600, "4h": 14400})
t["month"] = pd.to_datetime(t.ts, unit="s").dt.strftime("%Y-%m")
out = {"fills": len(t), "first": str(pd.to_datetime(t.ts.min(), unit="s")), "volume": round(t.usdc.sum()),
       "updown_slug_share_usd": round(t[t.start.notna()].usdc.sum() / t.usdc.sum(), 4),
       "other_slugs": t[t.start.isna()].slug.str.replace(r"\d+", "#", regex=True).value_counts().head(6).to_dict(),
       "taker_fill_share": round(t.taker.mean(), 3), "taker_usd_share": round(t[t.taker].usdc.sum() / t.usdc.sum(), 3)}
# ledger per market
g = t.groupby("slug")
led = g.agg(cost=("usdc", "sum"), n=("usdc", "size"), first=("ts", "min"), last=("ts", "max"), asset=("asset", "first"), dur=("dur", "first"), start=("start", "first"), win=("win", "first"))
for oi, nm in [(0, "Up"), (1, "Down")]:
    s = t[t.outcome_index == oi].groupby("slug").agg(**{f"q{nm}": ("size", "sum"), f"c{nm}": ("usdc", "sum")}); led = led.join(s)
led = led.fillna({"qUp": 0, "qDown": 0, "cUp": 0, "cDown": 0})
for ty, nm in [("REDEEM", "redeemed"), ("MERGE", "merged")]:
    led = led.join(a[a.type == ty].groupby("slug").usdc.sum().rename(nm))
led = led.fillna({"redeemed": 0, "merged": 0})
led["net"] = led.redeemed + led.merged - led.cost
led["both"] = (led.qUp > 0) & (led.qDown > 0)
led["paired"] = np.minimum(led.qUp, led.qDown)
led["pair_cost"] = led.cUp / led.qUp.replace(0, np.nan) + led.cDown / led.qDown.replace(0, np.nan)
led["locked"] = (led.paired * (1 - led.pair_cost)).fillna(0)
led["endts"] = (led.start + led.win).fillna(led["last"])
led["month"] = pd.to_datetime(led.endts, unit="s").dt.strftime("%Y-%m")
led["tk_cost"] = t[t.taker].groupby("slug").usdc.sum(); led["tk_cost"] = led.tk_cost.fillna(0)
out["ledger_total_net"] = round(led.net.sum()); out["markets"] = len(led)
# monthly table
pn = json.load(open(D + "user_pnl_max.json")); pts = pn["points"] if isinstance(pn, dict) else pn
ps = pd.DataFrame(pts); ps["month"] = pd.to_datetime(ps.timestamp, unit="s").dt.strftime("%Y-%m")
official = ps.groupby("month").realized_pnl.last().diff().fillna(ps.groupby("month").realized_pnl.last())
mt = led.groupby("month").agg(markets=("net", "size"), cost=("cost", "sum"), net=("net", "sum"), locked=("locked", "sum"), both=("both", "mean"), pair_cost=("pair_cost", "median"), win=("net", lambda x: (x > 0).mean()), tk=("tk_cost", "sum"))
mt["roc_pct"] = 100 * mt.net / mt.cost; mt["taker_usd_pct"] = 100 * mt.tk / mt.cost; mt["official_realised"] = official
tm = t.groupby("month").agg(fills=("usdc", "size"), med_fill_usd=("usdc", "median"), p90_fill_usd=("usdc", lambda x: x.quantile(.9)), days=("ts", lambda x: (x // 86400).nunique()))
tm["fills_per_day"] = tm.fills / tm.days
for col, nm in [("asset", "btc"), ("dur", "5m"), ("dur", "15m")]:
    tm[f"usd_{nm}_pct"] = 100 * t[t[col] == nm].groupby("month").usdc.sum() / t.groupby("month").usdc.sum()
mt = mt.join(tm).drop(columns=["tk", "fills", "days"]).round(2)
out["monthly"] = mt.round(2).to_dict("index")
# bankroll: cumulative cash flow from trading; its lowest point is the least capital that had to be in the account
fl = pd.concat([t[["ts", "usdc"]].assign(v=lambda x: -x.usdc)[["ts", "v"]], a[a.type.isin(["REDEEM", "MERGE", "MAKER_REBATE", "TAKER_REBATE", "REWARD"])][["ts", "usdc"]].rename(columns={"usdc": "v"})]).sort_values("ts")
fl["cum"] = fl.v.cumsum(); fl["day"] = (fl.ts - t.ts.min()) // 86400
out["cash_low_first_days"] = {int(d_): round(v, 2) for d_, v in fl.groupby("day").cum.min().head(10).items()}
out["cash_end_first_days"] = {int(d_): round(v, 2) for d_, v in fl.groupby("day").cum.last().head(10).items()}
out["deepest_cash_low_all_time"] = round(fl.cum.min(), 2)
fl["month"] = pd.to_datetime(fl.ts, unit="s").dt.strftime("%Y-%m")
# capital in use: within each month, the largest dip of cash below its running peak
fl["peak"] = fl.cum.cummax(); fl["dip"] = fl.peak - fl.cum
out["max_capital_tied_up_by_month"] = fl.groupby("month").dip.max().round(0).to_dict()
# first 3 days in detail
e = t[t.ts < t.ts.min() + 3 * 86400]
out["first_3_days"] = {"fills": len(e), "volume": round(e.usdc.sum(), 2), "median_fill_usd": round(e.usdc.median(), 2), "max_fill_usd": round(e.usdc.max(), 2),
                       "by_dur": e.groupby("dur").usdc.sum().round(1).to_dict(), "by_asset": e.groupby("asset").usdc.sum().round(1).to_dict(), "taker_usd_share": round(e[e.taker].usdc.sum() / e.usdc.sum(), 3)}
dl = led.assign(day=pd.to_datetime(led.endts, unit="s").dt.strftime("%Y-%m-%d")).groupby("day").net.sum()
out["days_total"] = len(dl); out["days_profitable"] = int((dl > 0).sum()); out["worst_day"] = [dl.idxmin(), round(dl.min())]; out["best_day"] = [dl.idxmax(), round(dl.max())]
out["first_14_days_net"] = dl.head(14).round(1).to_dict()
# maker vs taker result, timing of taker fills
tt = t[t.start.notna()].copy(); tt["frac"] = (tt.ts - tt.start) / tt.win
out["taker_vs_maker"] = {nm: {"usd": round(x.usdc.sum()), "avg_price": round((x.usdc.sum() / x["size"].sum()), 3), "median_frac_of_window": round(float(x.frac.median()), 2), "median_fill_usd": round(x.usdc.median(), 2)} for nm, x in [("taker", tt[tt.taker]), ("maker", tt[~tt.taker])]}

# --- edge per fill: did the side bought win more often than its price implied? ---
rw = a[(a.type == "REDEEM") & (a.usdc > 0)].groupby("slug").outcome_index.first().rename("winner")
# a winner is only redeemed when the wallet held it, so also infer the winner from leftovers that paid nothing:
# shares left on one side after merges, with no paying redemption, means that side lost
mg = a[a.type == "MERGE"].groupby("slug")["size"].sum().rename("mshares")
lw = led.join(rw).join(mg).fillna({"mshares": 0})
lw["lUp"] = lw.qUp - lw.mshares; lw["lDown"] = lw.qDown - lw.mshares
settled = lw.endts < t.ts.max() - 86400
lost_up = lw.winner.isna() & settled & (lw.lUp > 0.5) & (lw.lDown <= 0.5)
lost_dn = lw.winner.isna() & settled & (lw.lDown > 0.5) & (lw.lUp <= 0.5)
lw.loc[lost_up, "winner"] = 1; lw.loc[lost_dn, "winner"] = 0
out["winner_source_markets"] = {"redeemed": int(rw.shape[0]), "inferred_from_losing_leftover": int(lost_up.sum() + lost_dn.sum()), "unknown": int(lw.winner.isna().sum())}
tt = tt.join(lw.winner, on="slug"); kn = tt[tt.winner.notna()].copy()
kn["won"] = (kn.outcome_index == kn.winner).astype(float); kn["edge"] = kn.won - kn.price
def edge_tbl(x, by):
    g_ = x.groupby(by, observed=True)
    return pd.DataFrame({"usd": g_.usdc.sum().round(0), "avg_price": (g_.usdc.sum() / g_["size"].sum()).round(3),
                         "win_rate_sharew": (g_.apply(lambda v: (v.won * v["size"]).sum() / v["size"].sum())).round(3),
                         "edge_cents_per_share": (g_.apply(lambda v: 100 * (v.edge * v["size"]).sum() / v["size"].sum())).round(2)})
out["winner_known_usd_share"] = round(kn.usdc.sum() / tt.usdc.sum(), 3)
out["edge_by_role"] = edge_tbl(kn.assign(role=np.where(kn.taker, "taker", "maker")), "role").to_dict("index")
out["edge_by_price"] = edge_tbl(kn, pd.cut(kn.price, [0, .2, .4, .5, .6, .8, 1])).rename(index=str).to_dict("index")
out["edge_by_window_part"] = edge_tbl(kn, pd.cut(kn.frac.clip(0, .999), [0, .2, .4, .6, .8, 1], include_lowest=True)).rename(index=str).to_dict("index")
out["edge_by_duration"] = edge_tbl(kn, "dur").to_dict("index")
out["edge_by_asset"] = edge_tbl(kn, "asset").to_dict("index")
out["both_vs_one_sided"] = led.groupby("both").agg(markets=("net", "size"), cost=("cost", "sum"), net=("net", "sum"), locked=("locked", "sum")).round(0).rename(index={True: "both", False: "one"}).to_dict("index")
out["feb_markets"] = t[t.month == "2026-02"].slug.unique().tolist()[:8]
out["net_share_top1pct_markets"] = round(led.net.nlargest(len(led) // 100).sum() / led.net.sum(), 2)
out["median_market_cost_usd"] = round(led.cost.median(), 2); out["p99_market_cost_usd"] = round(led.cost.quantile(.99), 0)
print(json.dumps(out, indent=1, default=str))
