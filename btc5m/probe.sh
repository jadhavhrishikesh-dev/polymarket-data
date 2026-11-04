#!/usr/bin/env bash
# Discovery probe: docs + one raw BTC 5m market, written to data/_btc5m/probe/
set -u
OUT=data/_btc5m/probe; mkdir -p $OUT
UA="Mozilla/5.0 polymarket-data-fetcher"
g() { curl -sS -A "$UA" --max-time 30 "$1" -o "$OUT/$2" -w "$2 %{http_code}\n"; }
g "https://docs.polymarket.com/llms.txt" llms.txt
NOW=$(date +%s); T=$(( NOW/300*300 - 600 ))
g "https://gamma-api.polymarket.com/events/slug/btc-updown-5m-$T" event_prev.json
g "https://gamma-api.polymarket.com/events/slug/btc-updown-5m-$(( NOW/300*300 ))" event_live.json
g "https://gamma-api.polymarket.com/markets/slug/btc-updown-5m-$T" market_prev.json
g "https://gamma-api.polymarket.com/events?series_slug=btc-up-or-down-5m&limit=5&closed=true&order=endDate&ascending=false" series_events.json
g "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60" cb_1m.json
g "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=10" binance_vision.json
g "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=10" binance.json
echo "$NOW" > $OUT/now.txt
