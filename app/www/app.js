/* PM Signals: shows sniper and copy-trade signals, gates live trading on Polymarket's own geoblock check,
   and keeps a local log of trades (paper or live) with a scorecard. */
const SIGNALS_URL = "https://raw.githubusercontent.com/jadhavhrishikesh-dev/polymarket-data/signals-data/signals.json";
const NTFY_TOPIC = "pm-sig-86481239ad44";
const GEO_URL = "https://polymarket.com/api/geoblock";
const CLOB = "https://clob.polymarket.com";
const GAMMA = "https://gamma-api.polymarket.com";
const STORE = "pm_trades_v1";

const Cap = window.Capacitor || null;
const Plugins = (Cap && Cap.Plugins) || {};
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cents = (p) => (p == null ? "–" : `${(p * 100).toFixed(p > 0.95 || p < 0.05 ? 1 : 0)}¢`);
const usd = (n) => (n == null ? "–" : `$${Math.round(n).toLocaleString()}`);
const pct = (n, d = 2) => (n == null ? "–" : `${n >= 0 ? "+" : ""}${n.toFixed(d)}%`);
const ago = (t) => {
  const s = (Date.now() - (typeof t === "number" ? t * 1000 : Date.parse(t))) / 1000;
  if (s < 60) return "just now"; if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`; return `${Math.round(s / 86400)}d ago`;
};

const state = { data: null, live: null, geo: null, walletOn: new Set(), tab: "sniper" };

async function getJSON(url, opts) {
  const r = await fetch(url, Object.assign({ headers: { Accept: "application/json" } }, opts || {}));
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2200);
}
async function openUrl(url) {
  if (Plugins.Browser) return Plugins.Browser.open({ url });
  window.open(url, "_blank");
}
async function copyText(s) {
  try { if (Plugins.Clipboard) await Plugins.Clipboard.write({ string: s }); else await navigator.clipboard.writeText(s); toast("Copied"); }
  catch { toast("Couldn't copy"); }
}

/* ---------- trades store ---------- */
const loadTrades = () => { try { return JSON.parse(localStorage.getItem(STORE) || "[]"); } catch { return []; } };
const saveTrades = (t) => { try { localStorage.setItem(STORE, JSON.stringify(t)); } catch {} };

/* ---------- location gate ---------- */
async function checkGeo() {
  const el = $("#mode");
  try {
    const g = await getJSON(GEO_URL);
    state.geo = g; state.live = g.blocked === false;
  } catch { state.geo = null; state.live = false; }
  const c = state.geo && state.geo.country ? ` (${state.geo.country})` : "";
  el.className = "mode " + (state.live ? "mode-live" : "mode-paper");
  el.textContent = state.live
    ? `Live mode${c}: Polymarket allows trading here. Trades you log are tracked as live.`
    : state.geo
      ? `Paper mode${c}: Polymarket doesn't allow trading from here, so trades are logged as paper only.`
      : "Paper mode: couldn't confirm your location with Polymarket.";
}

/* ---------- data ---------- */
async function loadSignals() {
  try {
    state.data = await getJSON(`${SIGNALS_URL}?t=${Math.floor(Date.now() / 60000)}`);
    $("#updated").textContent = `Signals updated ${ago(state.data.generated_at)}`;
  } catch (e) {
    $("#updated").textContent = "Couldn't load signals. Pull to retry.";
  }
  renderAll();
}

function renderAll() { renderSniper(); renderCopy(); renderTrades(); }

function renderSniper() {
  const box = $("#list-sniper");
  const list = ((state.data && state.data.sniper) || []).filter((s) => !$("#hide-low").checked || s.confidence !== "low");
  const by = $("#sort-sniper").value;
  list.sort((a, b) => by === "depth" ? b.depth_usd - a.depth_usd : by === "price" ? b.best_bid - a.best_bid
    : Math.max(b.annual_yield_taker, b.annual_yield_maker) - Math.max(a.annual_yield_taker, a.annual_yield_maker));
  $("#n-sniper").textContent = list.length || "";
  if (!list.length) { box.innerHTML = `<div class="empty">No sniper signals right now.<br>The scanner checks every 5 minutes.</div>`; return; }
  box.innerHTML = list.map((s, i) => `
    <button class="card" data-kind="sniper" data-id="${esc(s.id)}">
      <div class="line1"><span class="tag t-${esc(s.confidence)}">${esc(s.confidence)} confidence</span><span class="muted">ended ${s.hours_since_end != null ? Math.round(s.hours_since_end) + "h ago" : "–"}</span></div>
      <div class="q">${esc(s.question)}</div>
      <div class="line1">
        <div class="meta"><span><span class="tag t-buy">BUY ${esc(s.outcome)}</span></span><span>at <b>${cents(s.best_ask)}</b></span><span><b>${usd(s.depth_usd)}</b> avail.</span></div>
        <div class="yield">${pct(s.gain_taker_pct)}</div>
      </div>
    </button>`).join("");
}

function renderCopy() {
  const all = (state.data && state.data.copy) || [];
  const wallets = (state.data && state.data.wallets) || [];
  const wf = $("#wallet-filter");
  if (!wf.dataset.built && wallets.length) {
    wallets.forEach((w) => state.walletOn.add(w.label));
    wf.innerHTML = wallets.map((w) => `<button class="chip on" data-wallet="${esc(w.label)}">${esc(w.label)}</button>`).join("");
    wf.dataset.built = "1";
  }
  const list = all.filter((s) => state.walletOn.has(s.wallet));
  $("#n-copy").textContent = list.length || "";
  const box = $("#list-copy");
  if (!list.length) { box.innerHTML = `<div class="empty">No large trades from these wallets yet.<br>New ones appear within ~5 minutes.</div>`; return; }
  box.innerHTML = list.map((s) => `
    <button class="card" data-kind="copy" data-id="${esc(s.id)}">
      <div class="line1"><span class="tag t-wallet">${esc(s.wallet)}</span><span class="muted">${ago(s.last_ts)}</span></div>
      <div class="q">${esc(s.question)}</div>
      <div class="line1">
        <div class="meta"><span class="tag ${s.side === "SELL" ? "t-sell" : "t-buy"}">${esc(s.side)} ${esc(s.outcome)}</span>
          <span>${usd(s.usd)} at <b>${cents(s.avg_price)}</b></span>
          ${s.now_ask != null ? `<span>now ${cents(s.now_ask)}</span>` : ""}</div>
      </div>
    </button>`).join("");
}

/* ---------- detail sheet ---------- */
function openSheet(html) { $("#sheet-content").innerHTML = html; $("#sheet").hidden = false; }
function closeSheet() { $("#sheet").hidden = true; }

async function liveBook(token) {
  try {
    const b = await getJSON(`${CLOB}/book?token_id=${encodeURIComponent(token)}`);
    const bids = (b.bids || []).map((x) => +x.price).sort((a, c) => c - a);
    const asks = (b.asks || []).map((x) => +x.price).sort((a, c) => a - c);
    return { bid: bids[0] ?? null, ask: asks[0] ?? null };
  } catch { return null; }
}

function tradeForm(sig, price) {
  return `
    <div class="live" id="live-line">Live price: checking…</div>
    <div class="row"><input id="amt" type="number" inputmode="decimal" min="1" placeholder="Amount in $" value="100"></div>
    <button class="btn" id="act-open" ${state.live ? "" : "disabled"}>${state.live ? "Open market on Polymarket" : "Trading not available here (paper mode)"}</button>
    <button class="btn ghost" id="act-copy">Copy limit price ${cents(price)}</button>
    <button class="btn ghost" id="act-log">${state.live ? "Log this trade" : "Log paper trade"}</button>`;
}

function showSniper(s) {
  const pay = 1 - s.best_ask;
  openSheet(`
    <span class="tag t-${esc(s.confidence)}">${esc(s.confidence)} confidence</span>
    <h2>${esc(s.question)}</h2>
    <div class="big-action"><div class="what">BUY ${esc(s.outcome)}</div>
      <div class="sub">Limit ${cents(s.suggested_limit)} to pay no fee, or take ${cents(s.best_ask)} now</div></div>
    <div class="grid">
      <div class="stat"><div class="k">Gain buying now</div><div class="v pos">${pct(s.gain_taker_pct)}</div></div>
      <div class="stat"><div class="k">Gain at limit (if filled)</div><div class="v pos">${pct(s.gain_maker_pct)}</div></div>
      <div class="stat"><div class="k">Est. time to payout</div><div class="v">${s.est_days.toFixed(1)} days</div></div>
      <div class="stat"><div class="k">Annualized</div><div class="v">${Math.round(s.annual_yield_taker * 100)}%</div></div>
      <div class="stat"><div class="k">Available at ask</div><div class="v">${usd(s.depth_usd)}</div></div>
      <div class="stat"><div class="k">Max loss per $1</div><div class="v neg">−$${s.best_ask.toFixed(3)}</div></div>
    </div>
    <ul class="why">${(s.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    ${tradeForm(s, s.suggested_limit)}
    <p class="risk">You win ${cents(pay)} per share if "${esc(s.outcome)}" is confirmed; you lose your full stake if the market resolves the other way or is disputed. Check the result yourself before buying.</p>`);
  wireTrade({ kind: "sniper", sig: s, token: s.token_id, outcome: s.outcome, defaultPrice: s.best_ask, limit: s.suggested_limit });
}

function showCopy(s) {
  const w = ((state.data && state.data.wallets) || []).find((x) => x.label === s.wallet) || {};
  const note = /ladder/.test(w.style || "")
    ? "This trader often holds both sides of a market and flips positions. A single buy can be a hedge, not a fresh view."
    : "This trader buys near-certain outcomes after the event. Copying only works while the price is still below $1.";
  openSheet(`
    <span class="tag t-wallet">${esc(s.wallet)} · ${esc(w.style || "")}</span>
    <h2>${esc(s.question)}</h2>
    <div class="big-action ${s.side === "SELL" ? "sell" : ""}"><div class="what">${esc(s.side)} ${esc(s.outcome)}</div>
      <div class="sub">${esc(s.wallet)} traded ${usd(s.usd)} at avg ${cents(s.avg_price)} · ${ago(s.last_ts)}</div></div>
    <div class="grid">
      <div class="stat"><div class="k">Their avg price</div><div class="v">${cents(s.avg_price)}</div></div>
      <div class="stat"><div class="k">Ask at scan</div><div class="v">${cents(s.now_ask)}</div></div>
      <div class="stat"><div class="k">Size</div><div class="v">${usd(s.usd)}</div></div>
      <div class="stat"><div class="k">Fills</div><div class="v">${s.fills}</div></div>
    </div>
    <ul class="why"><li>${esc(note)}</li>${s.slippage_c != null ? `<li>Price has moved ${s.slippage_c > 0 ? "up" : "down"} ${Math.abs(s.slippage_c).toFixed(1)}¢ since their trade.</li>` : ""}</ul>
    ${tradeForm(s, s.now_ask ?? s.avg_price)}
    <p class="risk">Copying is not a guarantee: you see the trade minutes after it happened, at a worse price, without knowing their exit.</p>`);
  wireTrade({ kind: "copy", sig: s, token: s.token_id, outcome: s.outcome, defaultPrice: s.now_ask ?? s.avg_price, limit: s.now_ask ?? s.avg_price });
}

async function wireTrade(o) {
  let price = o.defaultPrice;
  const book = await liveBook(o.token);
  const line = $("#live-line");
  if (line) {
    if (book && book.ask != null) { price = book.ask; line.textContent = `Live price: bid ${cents(book.bid)} · ask ${cents(book.ask)}`; }
    else line.textContent = "Live price unavailable; using the price from the last scan.";
  }
  $("#act-open").onclick = () => openUrl(o.sig.url);
  $("#act-copy").onclick = () => copyText(String(o.limit));
  $("#act-log").onclick = () => {
    const amt = parseFloat($("#amt").value);
    if (!(amt > 0) || !(price > 0)) return toast("Enter an amount");
    const trades = loadTrades();
    trades.unshift({ id: `${Date.now()}`, kind: o.kind, mode: state.live ? "live" : "paper", ts: Date.now(),
      question: o.sig.question, outcome: o.outcome, token_id: o.token, condition_id: o.sig.condition_id,
      url: o.sig.url, price, amount: amt, shares: amt / price, source: o.sig.wallet || "sniper", status: "open" });
    saveTrades(trades); closeSheet(); renderTrades(); toast("Trade logged"); refreshTrades();
  };
}

/* ---------- trades & scorecard ---------- */
async function refreshTrades() {
  const trades = loadTrades();
  const open = trades.filter((t) => t.status === "open" && t.condition_id);
  const ids = [...new Set(open.map((t) => t.condition_id))];
  for (let i = 0; i < ids.length; i += 20) {
    try {
      const ms = await getJSON(`${GAMMA}/markets?condition_ids=${ids.slice(i, i + 20).join(",")}&limit=50`);
      for (const m of ms || []) {
        const outs = JSON.parse(m.outcomes || "[]"), px = JSON.parse(m.outcomePrices || "[]").map(Number);
        for (const t of open.filter((x) => x.condition_id === m.conditionId)) {
          const k = outs.indexOf(t.outcome); if (k < 0) continue;
          t.mark = px[k];
          if (m.closed && (px[k] >= 0.99 || px[k] <= 0.01)) { t.status = px[k] >= 0.99 ? "won" : "lost"; t.settled = px[k] >= 0.99 ? 1 : 0; }
        }
      }
    } catch {}
  }
  saveTrades(trades); renderTrades();
}

function renderTrades() {
  const trades = loadTrades();
  $("#n-paper").textContent = trades.length || "";
  const pnl = (t) => t.status === "open" ? (t.mark != null ? t.shares * t.mark - t.amount : 0) : t.shares * t.settled - t.amount;
  const closed = trades.filter((t) => t.status !== "open");
  const realized = closed.reduce((a, t) => a + pnl(t), 0);
  const openPnl = trades.filter((t) => t.status === "open").reduce((a, t) => a + pnl(t), 0);
  const wins = closed.filter((t) => t.status === "won").length;
  $("#scorecard").innerHTML = `
    <div class="stat"><div class="k">Realized</div><div class="v ${realized >= 0 ? "pos" : "neg"}">${realized >= 0 ? "+" : "−"}$${Math.abs(realized).toFixed(2)}</div></div>
    <div class="stat"><div class="k">Open (marked)</div><div class="v ${openPnl >= 0 ? "pos" : "neg"}">${openPnl >= 0 ? "+" : "−"}$${Math.abs(openPnl).toFixed(2)}</div></div>
    <div class="stat"><div class="k">Win rate</div><div class="v">${closed.length ? Math.round((100 * wins) / closed.length) + "%" : "–"}</div></div>`;
  const box = $("#list-paper");
  if (!trades.length) { box.innerHTML = `<div class="empty">No trades logged yet.<br>Open a signal and tap “Log trade”.</div>`; return; }
  box.innerHTML = trades.map((t) => {
    const p = pnl(t);
    return `<div class="card">
      <div class="line1"><span class="tag ${t.mode === "live" ? "t-high" : "t-low"}">${t.mode}</span>
        <span class="tag ${t.status === "won" ? "t-high" : t.status === "lost" ? "t-sell" : "t-medium"}">${t.status}</span>
        <span class="muted">${ago(t.ts / 1000)}</span></div>
      <div class="q">${esc(t.question)}</div>
      <div class="line1"><div class="meta"><span>${esc(t.outcome)} @ <b>${cents(t.price)}</b></span><span>${usd(t.amount)}</span><span>${esc(t.source)}</span></div>
        <div class="${p >= 0 ? "pos" : "neg"}" style="font-weight:700">${p >= 0 ? "+" : "−"}$${Math.abs(p).toFixed(2)}</div></div>
      <div class="row" style="margin-top:6px"><button class="btn small ghost" data-del="${esc(t.id)}">Remove</button></div>
    </div>`;
  }).join("");
}

/* ---------- events ---------- */
document.addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (tab) {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === tab));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`));
    if (tab.dataset.tab === "paper") refreshTrades();
    return;
  }
  const card = e.target.closest(".card[data-kind]");
  if (card) {
    const list = (state.data && state.data[card.dataset.kind]) || [];
    const s = list.find((x) => x.id === card.dataset.id);
    if (s) (card.dataset.kind === "sniper" ? showSniper : showCopy)(s);
    return;
  }
  const chip = e.target.closest("[data-wallet]");
  if (chip) {
    const w = chip.dataset.wallet;
    state.walletOn.has(w) ? state.walletOn.delete(w) : state.walletOn.add(w);
    chip.classList.toggle("on"); renderCopy(); return;
  }
  const del = e.target.closest("[data-del]");
  if (del) { saveTrades(loadTrades().filter((t) => t.id !== del.dataset.del)); renderTrades(); return; }
  if (e.target.closest("[data-close]")) closeSheet();
});
$("#hide-low").onchange = renderSniper;
$("#sort-sniper").onchange = renderSniper;
$("#refresh").onclick = () => { toast("Refreshing…"); loadSignals(); checkGeo(); };
$("#topic").textContent = NTFY_TOPIC;
$("#copy-topic").onclick = () => copyText(NTFY_TOPIC);
$("#open-ntfy").onclick = () => openUrl(`https://ntfy.sh/${NTFY_TOPIC}`);
document.addEventListener("visibilitychange", () => { if (!document.hidden) { loadSignals(); checkGeo(); } });

checkGeo();
loadSignals();
refreshTrades();
setInterval(loadSignals, 60000);
