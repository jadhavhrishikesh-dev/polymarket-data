"""Price every fill against a driftless-GBM model using hourly spot. Output: fills.csv"""
import json, re, math, bisect, csv, sys
from datetime import datetime, timezone, timedelta

R = sys.argv[1]  # repo dir
W = f"{R}/data/0xa19cbababc312f9df185e49d7004c249ed1ade6b"
L = lambda p: json.load(open(p))
tr = L(f"{W}/trades.json")
pos = []
for n in ["positions_closed", "positions_open", "positions_redeemable", "positions_redeemable_lost"]:
    pos += L(f"{W}/{n}.json")
tok_price = {p["token_id"]: p["current_price"] for p in pos}
tok_end = {p["token_id"]: p.get("end_date") for p in pos}
for p in pos:  # opposite tokens resolve to the complement
    if p.get("opposite_token_id") and p["opposite_token_id"] not in tok_price:
        tok_price[p["opposite_token_id"]] = 1 - p["current_price"]

spot = {}
for s in ["BTC", "ETH", "SOL", "WTI"]:
    rows = sorted(L(f"{R}/data/_spot/{s}.json"))
    spot[s] = rows
TS = {s: [r[0] for r in v] for s, v in spot.items()}
COIN = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "wti": "WTI"}
MON = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
ET = 4  # hours UTC offset for ET (EDT); approximate

def d(m, day, h=0):
    return datetime(2026, MON[m.lower()], int(day), tzinfo=timezone.utc) + timedelta(hours=h)

def num(x):
    x = x.replace(",", "").replace("$", "")
    return float(x[:-1]) * 1000 if x.lower().endswith("k") else float(x)

def parse(title):
    t = title
    asset = next((v for k, v in COIN.items() if k in t.lower()), None)
    if not asset: return None
    m = re.search(r"\$([\d,\.]+k?)", t)
    if not m: return None
    K = num(m.group(1))
    tl = t.lower()
    M = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
    if "between" in tl or "up or down" in tl: return None
    # digital at expiry
    g = re.search(r"(above|greater than|less than|closes above) \$[\d,\.k]+ on " + M + r" (\d+)", tl)
    if g:
        hour = 18.5 if asset == "WTI" else 12 + ET
        return dict(asset=asset, K=K, kind="digital", dir="below" if g.group(1) == "less than" else "above",
                    start=None, end=d(g.group(2), g.group(3), hour))
    up = ("reach" in tl or "(high)" in tl or (" hit $" in tl))
    dn = ("dip to" in tl or "(low)" in tl)
    if not (up or dn): return None
    dirn = "up" if up and not dn else "down"
    if (g := re.search(r"on " + M + r" (\d+)", tl)):
        s = d(g.group(1), g.group(2), ET); return dict(asset=asset, K=K, kind="touch", dir=dirn, start=s, end=s + timedelta(days=1))
    if (g := re.search(M + r" (\d+)-" + M + r" (\d+)", tl)):
        return dict(asset=asset, K=K, kind="touch", dir=dirn, start=d(g.group(1), g.group(2), ET), end=d(g.group(3), g.group(4), ET) + timedelta(days=1))
    if (g := re.search(M + r" (\d+)-(\d+)", tl)):
        return dict(asset=asset, K=K, kind="touch", dir=dirn, start=d(g.group(1), g.group(2), ET), end=d(g.group(1), g.group(3), ET) + timedelta(days=1))
    if (g := re.search(r"week of " + M + r" (\d+)", tl)):
        s = d(g.group(1), g.group(2), ET); return dict(asset=asset, K=K, kind="touch", dir=dirn, start=s, end=s + timedelta(days=5))
    if (g := re.search(r"in " + M, tl)):
        mo = MON[g.group(1)]; s = datetime(2026, mo, 1, ET, tzinfo=timezone.utc)
        e = datetime(2026 + (mo == 12), mo % 12 + 1, 1, ET, tzinfo=timezone.utc)
        return dict(asset=asset, K=K, kind="touch", dir=dirn, start=s, end=e)
    if (g := re.search(r"by " + M + r" (\d+)", tl)):
        return dict(asset=asset, K=K, kind="touch", dir=dirn, start=None, end=d(g.group(1), g.group(2), ET) + timedelta(days=1))
    return None

N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
vol_cache = {}

def vol_per_hour(asset, ts, days=14):
    """Realized vol per sqrt(calendar hour), trailing window."""
    key = (asset, ts // 3600)
    if key in vol_cache: return vol_cache[key]
    i = bisect.bisect_right(TS[asset], ts)
    j = bisect.bisect_left(TS[asset], ts - days * 86400)
    rows = spot[asset][j:i]
    if len(rows) < 20: return None
    r = [math.log(rows[k][4] / rows[k - 1][4]) for k in range(1, len(rows))]
    var = sum(x * x for x in r)  # total variance over the window
    span = (rows[-1][0] - rows[0][0]) / 3600
    v = math.sqrt(var / span)
    vol_cache[key] = v
    return v

def spot_at(asset, ts):
    i = bisect.bisect_right(TS[asset], ts) - 1
    return spot[asset][i][4] if i >= 0 else None

def extreme(asset, a, b):
    i, j = bisect.bisect_left(TS[asset], a), bisect.bisect_right(TS[asset], b)
    rows = spot[asset][i:j]
    if not rows: return None, None
    return max(r[2] for r in rows), min(r[3] for r in rows)

def fair_yes(m, ts):
    S = spot_at(m["asset"], ts); v = vol_per_hour(m["asset"], ts)
    if not S or not v: return None, S, v, None
    end = m["end"].timestamp()
    T = (end - ts) / 3600
    if T <= 0: return None, S, v, T
    if m["kind"] == "digital":
        sd = v * math.sqrt(T); z = (math.log(S / m["K"]) - sd * sd / 2) / sd
        p = N(z) if m["dir"] == "above" else 1 - N(z)
        return p, S, v, T
    start = m["start"].timestamp() if m["start"] else ts
    if start <= ts and m["start"]:
        hi, lo = extreme(m["asset"], start, ts)
        if hi is not None and ((m["dir"] == "up" and hi >= m["K"]) or (m["dir"] == "down" and lo <= m["K"])):
            return 1.0, S, v, T
    Teff = (end - max(ts, start)) / 3600
    sd = v * math.sqrt(T)
    x = abs(math.log(m["K"] / S))
    if (m["dir"] == "up" and S >= m["K"]) or (m["dir"] == "down" and S <= m["K"]):
        return 1.0, S, v, T
    p = min(1.0, 2 * N(-x / sd))
    if start > ts:  # window not open yet: rough haircut
        p = min(p, 2 * N(-x / (v * math.sqrt(Teff))))
    return p, S, v, T

out = []
skip = 0
for t in tr:
    m = parse(t["title"])
    if not m: skip += 1; continue
    p, S, v, T = fair_yes(m, t["timestamp"])
    if p is None: skip += 1; continue
    yes = t["outcome"].lower() in ("yes",)
    fair = p if yes else 1 - p
    res = tok_price.get(t["token_id"])
    resolved = res is not None and m["end"].timestamp() < 1793700000 and (res >= 0.99 or res <= 0.01)
    out.append(dict(ts=t["timestamp"], asset=m["asset"], kind=m["kind"], dir=m["dir"], K=m["K"], S=S,
                    dist=math.log(m["K"] / S), hours_left=T, vol_ann=v * math.sqrt(24 * 365),
                    outcome=t["outcome"], price=t["price"], size=t["size"], usd=t["size"] * t["price"],
                    fair=fair, edge=fair - t["price"], won=(1 if res >= 0.99 else 0) if resolved else "",
                    cond=t["condition_id"], token=t["token_id"], title=t["title"]))
with open("/home/claude/analysis/fills.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print("priced fills", len(out), "skipped", skip, "resolved", sum(1 for o in out if o["won"] != ""))
