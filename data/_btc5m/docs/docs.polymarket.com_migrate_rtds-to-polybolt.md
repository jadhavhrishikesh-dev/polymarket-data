> ## Documentation Index
> Fetch the complete documentation index at: https://docs.polymarket.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Migrate from RTDS to PolyBolt

> Migrate price subscriptions from RTDS to PolyBolt

Move reference-price subscriptions to PolyBolt while keeping your event-driven price workflow. Reference prices require authentication.

## Migrate an API Integration

Update the connection, authentication, and subscription frames. See the [Live Data Channel](https://docs.polymarket.com/api-reference/wss/polybolt.md) for the full protocol.

### What Changes

| RTDS | PolyBolt |
| - | - |
| `wss://ws-live-data.polymarket.com` | `wss://ws-live-v2.polymarket.com/ws` |
| Text frame `PING` every 5 s | Nothing to send. The server pings every 25 s (optional `{"op":"ping"}`) |
| `{"action":"subscribe","subscriptions":[{"topic","type","filters"}]}` | `{"op":"subscribe","subscriptions":[{"channel","filter"}]}`. `filter` is a JSON object, not a string |
| Source-named price and TWAP topics | Channels `price.crypto`, `price.crypto.twap`, `price.equity` (see the mapping below) |
| `{"topic","type","timestamp","payload"}` per message | `{"v":1,"channel","seq","ts","snapshot"?,"dropped"?,"payload"}`. Channel-specific payloads |
| Silence for a quiet symbol | One snapshot frame per subscription (`snapshot: true`), possibly empty |
| No sequence | Dense per-channel `seq` and a `dropped` counter |
| Public | Reference-price channels require CLOB API credentials via `{"op":"auth"}` |
| No limits | 64 subscriptions, 20 subscribe frames/s, 64 KB frames, 8 auth frames. Breaches close `4008` |
| Raw `1006` closes | `4001` auth, `4002` slow consumer, `4003` draining, `4008` policy |

### Topic Mapping

| RTDS topic | RTDS filter | PolyBolt channel | PolyBolt filter | Notes |
| - | - | - | - | - |
| `crypto_prices` (Binance) | `btcusdt` | `price.crypto` | `{"symbol":"btcusd"}` | Source changes to Chainlink by default and quote currency changes from USDT to USD. |
| `crypto_prices_chainlink` | `{"symbol":"btc/usd"}` | `price.crypto` | `{"symbol":"btcusd"}` | Source stays Chainlink, the `price.crypto` default. Use `btcusd` instead of `btc/usd`. |
| `crypto_prices_twap_sixty` | `{"symbol":"btc/usd"}` | `price.crypto.twap` | `{"symbol":"btcusd","window_seconds":60}` | 60-second Chainlink TWAP |
| `crypto_prices_twap_thirty` | `{"symbol":"btc/usd"}` | None | None | No PolyBolt replacement for the 30-second window |
| `equity_prices` | `{"symbol":"AAPL"}` | `price.equity` | `{"symbol":"aapl"}` | Same catalog, lowercase: stocks, ETFs, forex, metals and the commodities `cll`, `hn`, `cc3m` |

> [!WARNING]
>
> Crypto spot and TWAP subscriptions now use lowercase symbols ending in `usd`,
> not `usdt`. Update `btcusdt` or `btc/usd` to `btcusd`, and apply the same
> format to every crypto symbol you subscribe to.

Live price payloads contain `symbol`, `value`, `full_accuracy_value`,
`timestamp`, and `source`, the vendor that produced the price. `price.crypto`
and `price.equity` default to Chainlink wherever Chainlink serves the symbol;
add `provider` to the filter to pin a specific vendor
([Pin a Price Provider](https://docs.polymarket.com/api-reference/live-data/overview.md#pin-a-price-provider)).
Equity updates may also include `received_at` and `is_carried_forward`, and
equity payloads carry `market_status` (`open`, `closed` or `unknown`), which
legacy RTDS never sent
([Read the Market Status](https://docs.polymarket.com/api-reference/live-data/overview.md#read-the-market-status)).
TWAP uses `window_seconds`. Prefer the exact decimal `full_accuracy_value` over the
float `value`. Legacy TWAP frames used `window_s` and an E18 fixed-point
price. Do not apply that E18 conversion to PolyBolt's decimal string.

### Before and After

```json RTDS theme={null}
{
  "action": "subscribe",
  "subscriptions": [
    { "topic": "crypto_prices", "type": "update", "filters": "btcusdt" }
  ]
}
```

```json PolyBolt theme={null}
{ "op": "auth", "auth": { "apiKey": "<api key>", "secret": "<api secret>", "passphrase": "<api passphrase>" } }
{ "op": "subscribe", "subscriptions": [ { "channel": "price.crypto", "filter": { "symbol": "btcusd" } } ] }
```

### Client Checklist

1. Point at `wss://ws-live-v2.polymarket.com/ws` and delete the `PING` text heartbeat.
2. Send `{"op":"auth", ...}` with CLOB API credentials before subscribing to price channels.
3. Batch subscriptions per connection. Stay at or below 64 active pairs.
4. Seed local state from the snapshot, then apply live updates. Compare `seq` only within the same connection and channel.
5. Handle `4003` with one jittered reconnect, `4008` as a bug, and resubscribe after every reconnect.

## Comments Retirement

The live comments stream is being retired without a replacement streaming channel.
See [Comments](https://docs.polymarket.com/market-data/realtime-data.md#comments) for supported comment-listing options.

## Activity on RTDS

Keep using RTDS for the `activity` topic. It has no PolyBolt channel.

## Migrate SDKs to PolyBolt

### Migrate a 60-Second TWAP Subscription

> [tab] TypeScript
>
> PolyBolt support starts in `@polymarket/client` version `0.11.0`.
> Migrate a BTC/USD 60-second TWAP subscription with `createSecureClient`. Deprecated RTDS price topics are planned for removal one month after the `0.11.0` release.
>
> > [accordion] Before: RTDS
> >
> > ```ts theme={null}
> > import { createPublicClient } from "@polymarket/client";
> >
> > const client = createPublicClient();
> > const stream = await client.subscribe([
> >   {
> >     topic: "prices.crypto.chainlink.twap",
> >     symbols: ["btc/usd"],
> >     windowSeconds: 60,
> >   },
> > ]);
> >
> > try {
> >   for await (const event of stream) {
> >     if (event.type === "update") {
> >       const price = event.payload.value;
> >     }
> >   }
> > } finally {
> >   await stream.close();
> > }
> > ```
>
> **1. Create an Authenticated Client**
>
> Set `POLYMARKET_PRIVATE_KEY`. This example uses the signer's EOA address and the default production configuration.
>
> ```ts theme={null}
> import { createSecureClient } from "@polymarket/client";
> import { privateKey } from "@polymarket/client/viem";
>
> const signer = privateKey(process.env.POLYMARKET_PRIVATE_KEY);
> const client = await createSecureClient({
>   signer,
>   wallet: await signer.getAddress(),
> });
> ```
>
> **2. Subscribe to Prices**
>
> Change the topic from `prices.crypto.chainlink.twap` to `prices.crypto.twap` and provide an explicit `symbols` list. Change `btc/usd` to `btcusd` and remove `windowSeconds` from the subscription input. The new topic always uses a 60-second window.
>
> ```ts theme={null}
> const stream = await client.subscribe([
>   { topic: "prices.crypto.twap", symbols: ["btcusd"] },
> ]);
>
> try {
>   for await (const event of stream) {
>     // event: CryptoTwapPriceEvent
>     if (event.type === "subscribe") {
>       const history = event.payload.data;
>       // Seed local state from the snapshot.
>     } else {
>       const price = event.payload.value;
>       const observedAt = event.payload.timestamp;
>       // Apply the latest price.
>     }
>   }
> } finally {
>   await stream.close();
> }
> ```
>
> > [accordion] Output: CryptoTwapPriceEvent
> >
> > **events: CryptoTwapPriceEvent\[]**
> >
> > ```ts CryptoTwapPriceEvent Union theme={null}
> > type CryptoTwapPriceEvent =
> >   | {
> >       topic: "prices.crypto.twap";
> >       type: "subscribe";
> >       timestamp: EpochMilliseconds;
> >       seq?: number;
> >       dropped?: number;
> >       payload: {
> >         symbol: string;
> >         data: { timestamp: EpochMilliseconds; value: DecimalString }[];
> >         windowSeconds: 60;
> >       };
> >     }
> >   | {
> >       topic: "prices.crypto.twap";
> >       type: "update";
> >       timestamp: EpochMilliseconds;
> >       seq?: number;
> >       dropped?: number;
> >       payload: {
> >         symbol: string;
> >         timestamp: EpochMilliseconds;
> >         value: DecimalString;
> >         windowSeconds: 60;
> >       };
> >     };
> > ```
> >
> > ```json CryptoTwapPriceEvent Example theme={null}
> > [
> >   {
> >     "topic": "prices.crypto.twap",
> >     "type": "subscribe",
> >     "timestamp": 1788886175000,
> >     "seq": 2,
> >     "payload": {
> >       "symbol": "btcusd",
> >       "data": [
> >         {
> >           "timestamp": 1788886057000,
> >           "value": "78788.525642908795142144"
> >         },
> >         {
> >           "timestamp": 1788886058000,
> >           "value": "78788.786579938813673472"
> >         },
> >         {
> >           "timestamp": 1788886059000,
> >           "value": "78789.052518750893375488"
> >         }
> >       ],
> >       "windowSeconds": 60
> >     }
> >   },
> >   {
> >     "topic": "prices.crypto.twap",
> >     "type": "update",
> >     "timestamp": 1788886177000,
> >     "seq": 3,
> >     "payload": {
> >       "symbol": "btcusd",
> >       "timestamp": 1788886177000,
> >       "value": "78803.715261094101516288",
> >       "windowSeconds": 60
> >     }
> >   }
> > ]
> > ```
>
> Returned events still include `windowSeconds: 60`. There is no PolyBolt replacement for the deprecated 30-second TWAP workflow.
>
> `subscribe()` waits for server acceptance. Snapshot events provide `payload.data` for initialization. Updates retain `symbol`, `timestamp`, decimal-string `value`, and `windowSeconds`.
>
> The new crypto topics require explicit lowercase USD symbols such as `btcusd`. Inputs such as `btc/usd`, `btcusdt`, and `BTCUSD` fail with `UserInputError`. The SDK does not rewrite them.

> [tab] Python
>
> Migrate a BTC/USD 60-second TWAP subscription with `AsyncSecureClient.subscribe`. Run the following steps inside an async function.
>
> > [!NOTE]
> >
> > PolyBolt support starts in `polymarket-client` version `0.11.0`. The legacy
> > RTDS price specs are deprecated.
>
> > [accordion] Before: RTDS
> >
> > The legacy subscription passed these specs to `AsyncPublicClient.subscribe` or `AsyncSecureClient.subscribe`:
> >
> > ```python theme={null}
> > from polymarket.streams import CryptoPricesChainlinkTwapSpec
> >
> > spec = CryptoPricesChainlinkTwapSpec(symbols=["btc/usd"], window_seconds=60)
> > ```
>
> **1. Create an Authenticated Client**
>
> Set `POLYMARKET_PRIVATE_KEY` to your signer private key. This example uses the signer's EOA address. `AsyncSecureClient.create` derives or retrieves API credentials.
>
> ```python theme={null}
> import os
>
> from eth_account import Account
> from polymarket import AsyncSecureClient
>
> private_key = os.environ["POLYMARKET_PRIVATE_KEY"]
> client = await AsyncSecureClient.create(
>     private_key=private_key,
>     wallet=Account.from_key(private_key).address,
> )
> ```
>
> **2. Subscribe to Prices**
>
> Subscribe to BTC/USD with `CryptoTwapPriceSpec`. The async context manager closes the subscription when the block exits.
>
> ```python theme={null}
> from polymarket.streams import CryptoTwapPriceSpec
>
> async with await client.subscribe(
>     CryptoTwapPriceSpec(symbols=["btcusd"])
> ) as stream:
>     async for event in stream:
>         # event: CryptoTwapPriceEvent
>         if event.type == "subscribe":
>             history = event.payload.data
>             # Seed local state from the snapshot.
>         else:
>             price = event.payload.value
>             observed_at = event.payload.timestamp
>             # Apply the latest price.
> ```
>
> > [accordion] Output: CryptoTwapPriceEvent
> >
> > **event: CryptoTwapPriceEvent**
> >
> > ```python CryptoTwapPriceEvent Union theme={null}
> > class RealtimePricePoint:
> >     timestamp: datetime
> >     value: Decimal
> >
> > class RealtimeTwapSnapshot:
> >     symbol: str
> >     data: tuple[RealtimePricePoint, ...]
> >     window_seconds: Literal[60]
> >
> > class RealtimeTwapUpdate:
> >     symbol: str
> >     timestamp: datetime
> >     value: Decimal
> >     window_seconds: Literal[60]
> >
> > class CryptoTwapPriceSnapshotEvent:
> >     topic: Literal["prices.crypto.twap"]
> >     type: Literal["subscribe"]
> >     timestamp: datetime
> >     seq: int | None
> >     dropped: int | None
> >     payload: RealtimeTwapSnapshot
> >
> > class CryptoTwapPriceUpdateEvent:
> >     topic: Literal["prices.crypto.twap"]
> >     type: Literal["update"]
> >     timestamp: datetime
> >     seq: int | None
> >     dropped: int | None
> >     payload: RealtimeTwapUpdate
> >
> > CryptoTwapPriceEvent = CryptoTwapPriceSnapshotEvent | CryptoTwapPriceUpdateEvent
> > ```
> >
> > ```json CryptoTwapPriceEvent Example theme={null}
> > {
> >   "timestamp": "2026-09-08T16:49:37Z",
> >   "seq": 3,
> >   "topic": "prices.crypto.twap",
> >   "type": "update",
> >   "payload": {
> >     "timestamp": "2026-09-08T16:49:37Z",
> >     "value": "78803.715261094101516288",
> >     "symbol": "btcusd",
> >     "window_seconds": 60
> >   }
> > }
> > ```
>
> `subscribe()` waits for server acceptance. The SDK handles authentication, heartbeats, reconnects, and distributing filters beyond 64 per connection. Handle errors from both subscription creation and iteration. Acceptance times out after 30 seconds. `seq` belongs to one channel on one connection and resets after reconnecting.
>
> Crypto symbols must be explicit lowercase USD pairs such as `btcusd`. `btc/usd`, `btcusdt`, and `BTCUSD` raise `UserInputError`.

### Migrate Crypto Spot Prices

> [tab] TypeScript
>
> Use the authenticated `client` created above. Change the symbol suffix from `usdt` to `usd`, for example `btcusdt` to `btcusd`. Remove any slash separators, for example `btc/usd` to `btcusd`. The new topic requires explicit lowercase USD symbols.
>
> The `prices.crypto` topic defaults to Chainlink prices, so migrating from the legacy Chainlink spot topic keeps the data source. Migrating from Binance changes both the source and the quote currency, from USDT to USD. Confirm that the new feed meets your pricing requirements before switching.
>
> > [accordion] Before: RTDS
> >
> > ```ts theme={null}
> > import { createPublicClient } from "@polymarket/client";
> >
> > const client = createPublicClient();
> > const stream = await client.subscribe([
> >   { topic: "prices.crypto.chainlink", symbols: ["btc/usd"] },
> >   { topic: "prices.crypto.binance", symbols: ["btcusdt"] },
> > ]);
> >
> > try {
> >   for await (const event of stream) {
> >     if (event.type === "update") {
> >       const price = event.payload.value;
> >     }
> >   }
> > } finally {
> >   await stream.close();
> > }
> > ```
>
> Replace the legacy subscription with:
>
> ```ts theme={null}
> const stream = await client.subscribe([
>   { topic: "prices.crypto", symbols: ["btcusd"] },
> ]);
> try {
>   for await (const event of stream) {
>     if (event.type === "subscribe") {
>       const history = event.payload.data; // Snapshot of historical prices.
>     } else {
>       const price = event.payload.value;
>     }
>   }
> } finally {
>   await stream.close();
> }
> ```
>
> > [accordion] Output: CryptoPriceEvent
> >
> > **events: CryptoPriceEvent\[]**
> >
> > ```ts CryptoPriceEvent Union theme={null}
> > type CryptoPriceEvent =
> >   | {
> >       topic: "prices.crypto";
> >       type: "subscribe";
> >       timestamp: EpochMilliseconds;
> >       seq?: number;
> >       dropped?: number;
> >       payload: {
> >         symbol: string;
> >         data: { timestamp: EpochMilliseconds; value: DecimalString }[];
> >       };
> >     }
> >   | {
> >       topic: "prices.crypto";
> >       type: "update";
> >       timestamp: EpochMilliseconds;
> >       seq?: number;
> >       dropped?: number;
> >       payload: {
> >         symbol: string;
> >         timestamp: EpochMilliseconds;
> >         value: DecimalString;
> >         receivedAt: EpochMilliseconds | undefined;
> >         isCarriedForward: boolean | undefined;
> >       };
> >     };
> > ```
> >
> > ```json CryptoPriceEvent Example theme={null}
> > [
> >   {
> >     "topic": "prices.crypto",
> >     "type": "subscribe",
> >     "timestamp": 1788886176000,
> >     "seq": 1,
> >     "payload": {
> >       "symbol": "btcusd",
> >       "data": [
> >         {
> >           "timestamp": 1788886057000,
> >           "value": "78803.76173179"
> >         },
> >         {
> >           "timestamp": 1788886058000,
> >           "value": "78801.86287741"
> >         },
> >         {
> >           "timestamp": 1788886059000,
> >           "value": "78798.28703224"
> >         }
> >       ]
> >     }
> >   },
> >   {
> >     "topic": "prices.crypto",
> >     "type": "update",
> >     "timestamp": 1788886177000,
> >     "seq": 5,
> >     "payload": {
> >       "symbol": "btcusd",
> >       "timestamp": 1788886177000,
> >       "value": "78794.15450441"
> >     }
> >   }
> > ]
> > ```

> [tab] Python
>
> Use the authenticated `client` created above, then call `client.subscribe`.
>
> > [accordion] Before: RTDS
> >
> > The legacy subscription passed these specs to `AsyncPublicClient.subscribe` or `AsyncSecureClient.subscribe`:
> >
> > ```python theme={null}
> > from polymarket.streams import CryptoPricesSpec
> >
> > specs = [
> >     CryptoPricesSpec(topic="prices.crypto.chainlink", symbols=["btc/usd"]),
> >     CryptoPricesSpec(topic="prices.crypto.binance", symbols=["btcusdt"]),
> > ]
> > ```
>
> Replace `CryptoPricesSpec` with `CryptoPriceSpec` and choose USD prices explicitly. Binance `btcusdt` is quoted in USDT; `btcusd` is quoted in USD and defaults to Chainlink, so migrating from the legacy Chainlink spot topic keeps the source while migrating from Binance changes it. Confirm the feed fits your pricing requirements.
>
> Replace the legacy call with this subscription:
>
> ```python theme={null}
> from polymarket.streams import CryptoPriceSpec
>
> async with await client.subscribe(
>     CryptoPriceSpec(symbols=["btcusd"])
> ) as stream:
>     async for event in stream:
>         # event: CryptoPriceEvent
>         if event.type == "subscribe":
>             history = event.payload.data  # Snapshot of historical prices.
>         else:
>             price = event.payload.value
>             observed_at = event.payload.timestamp
> ```
>
> > [accordion] Output: CryptoPriceEvent
> >
> > **event: CryptoPriceEvent**
> >
> > ```python CryptoPriceEvent Union theme={null}
> > class RealtimePricePoint:
> >     timestamp: datetime
> >     value: Decimal
> >
> > class RealtimePriceSnapshot:
> >     symbol: str
> >     data: tuple[RealtimePricePoint, ...]
> >
> > class RealtimePriceUpdate:
> >     symbol: str
> >     timestamp: datetime
> >     value: Decimal
> >     received_at: datetime | None
> >     is_carried_forward: bool | None
> >
> > class CryptoPriceSnapshotEvent:
> >     topic: Literal["prices.crypto"]
> >     type: Literal["subscribe"]
> >     timestamp: datetime
> >     seq: int | None
> >     dropped: int | None
> >     payload: RealtimePriceSnapshot
> >
> > class CryptoPriceUpdateEvent:
> >     topic: Literal["prices.crypto"]
> >     type: Literal["update"]
> >     timestamp: datetime
> >     seq: int | None
> >     dropped: int | None
> >     payload: RealtimePriceUpdate
> >
> > CryptoPriceEvent = CryptoPriceSnapshotEvent | CryptoPriceUpdateEvent
> > ```
> >
> > ```json CryptoPriceEvent Example theme={null}
> > {
> >   "timestamp": "2026-09-08T16:49:37Z",
> >   "seq": 5,
> >   "topic": "prices.crypto",
> >   "type": "update",
> >   "payload": {
> >     "timestamp": "2026-09-08T16:49:37Z",
> >     "value": "78794.15450441",
> >     "symbol": "btcusd"
> >   }
> > }
> > ```
>
> `subscribe` events provide a tuple of historical price points in `payload.data`. `update` events provide the latest price. Values are `Decimal`, and timestamps are UTC `datetime` objects.
>
> Choose explicit lowercase USD symbols such as `btcusd`. For live prices only, skip events whose `type` is `"subscribe"`.

### Migrate Equity Prices

> [tab] TypeScript
>
> Use the authenticated `client` created above. Preserve `symbol` and `types` when changing the topic.
>
> > [accordion] Before: RTDS
> >
> > ```ts theme={null}
> > import { createPublicClient } from "@polymarket/client";
> >
> > const client = createPublicClient();
> > const stream = await client.subscribe([
> >   { topic: "prices.equity.pyth", symbol: "aapl", types: ["update"] },
> > ]);
> >
> > try {
> >   for await (const event of stream) {
> >     if (event.type === "update") {
> >       const price = event.payload.value;
> >     }
> >   }
> > } finally {
> >   await stream.close();
> > }
> > ```
>
> Replace the legacy subscription with:
>
> ```ts theme={null}
> const stream = await client.subscribe([
>   { topic: "prices.equity", symbol: "aapl", types: ["update"] },
> ]);
> try {
>   for await (const event of stream) {
>     if (event.type === "update") {
>       const price = event.payload.value;
>     }
>   }
> } finally {
>   await stream.close();
> }
> ```
>
> > [accordion] Output: EquityPriceEvent
> >
> > **events: EquityPriceEvent\[]**
> >
> > ```ts EquityPriceEvent Union theme={null}
> > import type { EquityMarketStatus } from "@polymarket/client";
> >
> > type EquityPriceEvent =
> >   | {
> >       topic: "prices.equity";
> >       type: "subscribe";
> >       timestamp: EpochMilliseconds;
> >       seq?: number;
> >       dropped?: number;
> >       payload: {
> >         symbol: string;
> >         marketStatus?: EquityMarketStatus;
> >         data: { timestamp: EpochMilliseconds; value: DecimalString }[];
> >       };
> >     }
> >   | {
> >       topic: "prices.equity";
> >       type: "update";
> >       timestamp: EpochMilliseconds;
> >       seq?: number;
> >       dropped?: number;
> >       payload: {
> >         symbol: string;
> >         marketStatus?: EquityMarketStatus;
> >         timestamp: EpochMilliseconds;
> >         value: DecimalString;
> >         receivedAt: EpochMilliseconds | undefined;
> >         isCarriedForward: boolean | undefined;
> >       };
> >     };
> > ```
> >
> > ```json EquityPriceEvent Example theme={null}
> > [
> >   {
> >     "topic": "prices.equity",
> >     "type": "subscribe",
> >     "timestamp": 1788886176400,
> >     "seq": 1,
> >     "payload": {
> >       "symbol": "aapl",
> >       "marketStatus": "open",
> >       "data": [
> >         {
> >           "timestamp": 1788886056800,
> >           "value": "316.11"
> >         },
> >         {
> >           "timestamp": 1788886057000,
> >           "value": "316.11"
> >         },
> >         {
> >           "timestamp": 1788886057200,
> >           "value": "316.11001"
> >         }
> >       ]
> >     }
> >   },
> >   {
> >     "topic": "prices.equity",
> >     "type": "update",
> >     "timestamp": 1788886176600,
> >     "seq": 2,
> >     "payload": {
> >       "symbol": "aapl",
> >       "marketStatus": "open",
> >       "timestamp": 1788886176600,
> >       "value": "316.1",
> >       "receivedAt": 1788886176600
> >     }
> >   }
> > ]
> > ```
>
> `types: ["update"]` keeps this stream limited to live updates. Omit `types` to receive history snapshots too.

> [tab] Python
>
> Use the authenticated `client` created above, then call `client.subscribe`.
>
> > [accordion] Before: RTDS
> >
> > The legacy subscription passed these specs to `AsyncPublicClient.subscribe` or `AsyncSecureClient.subscribe`:
> >
> > ```python theme={null}
> > from polymarket.streams import EquityPricesSpec
> >
> > spec = EquityPricesSpec(symbol="AAPL", types=["update"])
> > ```
>
> Replace `EquityPricesSpec` with `EquityPriceSpec`, preserving `symbol` and `types`. Symbols are trimmed and lowercased. `types=["update"]` keeps live updates only. Omit `types` to receive history snapshots too.
>
> Replace the legacy call with this subscription:
>
> ```python theme={null}
> from polymarket.streams import EquityPriceSpec
>
> async with await client.subscribe(
>     EquityPriceSpec(symbol="aapl", types=["update"])
> ) as stream:
>     async for event in stream:
>         # event: EquityPriceEvent
>         if event.type == "update":
>             price = event.payload.value
>             observed_at = event.payload.timestamp
> ```
>
> > [accordion] Output: EquityPriceEvent
> >
> > **event: EquityPriceEvent**
> >
> > ```python EquityPriceEvent Union theme={null}
> > from polymarket.streams import EquityMarketStatus
> >
> > class RealtimePricePoint:
> >     timestamp: datetime
> >     value: Decimal
> >
> > class RealtimeEquityPriceSnapshot:
> >     symbol: str
> >     market_status: EquityMarketStatus | None = None
> >     data: tuple[RealtimePricePoint, ...]
> >
> > class RealtimeEquityPriceUpdate:
> >     symbol: str
> >     market_status: EquityMarketStatus | None = None
> >     timestamp: datetime
> >     value: Decimal
> >     received_at: datetime | None
> >     is_carried_forward: bool | None
> >
> > class EquityPriceSnapshotEvent:
> >     topic: Literal["prices.equity"]
> >     type: Literal["subscribe"]
> >     timestamp: datetime
> >     seq: int | None
> >     dropped: int | None
> >     payload: RealtimeEquityPriceSnapshot
> >
> > class EquityPriceUpdateEvent:
> >     topic: Literal["prices.equity"]
> >     type: Literal["update"]
> >     timestamp: datetime
> >     seq: int | None
> >     dropped: int | None
> >     payload: RealtimeEquityPriceUpdate
> >
> > EquityPriceEvent = EquityPriceSnapshotEvent | EquityPriceUpdateEvent
> > ```
> >
> > ```json EquityPriceEvent Example theme={null}
> > {
> >   "timestamp": "2026-09-08T16:49:36.600000Z",
> >   "seq": 2,
> >   "topic": "prices.equity",
> >   "type": "update",
> >   "payload": {
> >     "timestamp": "2026-09-08T16:49:36.600000Z",
> >     "value": "316.1",
> >     "symbol": "aapl",
> >     "market_status": "open",
> >     "received_at": "2026-09-08T16:49:36.600000Z"
> >   }
> > }
> > ```
>
> `subscribe` events provide a tuple of historical price points in `payload.data`. `update` events provide the latest price. Values are `Decimal`, and timestamps are UTC `datetime` objects.
>
> Updates may include `received_at` and `is_carried_forward`.

Read [market status](https://docs.polymarket.com/market-data/realtime-data.md#read-the-market-status) on snapshots and live updates to distinguish closed markets from stalled prices. Both SDKs expose this field from version 0.14.0.


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.