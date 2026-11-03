"""Strategy profile for one wallet. Usage: python profile.py <repo_dir> <wallet>"""
import json, os, sys, collections, re
import numpy as np, pandas as pd

R, WAL = sys.argv[1], sys.argv[2].lower()
W = f"{R}/data/{WAL}"
L = lambda n: json.load(open(f"{W}/{n}.json")) if os.path.exists(f"{W}/{n}.json") else []
pos = sum([L(n) for n in ["positions_closed", "positions_open", "positions_redeemable", "positions_redeemable_lost"]], [])
tr = pd.DataFrame(L("trades")); ac = pd.DataFrame(L("activity")); tk = L("trades_taker")
stats = L("user_stats") or {}; vol = L("user_volume") or {}; val = L("value") or {}

def cat(t):
    t = t.lower()
    if "up or down" in t: return "crypto up/down"
    if re.search(r"bitcoin|ethereum|solana|xrp|dogecoin|hyperliquid|\bbtc\b|\beth\b", t): return "crypto price"
    if re.search(r"wti|crude|gold|silver|xau|xag", t): return "commodities"
    if re.search(r"\bvs\.?\b|both teams|o/u|spread:|win the|nba|nfl|mlb|nhl|ufc|premier league|la liga|champions|grand prix|open\b|cup|series|match|game \d|map \d|set \d", t): return "sports"
    if re.search(r"election|president|senate|house|governor|mayor|trump|republican|democrat|prime minister|parliament|vote|nominee", t): return "politics"
    if re.search(r"fed |interest rate|cpi|inflation|gdp|jobs report|unemployment|recession|tariff", t): return "macro"
    if re.search(r"largest company|valuation|ipo|stock|nvidia|apple|tesla|openai", t): return "companies"
    return "other"

out = {}
ap = stats.get("all_time_pnl") or {}
out["name"] = tr.name.iloc[0] if len(tr) and "name" in tr else ""
out["realized_pnl"] = ap.get("realized_pnl"); out["unrealized_pnl"] = ap.get("unrealized_pnl")
out["rebates_rewards"] = sum(ap.get(k) or 0 for k in ["maker_rebate", "taker_rebate", "reward_income", "yield_income"])
out["maker_rebate"] = ap.get("maker_rebate"); out["taker_rebate"] = ap.get("taker_rebate")
out["portfolio_value"] = val.get("value"); out["volume_usdc"] = vol.get("volume_usdc"); out["trades"] = len(tr)
if len(tr):
    tr["usd"] = tr["size"] * tr["price"]; tr["cat"] = tr.title.map(cat)
    tr["dt"] = pd.to_datetime(tr.timestamp, unit="s", utc=True)
    out["first"], out["last"] = str(tr.dt.min())[:10], str(tr.dt.max())[:10]
    out["active_days"] = tr.dt.dt.date.nunique()
    out["fills_per_day"] = round(len(tr) / max(out["active_days"], 1))
    out["sell_share_usd"] = round(tr[tr.side == "SELL"].usd.sum() / tr.usd.sum(), 3)
    out["fill_usd_median"] = round(tr.usd.median(), 1); out["fill_usd_p90"] = round(tr.usd.quantile(.9), 1)
    out["volume_by_cat"] = (tr.groupby("cat").usd.sum() / tr.usd.sum()).round(3).sort_values(ascending=False).to_dict()
    out["peak_utc_hours"] = tr.dt.dt.hour.value_counts().head(4).index.tolist()
    out["fill_price_buckets_usd"] = (tr.groupby(pd.cut(tr.price, [0, .1, .3, .5, .7, .9, 1]), observed=True).usd.sum() / tr.usd.sum()).round(3).rename(index=str).to_dict()
    if tk is not None:
        key = set((t["transaction_hash"], t["token_id"], round(t["size"], 4)) for t in tk)
        tr["taker"] = [(h, a, round(s, 4)) in key for h, a, s in zip(tr.transaction_hash, tr.token_id, tr["size"])]
        out["taker_fill_share"] = round(tr.taker.mean(), 3); out["taker_usd_share"] = round(tr[tr.taker].usd.sum() / tr.usd.sum(), 3)
    # holding span per market
    g = tr.groupby("condition_id").timestamp
    out["markets"] = int(g.ngroups); out["median_trade_span_hrs"] = round(((g.max() - g.min()) / 3600).median(), 1)
    sides = tr.groupby("condition_id").outcome_index.nunique()
    out["both_sides_share"] = round((sides == 2).mean(), 3)
    # time to market end at fill
    ends = {p["condition_id"]: p.get("end_date") for p in pos if p.get("end_date")}
    e = pd.to_datetime(tr.condition_id.map(ends), utc=True, errors="coerce")
    hl = ((e - tr.dt).dt.total_seconds() / 3600)
    out["hours_to_end_median_usdw"] = round(float(np.nanmedian(np.repeat(hl.values, np.clip((tr.usd.values / 10).astype(int), 1, 50)))), 1) if hl.notna().any() else None
if len(ac):
    out["activity_types"] = ac.type.value_counts().to_dict()
    for t in ["MERGE", "REDEEM", "SPLIT", "CONVERSION"]:
        out[f"{t.lower()}_usdc"] = round(ac[ac.type == t].usdc_size.sum()) if "usdc_size" in ac else None
# closed positions
cl = pd.DataFrame([p for p in pos if p["status"] == "CLOSED"])
if len(cl):
    cl["cat"] = cl.title.map(cat)
    out["closed_positions"] = len(cl); out["win_rate"] = round((cl.realized_pnl > 0).mean(), 3)
    s = cl.realized_pnl.sort_values(ascending=False)
    out["top10_share_of_pnl"] = round(s.head(10).sum() / s.sum(), 3) if s.sum() else None
    out["biggest_win"] = round(s.iloc[0]); out["biggest_loss"] = round(s.iloc[-1])
    out["pnl_by_cat"] = cl.groupby("cat").realized_pnl.sum().round().sort_values(ascending=False).to_dict()
    out["winrate_by_cat"] = cl.groupby("cat").realized_pnl.apply(lambda x: round((x > 0).mean(), 3)).to_dict()
    b = cl.groupby(pd.cut(cl.avg_price, [0, .1, .3, .5, .7, .9, 1]), observed=True)
    out["pnl_by_entry_price"] = {str(k): [int(len(v)), round((v.realized_pnl > 0).mean(), 3), round(v.realized_pnl.sum())] for k, v in b}
    out["top_wins"] = [f"{r.realized_pnl:,.0f} @ {r.avg_price:.2f} {r.title[:60]} [{r.outcome}]" for r in cl.nlargest(6, "realized_pnl").itertuples()]
    out["top_losses"] = [f"{r.realized_pnl:,.0f} @ {r.avg_price:.2f} {r.title[:60]} [{r.outcome}]" for r in cl.nsmallest(4, "realized_pnl").itertuples()]
op = [p for p in pos if p["status"] != "CLOSED"]
out["open_positions"] = len(op)
out["top_open"] = [f"{p['current_value']:,.0f} avg {p['avg_price']:.2f} now {p['current_price']:.2f} {p['title'][:55]} [{p['outcome']}]" for p in sorted(op, key=lambda p: -p["current_value"])[:6]]
# markouts with price history
pdir = f"{W}/prices"
if len(tr) and os.path.isdir(pdir):
    H = {}
    for fn in os.listdir(pdir):
        p = json.load(open(f"{pdir}/{fn}"))
        if p: H[fn[:-5]] = pd.DataFrame(p).sort_values("timestamp")
    def at(tok, ts):
        d = H[tok]; i = np.searchsorted(d.timestamp.values, ts, side="right") - 1
        return d.price.values[i] if i >= 0 else np.nan
    m = tr[tr.token_id.isin(H)].copy()
    res = {}
    for h in [1, 24, 72]:
        m[f"mo{h}"] = [(at(a, t + h * 3600) - p) * (1 if s == "BUY" else -1) for a, t, p, s in zip(m.token_id, m.timestamp, m.price, m.side)]
    for grp, x in (m.groupby("taker") if "taker" in m else [("all", m)]):
        res["taker" if grp is True else "maker" if grp is False else grp] = [round(100 * np.nansum(x[c] * x.usd) / x.usd[x[c].notna()].sum(), 2) for c in ["mo1", "mo24", "mo72"]]
    out["markout_cents_1h_24h_72h"] = res; out["markout_coverage_usd"] = round(m.usd.sum() / tr.usd.sum(), 3)
print(json.dumps(out, indent=1, default=str))
