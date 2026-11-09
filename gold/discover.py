"""Find Polymarket gold (XAU) short-window Up/Down markets; dump rules, metadata and recent history."""
import json, urllib.request, urllib.parse, time, os
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
OUT = "data/_gold"; os.makedirs(OUT, exist_ok=True)
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r: return json.load(r)
    except Exception as e: print("ERR", u[:100], repr(e)[:100]); return None
G = "https://gamma-api.polymarket.com"
found = {}
for q in ("gold up or down", "xau up or down", "gold 5 minute", "XAU/USD", "gold"):
    d = get(f"{G}/public-search?q={urllib.parse.quote(q)}&limit_per_type=50&events_status=active")
    for e in (d or {}).get("events", []) or []:
        found[e.get("slug")] = e.get("title")
    for s in (d or {}).get("series", []) or []: print("search-series", q, s.get("slug"), s.get("title"), s.get("recurrence"))
ser = []
for off in range(0, 4000, 500):
    d = get(f"{G}/series?limit=500&offset={off}")
    if not d: break
    ser += d
    if len(d) < 500: break
gs = [s for s in ser if any(k in (str(s.get("slug")) + str(s.get("title"))).lower() for k in ("gold", "xau", "silver", "xag", "paxg"))]
print("series total", len(ser))
for s in gs: print("SERIES", s.get("id"), s.get("slug"), "|", s.get("title"), "|", s.get("recurrence"), "| active", s.get("active"), "closed", s.get("closed"))
print("search events:"); [print("  ", k, "|", v) for k, v in list(found.items())[:60]]
json.dump({"series": gs, "search": found}, open(f"{OUT}/discover.json", "w"), indent=1)
# guess 5m slugs directly
now = int(time.time()) // 300 * 300
for pref in ("xau-updown-5m", "gold-updown-5m", "xauusd-updown-5m", "paxg-updown-5m", "gold-up-or-down-5m", "xau-up-or-down-5m"):
    e = get(f"{G}/events/slug/{pref}-{now}")
    if e: print("SLUG HIT", pref); json.dump(e, open(f"{OUT}/sample_{pref}.json", "w"), indent=1)
# for each 5m-looking series, dump one recent event in full
for s in gs:
    if "5" in str(s.get("slug")) or "5m" in str(s.get("recurrence")) or "5 min" in str(s.get("title")).lower():
        evs = get(f"{G}/events?series_id={s['id']}&limit=5&order=startDate&ascending=false")
        if evs:
            json.dump(evs, open(f"{OUT}/series_{s['slug']}_recent.json", "w"), indent=1)
            e = evs[0]; m = (e.get("markets") or [{}])[0]
            print("EVENT", e.get("slug"), e.get("startDate"), "\n  resolutionSource:", e.get("resolutionSource") or m.get("resolutionSource"),
                  "\n  eventMetadata:", e.get("eventMetadata"), "\n  desc:", (m.get("description") or e.get("description") or "")[:1500])
