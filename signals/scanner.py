"""Signal scanner: resolution-sniper opportunities and copy-trade alerts.

Writes <out>/signals.json and <out>/state.json, and pushes new signals to an ntfy topic.
Usage: python scanner.py <out_dir> [--no-notify]
"""
import json, os, sys, time, math, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
NOTIFY = "--no-notify" not in sys.argv
GAMMA, CLOB, DATA = "https://gamma-api.polymarket.com", "https://clob.polymarket.com", "https://data-api.polymarket.com/v2"
UA = {"User-Agent": "Mozilla/5.0 pm-signal-scanner", "Accept": "application/json"}
NOW = datetime.now(timezone.utc)
os.makedirs(OUT, exist_ok=True)
log = lambda *a: print(*a, flush=True)


def http(url, params=None, body=None, tries=3):
    if params:
        url += "?" + urllib.parse.urlencode(params, safe=",")
    data = json.dumps(body).encode() if body is not None else None
    headers = dict(UA, **({"Content-Type": "application/json"} if data else {}))
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            log("  HTTP", e.code, url[:120], e.read()[:200])
            if e.code in (400, 404, 410, 422):
                return None
        except Exception as e:
            log("  err", url[:120], repr(e)[:150])
        time.sleep(1.5 * (i + 1))
    return None


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromtimestamp(int(s), timezone.utc)
        except Exception:
            return None


def books(token_ids):
    """Order books for many tokens -> {token_id: (bids, asks)} with float tuples."""
    out = {}
    ids = list(dict.fromkeys(token_ids))
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        res = http(f"{CLOB}/books", body=[{"token_id": t} for t in chunk])
        if res is None:  # fall back to single requests
            res = [http(f"{CLOB}/book", {"token_id": t}) for t in chunk]
        for b in res or []:
            if not b:
                continue
            f = lambda lv: sorted(((float(x["price"]), float(x["size"])) for x in lv), key=lambda x: x[0])
            out[b.get("asset_id")] = (f(b.get("bids") or [])[::-1], f(b.get("asks") or []))
        time.sleep(0.2)
    return out


def taker_fee_per_share(m, p):
    fs = m.get("feeSchedule") or {}
    if not m.get("feesEnabled") or not fs:
        return 0.0
    rate, exp = float(fs.get("rate") or 0), float(fs.get("exponent") or 1)
    return rate * p * (p * (1 - p)) ** exp  # estimate; shown as such in the app


def resolutions(cond_ids):
    out = {}
    for i in range(0, len(cond_ids), 20):
        r = http(f"{DATA}/resolutions", {"condition": ",".join(cond_ids[i:i + 20])})
        for row in (r or {}).get("data") or []:
            out[row.get("condition_id")] = row
        time.sleep(0.2)
    return out


# ---------------------------------------------------------------- sniper
def scan_sniper():
    c = CFG["sniper"]
    lo, hi = c["min_price"], c["max_price"]
    params = {"limit": 100, "closed": "false", "order": "endDate", "ascending": "false",
              "end_date_max": iso(NOW), "end_date_min": iso(NOW - timedelta(days=c["lookback_days"]))}
    markets, cursor = [], None
    for _ in range(c["max_pages"]):
        p = dict(params, **({"after_cursor": cursor} if cursor else {}))
        r = http(f"{GAMMA}/markets/keyset", p)
        if not r:
            break
        markets += r.get("markets") or []
        cursor = r.get("next_cursor")
        if not cursor:
            break
    log(f"sniper: {len(markets)} open markets past end date")
    cands = []
    for m in markets:
        if not m.get("acceptingOrders") or not m.get("enableOrderBook") or m.get("negRiskOther"):
            continue
        try:
            toks, outs = json.loads(m.get("clobTokenIds") or "[]"), json.loads(m.get("outcomes") or "[]")
        except ValueError:
            continue
        if len(toks) != 2:
            continue
        ba, bb = m.get("bestAsk"), m.get("bestBid")
        if ba is not None and lo <= float(ba) <= hi:
            cands.append((m, 0, toks[0], outs[0]))
        if bb is not None and lo <= 1 - float(bb) <= hi:
            cands.append((m, 1, toks[1], outs[1]))
    log(f"sniper: {len(cands)} candidates at {lo}-{hi}")
    bk = books([t for _, _, t, _ in cands])
    res = resolutions(list({m["conditionId"] for m, *_ in cands}))
    sigs = []
    for m, idx, tok, outcome in cands:
        bids, asks = bk.get(tok, ([], []))
        if not asks:
            continue
        ask = asks[0][0]
        if not (lo <= ask <= hi):
            continue
        depth = sum(p * s for p, s in asks if p <= min(ask + 0.002, hi))
        if depth < c["min_depth_usd"]:
            continue
        bid = bids[0][0] if bids else None
        tick = float(m.get("orderPriceMinTickSize") or 0.001)
        maker = round(min(ask - tick, (bid or 0) + tick), 4) if bid and ask - bid > tick + 1e-9 else (bid or ask)
        r = res.get(m["conditionId"]) or {}
        status = r.get("status") or "none"
        if status in c["skip_statuses"]:
            continue
        settle = parse_ts(r.get("expected_settlement_time"))
        end = parse_ts(m.get("endDate"))
        est_days = max((settle - NOW).total_seconds() / 86400, 0) + 0.5 if settle else (1.0 if status == "proposed" else 3.0)
        fee = taker_fee_per_share(m, ask)
        gain_taker = (1 - ask - fee) / ask
        gain_maker = (1 - maker) / maker if maker else 0
        ev = (m.get("events") or [{}])[0]
        reasons = [f"Ended {((NOW - end).total_seconds() / 3600):.0f}h ago" if end else "Past end date",
                   {"proposed": "outcome proposed to oracle", "resolved": "oracle resolved, awaiting settlement",
                    "none": "no oracle proposal yet"}.get(status, f"oracle status: {status}"),
                   f"${depth:,.0f} available at ask"]
        if fee:
            reasons.append(f"taker fee ~{fee * 100:.2f}c/share, maker free")
        sigs.append(dict(
            id=f"snp:{tok}", type="sniper", question=m.get("question"), outcome=outcome, token_id=tok,
            condition_id=m["conditionId"], event_slug=ev.get("slug"), slug=m.get("slug"),
            url=f"https://polymarket.com/event/{ev.get('slug') or m.get('slug')}", image=m.get("icon"),
            end_date=m.get("endDate"), hours_since_end=round((NOW - end).total_seconds() / 3600, 1) if end else None,
            best_ask=ask, best_bid=bid, tick=tick, suggested_limit=maker, depth_usd=round(depth),
            gain_taker_pct=round(gain_taker * 100, 3), gain_maker_pct=round(gain_maker * 100, 3),
            taker_fee_est=round(fee, 5), res_status=status, expected_settlement=r.get("expected_settlement_time"),
            est_days=round(est_days, 2), annual_yield_taker=round(gain_taker / max(est_days, 0.25) * 365, 3),
            annual_yield_maker=round(gain_maker / max(est_days, 0.25) * 365, 3),
            volume=round(float(m.get("volumeNum") or 0)), reasons=reasons))
    sigs.sort(key=lambda s: -max(s["annual_yield_taker"], s["annual_yield_maker"] * 0.5))
    log(f"sniper: {len(sigs)} signals")
    return sigs


# ---------------------------------------------------------------- copy
def scan_copy():
    c = CFG["copy"]
    start = int((NOW - timedelta(minutes=c["lookback_minutes"])).timestamp())
    win = c["group_window_minutes"] * 60
    sigs = []
    for w in c["wallets"]:
        r = http(f"{DATA}/activity", {"user": w["address"], "type": "TRADE", "start": start, "limit": 1000,
                                      "sort_by": "TIMESTAMP", "sort_direction": "DESC"})
        rows = (r or {}).get("data") or []
        groups = {}
        for a in rows:
            if a.get("type") != "TRADE":
                continue
            k = (a["condition_id"], a.get("outcome"), a.get("side"), int(a["timestamp"]) // win)
            g = groups.setdefault(k, dict(usd=0.0, size=0.0, fills=0, first=a["timestamp"], last=a["timestamp"], a=a))
            g["usd"] += float(a.get("usdc_size") or 0); g["size"] += float(a.get("size") or 0); g["fills"] += 1
            g["first"] = min(g["first"], a["timestamp"]); g["last"] = max(g["last"], a["timestamp"])
        for (cond, outcome, side, bucket), g in groups.items():
            if g["usd"] < w["min_usd"]:
                continue
            a = g["a"]
            sigs.append(dict(
                id=f"cpy:{w['address'][:10]}:{cond[:12]}:{outcome}:{side}:{bucket}", type="copy",
                wallet=w["label"], wallet_style=w["style"], address=w["address"], question=a.get("title"),
                outcome=outcome, side=side, token_id=a.get("token_id"), condition_id=cond,
                event_slug=a.get("event_slug"), slug=a.get("slug"), image=a.get("icon"),
                url=f"https://polymarket.com/event/{a.get('event_slug') or a.get('slug')}",
                usd=round(g["usd"]), size=round(g["size"], 2), avg_price=round(g["usd"] / g["size"], 4) if g["size"] else None,
                fills=g["fills"], first_ts=g["first"], last_ts=g["last"]))
        log(f"copy: {w['label']}: {len(rows)} fills, {sum(1 for s in sigs if s['address'] == w['address'])} signals")
        time.sleep(0.3)
    bk = books([s["token_id"] for s in sigs if s.get("token_id")])
    for s in sigs:
        bids, asks = bk.get(s["token_id"], ([], []))
        s["now_ask"] = asks[0][0] if asks else None
        s["now_bid"] = bids[0][0] if bids else None
        if s["now_ask"] and s["avg_price"]:
            s["slippage_c"] = round((s["now_ask"] - s["avg_price"]) * 100, 2)
    return sigs


# ---------------------------------------------------------------- notify
def ntfy(title, body, url, tags, priority=3):
    if not NOTIFY:
        return
    req = urllib.request.Request(f"https://ntfy.sh/{CFG['ntfy_topic']}", data=body.encode(), headers={
        "Title": title.encode("ascii", "ignore").decode(), "Tags": tags, "Click": url, "Priority": str(priority)})
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        log("  ntfy failed", repr(e)[:120])


if __name__ == "__main__":
    state_fn = os.path.join(OUT, "state.json")
    state = json.load(open(state_fn)) if os.path.exists(state_fn) else {"seen": {}, "copy_history": []}
    sniper, copy = scan_sniper(), scan_copy()
    seen = state["seen"]
    new_copy = [s for s in copy if s["id"] not in seen]
    new_snp = [s for s in sniper if s["id"] not in seen and s["annual_yield_taker"] >= CFG["sniper"]["notify_min_annual_yield"]]
    for s in new_copy:
        price = f"{s['avg_price'] * 100:.1f}c" if s["avg_price"] else "?"
        now = f", now {s['now_ask'] * 100:.1f}c" if s.get("now_ask") else ""
        ntfy(f"{s['wallet']} {s['side']} {s['outcome']}", f"{s['question']}\n${s['usd']:,} at {price}{now}", s["url"], "eyes", 4)
    for s in new_snp[:5]:
        ntfy(f"Sniper: {s['outcome']} @ {s['best_ask'] * 100:.1f}c", f"{s['question']}\n+{s['gain_taker_pct']:.2f}% in ~{s['est_days']:.1f}d "
             f"(~{s['annual_yield_taker'] * 100:.0f}%/yr), ${s['depth_usd']:,} available", s["url"], "dart", 3)
    stamp = int(NOW.timestamp())
    for s in sniper + copy:
        seen.setdefault(s["id"], stamp)
    state["seen"] = {k: v for k, v in seen.items() if v > stamp - 14 * 86400}
    hist = {h["id"]: h for h in state.get("copy_history", [])}
    for s in copy:
        hist[s["id"]] = s
    state["copy_history"] = sorted(hist.values(), key=lambda h: -h["last_ts"])[:300]
    json.dump(state, open(state_fn, "w"))
    json.dump(dict(generated_at=iso(NOW), sniper=sniper[:150], copy=state["copy_history"][:150],
                   wallets=CFG["copy"]["wallets"]), open(os.path.join(OUT, "signals.json"), "w"))
    log(f"done: {len(sniper)} sniper, {len(copy)} copy now, {len(new_copy)} new copy, {len(new_snp)} new sniper notified")
