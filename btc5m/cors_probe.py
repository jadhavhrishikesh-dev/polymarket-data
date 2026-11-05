"""Can a browser page reach the data? Prints CORS headers and tests websockets with a browser Origin."""
import json, urllib.request, asyncio, time, sys, subprocess
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "websockets"])
import websockets
ORIGIN = "https://jadhavhrishikesh-dev.github.io"
start = int(time.time()) // 300 * 300
def probe(url, body=None):
    h = {"Origin": ORIGIN, "User-Agent": "Mozilla/5.0"}
    if body: h["Content-Type"] = "application/json"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=h), timeout=10)
        print(url[:80], r.status, "ACAO=", r.headers.get("Access-Control-Allow-Origin")); return json.load(r)
    except Exception as e: print(url[:80], "ERR", repr(e)[:120])
    # preflight
ev = probe(f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{start}")
toks = json.loads(ev["markets"][0]["clobTokenIds"]) if ev else []
probe("https://clob.polymarket.com/books", [{"token_id": t} for t in toks])
probe(f"https://clob.polymarket.com/book?token_id={toks[0]}" if toks else "https://clob.polymarket.com/")
probe("https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=BTCUSDT")
probe("https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT")
for u, m in (("https://clob.polymarket.com/books", "POST"),):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, method="OPTIONS", headers={"Origin": ORIGIN, "Access-Control-Request-Method": m, "Access-Control-Request-Headers": "content-type"}), timeout=10)
        print("preflight", u, r.status, dict((k, v) for k, v in r.headers.items() if k.lower().startswith("access-control")))
    except Exception as e: print("preflight ERR", repr(e)[:150])
async def ws(url, sub, n=6, ping=None):
    try:
        async with websockets.connect(url, origin=ORIGIN, open_timeout=10) as w:
            await w.send(json.dumps(sub)); t0 = time.time(); k = 0
            while k < n and time.time() - t0 < 25:
                try: m = await asyncio.wait_for(w.recv(), 6)
                except asyncio.TimeoutError:
                    if ping: await w.send(ping)
                    continue
                print("  ", url[-30:], str(m)[:300]); k += 1
    except Exception as e: print("WS ERR", url, repr(e)[:200])
async def main():
    await ws("wss://ws-live-data.polymarket.com", {"action": "subscribe", "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": "{\"symbol\":\"btc/usd\"}"}]}, 5, "PING")
    await ws("wss://ws-live-data.polymarket.com", {"action": "subscribe", "subscriptions": [{"topic": "crypto_prices_twap_sixty", "type": "*", "filters": "{\"symbol\":\"btc/usd\"}"}]}, 5, "PING")
    await ws("wss://ws-live-v2.polymarket.com/ws", {"op": "subscribe", "rid": "s1", "subscriptions": [{"channel": "price.crypto", "filter": {"symbol": "btcusd"}}]}, 3)
    if toks: await ws("wss://ws-subscriptions-clob.polymarket.com/ws/market", {"assets_ids": toks, "type": "market"}, 4, "PING")
    await ws("wss://stream.binance.com:9443/ws/btcusdt@bookTicker", {"method": "SUBSCRIBE", "params": ["btcusdt@bookTicker"], "id": 1}, 3)
    await ws("wss://data-stream.binance.vision/ws/btcusdt@bookTicker", {"method": "SUBSCRIBE", "params": ["btcusdt@bookTicker"], "id": 1}, 3)
asyncio.run(main())
