/* BTC 5-minute Up/Down: live fair value from the Chainlink 60s-TWAP settlement rule, compared with
   the Polymarket order book every second. Tells you UP / DOWN / SKIP; you place the trade yourself.
   Maths (see btc5m/model.py in the repo):
     strike K = average BTC price over the 60s before the window opens
     final F  = average BTC price over the last 60s of the window;  Up wins if F >= K
     tau <= 240s: F - x ~ N(0, sig^2 (260 - tau))
     tau  > 240s: F = ((tau-240)*A + r*x)/60 + N(0, sig^2 r^3/3 / 3600),  r = 300 - tau
   Binance is the price proxy; BASIS_SD covers the gap to Chainlink (measured on 577 windows). */
(() => {
  const BIN = ["https://api.binance.com", "https://data-api.binance.vision"];
  const BASIS_SD = 4.15, FEE_RATE = 0.07, SIG_LOOK = 900;
  const CFG_KEY = "btc5m_cfg_v2", SHADOW_KEY = "btc5m_shadow_v1";
  const cfg = Object.assign({ edge: 0.05, minTau: 240, maxTau: 280, hold: 3, maxPrice: 0.95, vibrate: true },
    (() => { try { return JSON.parse(localStorage.getItem(CFG_KEY) || "{}"); } catch { return {}; } })());
  const saveCfg = () => { try { localStorage.setItem(CFG_KEY, JSON.stringify(cfg)); } catch {} };

  const px = new Map();           // second -> BTC mid
  const meta = new Map();         // window start -> {tokens, conditionId, ptb}
  let streak = { side: null, n: 0 }, lastAlert = null, running = false, view = null, binHost = 0;

  const ncdf = (z) => { // Abramowitz-Stegun erf
    const t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2);
    const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z / 2);
    return 0.5 * (1 + (z >= 0 ? y : -y));
  };
  const fee = (p) => FEE_RATE * p * (1 - p);
  const nowS = () => Math.floor(Date.now() / 1000);
  const avg = (a, b) => { let s = 0, n = 0; for (let t = a; t < b; t++) if (px.has(t)) { s += px.get(t); n++; } return n ? s / n : null; };
  const fmtT = (s) => new Date(s * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const usd2 = (n) => (n >= 0 ? "+" : "−") + "$" + Math.abs(n).toFixed(0);

  async function j(url, opts) {
    const r = await fetch(url, Object.assign({ headers: { Accept: "application/json" } }, opts || {}));
    if (!r.ok) throw new Error(r.status); return r.json();
  }
  async function binance(path) {
    for (let k = 0; k < BIN.length; k++) {
      const h = BIN[(binHost + k) % BIN.length];
      try { const d = await j(h + path); binHost = (binHost + k) % BIN.length; return d; } catch {}
    }
    throw new Error("binance");
  }
  async function backfill() { // last ~16 min of 1-second closes
    const d = await binance("/api/v3/klines?symbol=BTCUSDT&interval=1s&limit=1000");
    for (const k of d) px.set(Math.floor(k[0] / 1000), +k[4]);
  }
  async function getWin(start) {
    if (meta.has(start)) return meta.get(start);
    const e = await j(`https://gamma-api.polymarket.com/events/slug/btc-updown-5m-${start}`);
    const m = e.markets[0];
    const v = { tokens: JSON.parse(m.clobTokenIds), conditionId: m.conditionId, question: m.question,
      ptb: (e.eventMetadata || {}).priceToBeat };
    meta.set(start, v); return v;
  }
  async function books(tokens) {
    const b = await j("https://clob.polymarket.com/books", { method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(tokens.map((t) => ({ token_id: t }))) });
    const by = Object.fromEntries(b.map((x) => [x.asset_id, x]));
    const best = (x, side) => {
      const l = ((x || {})[side] || []).map((o) => [+o.price, +o.size]).sort((a, c) => side === "asks" ? a[0] - c[0] : c[0] - a[0]);
      return l[0] || null;
    };
    return { upAsk: best(by[tokens[0]], "asks"), upBid: best(by[tokens[0]], "bids"),
      dnAsk: best(by[tokens[1]], "asks"), dnBid: best(by[tokens[1]], "bids") };
  }
  function sigma() {
    const t1 = nowS(), r = [];
    for (let t = t1 - SIG_LOOK; t < t1; t++) if (px.has(t) && px.has(t - 1)) r.push(px.get(t) - px.get(t - 1));
    if (r.length < 120) return null;
    return Math.sqrt(r.reduce((a, x) => a + x * x, 0) / r.length);
  }
  function fair(start, tau, x, sig) {
    const K = avg(start - 60, start);
    if (K == null) return null;
    let mu, sd;
    if (tau <= 240) { mu = x; sd = sig * Math.sqrt(260 - tau); }
    else { const A = avg(start + 240, start + tau) ?? x, r = 300 - tau; mu = ((tau - 240) * A + r * x) / 60; sd = sig * Math.sqrt(r ** 3 / 3) / 60; }
    return { K, pUp: ncdf((mu - K) / Math.sqrt(sd * sd + BASIS_SD * BASIS_SD)) };
  }

  /* ---------- shadow log: every signal the app shows is recorded and scored automatically ---------- */
  const loadShadow = () => { try { return JSON.parse(localStorage.getItem(SHADOW_KEY) || "[]"); } catch { return []; } };
  const saveShadow = (s) => { try { localStorage.setItem(SHADOW_KEY, JSON.stringify(s.slice(0, 500))); } catch {} };
  async function settleShadow() {
    const s = loadShadow(); let changed = false;
    for (const x of s.filter((y) => y.result == null && y.start + 330 < nowS()).slice(0, 5)) {
      try {
        const e = await j(`https://gamma-api.polymarket.com/events/slug/btc-updown-5m-${x.start}`);
        const op = JSON.parse(e.markets[0].outcomePrices || "[]");
        if (op[0] === "1" || op[0] === "0") { const up = op[0] === "1"; x.result = (x.side === "UP") === up ? "won" : "lost"; changed = true; }
      } catch {}
    }
    if (changed) saveShadow(s);
  }

  /* ---------- tick ---------- */
  async function tick() {
    const t = nowS(), start = Math.floor(t / 300) * 300, tau = t - start;
    try { const b = await binance("/api/v3/ticker/bookTicker?symbol=BTCUSDT"); px.set(t, (+b.bidPrice + +b.askPrice) / 2); }
    catch { view = { err: "Can't reach Binance for the BTC price." }; return render(); }
    for (const k of px.keys()) if (k < t - 1300) px.delete(k);
    if (!px.has(start - 60) || !px.has(start - 1)) { try { await backfill(); } catch {} }
    let m, bk;
    try { m = await getWin(start); bk = await books(m.tokens); }
    catch { view = { err: "Can't reach Polymarket for this window yet." }; return render(); }
    const sig = sigma(), x = px.get(t - 1) ?? px.get(t);
    const f = sig && x ? fair(start, tau, x, sig) : null;
    const v = { start, tau, x, sig, m, bk, f, sides: [] };
    if (f) {
      for (const [side, ask, p] of [["UP", bk.upAsk, f.pUp], ["DOWN", bk.dnAsk, 1 - f.pUp]]) {
        if (!ask) continue;
        const edge = p - ask[0] - fee(ask[0]);
        // most you should pay: keep cfg.edge after the taker fee
        let lim = null; for (let q = 0.99; q >= 0.01; q -= 0.01) if (p - q - fee(q) >= cfg.edge) { lim = Math.round(q * 100) / 100; break; }
        v.sides.push({ side, ask: ask[0], depth: ask[1], p, edge, lim });
      }
      const best = v.sides.slice().sort((a, b) => b.edge - a.edge)[0];
      const ok = best && best.edge >= cfg.edge && best.ask <= cfg.maxPrice && tau >= cfg.minTau && tau <= cfg.maxTau;
      streak = ok ? (streak.side === best.side ? { side: best.side, n: streak.n + 1 } : { side: best.side, n: 1 }) : { side: null, n: 0 };
      v.signal = ok && streak.n >= cfg.hold ? best : null;
      if (v.signal && lastAlert !== `${start}:${best.side}`) {
        lastAlert = `${start}:${best.side}`;
        if (cfg.vibrate && navigator.vibrate) navigator.vibrate([120, 60, 120]);
        const s = loadShadow();
        s.unshift({ start, side: best.side, tau, price: best.ask, fair: +best.p.toFixed(4), edge: +best.edge.toFixed(4), ts: Date.now() });
        saveShadow(s);
      }
    }
    view = v; render();
    if (tau % 15 === 0) settleShadow();
  }
  async function loop() {
    if (running) return; running = true;
    try { await backfill(); } catch {}
    while (running) {
      const t0 = Date.now();
      try { await tick(); } catch {}
      await new Promise((r) => setTimeout(r, Math.max(150, 1000 - (Date.now() - t0))));
    }
  }
  const stop = () => { running = false; };

  /* ---------- UI ---------- */
  function shadowStats() {
    const s = loadShadow().filter((x) => x.result);
    let pnl = 0, won = 0; for (const x of s) { const w = x.result === "won"; won += w; pnl += (w ? 1 : 0) - x.price - fee(x.price); }
    return { n: s.length, won, pnl, roi: s.length ? pnl / s.reduce((a, x) => a + x.price, 0) : null };
  }
  function render() {
    const box = document.querySelector("#b5-live"); if (!box) return;
    if (!view) { box.innerHTML = `<div class="empty">Starting…</div>`; return; }
    if (view.err) { box.innerHTML = `<div class="empty">${view.err}<br>Retrying every second.</div>`; return; }
    const { start, tau, x, f, sides, bk, sig } = view, left = 300 - tau;
    const phase = tau < cfg.minTau ? (cfg.minTau >= 240 ? "Waiting for the final minute (earlier calls lost money in testing)" : "Too early — strike just set") : tau > cfg.maxTau ? "Too late to act by hand" : tau > 240 ? "Final minute: averaging has started" : "Open";
    const sig2 = view.signal;
    const verdict = !f ? `<div class="big-action neutral"><div class="what">Warming up</div><div class="sub">Need ~2 min of BTC prices and the 60s before this window opened.</div></div>`
      : sig2 ? `<div class="big-action ${sig2.side === "DOWN" ? "sell" : ""}"><div class="what">BUY ${sig2.side} · pay up to ${Math.round(sig2.lim * 100)}¢</div>
          <div class="sub">Model ${Math.round(sig2.p * 100)}% vs ask ${Math.round(sig2.ask * 100)}¢ · edge ${(sig2.edge * 100).toFixed(1)}¢/share after fee · ${Math.round(sig2.depth)} shares at ask</div></div>`
      : `<div class="big-action neutral"><div class="what">SKIP</div><div class="sub">${tau >= cfg.minTau && tau <= cfg.maxTau ? `No side has ≥ ${Math.round(cfg.edge * 100)}¢ edge after fees${streak.n ? ` (building: ${streak.side} ${streak.n}/${cfg.hold}s)` : ""}.` : phase + "."}</div></div>`;
    const d = f ? x - f.K : null;
    const st = shadowStats();
    box.innerHTML = `
      <div class="card">
        <div class="line1"><span class="tag t-medium">${fmtT(start)}–${fmtT(start + 300)}</span><span class="muted">${phase}</span></div>
        <div class="clock"><span class="cd">${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}</span><span class="muted">left</span>
          <div class="bar"><i style="width:${(tau / 300) * 100}%"></i><b style="left:${(240 / 300) * 100}%"></b></div></div>
        <div class="grid">
          <div class="stat"><div class="k">BTC vs strike</div><div class="v ${d == null ? "" : d >= 0 ? "pos" : "neg"}">${d == null ? "–" : usd2(d)}</div></div>
          <div class="stat"><div class="k">Model P(Up)</div><div class="v">${f ? Math.round(f.pUp * 100) + "%" : "–"}</div></div>
          ${sides.map((s) => `<div class="stat"><div class="k">${s.side} ask · edge</div><div class="v">${Math.round(s.ask * 100)}¢ <span class="${s.edge >= 0 ? "pos" : "neg"}" style="font-size:13px">${s.edge >= 0 ? "+" : ""}${(s.edge * 100).toFixed(1)}¢</span></div></div>`).join("")}
        </div>
      </div>
      ${verdict}
      <button class="btn" id="b5-open">Open this window on Polymarket</button>
      ${sig2 ? `<button class="btn ghost" id="b5-log">Log ${sig2.side} @ ${Math.round(sig2.ask * 100)}¢ as a trade</button>` : ""}
      <div class="card">
        <div class="line1"><b>Every signal so far (auto-scored)</b><span class="muted">${st.n} settled</span></div>
        <div class="meta" style="margin-top:6px"><span>Won <b>${st.won}/${st.n}</b></span><span>P&amp;L per share <b class="${st.pnl >= 0 ? "pos" : "neg"}">${st.pnl >= 0 ? "+" : ""}${st.pnl.toFixed(2)}</b></span><span>ROI <b>${st.roi == null ? "–" : (st.roi * 100).toFixed(1) + "%"}</b></span></div>
        <p class="muted" style="font-size:12px;margin:6px 0 0">Counts every BUY the app shows, at the ask it showed, minus fees. Trust this tally over any backtest; give it 100+ signals before risking money.</p>
      </div>

`;
    const sg = document.querySelector("#b5-sig"); if (sg) sg.textContent = `σ now ${sig ? sig.toFixed(2) : "–"} $/√s · Polymarket (Chainlink) strike ${view.m.ptb ? "$" + Number(view.m.ptb).toFixed(2) : "not published yet"}`;
    document.querySelector("#b5-open").onclick = () => (window.openUrl || ((u) => window.open(u, "_blank")))(`https://polymarket.com/event/btc-updown-5m-${start}`);
    const lg = document.querySelector("#b5-log");
    if (lg && sig2) lg.onclick = () => {
      const amt = parseFloat(prompt("Amount in $", "10") || "0"); if (!(amt > 0)) return;
      const tr = JSON.parse(localStorage.getItem("pm_trades_v1") || "[]");
      tr.unshift({ id: `${Date.now()}`, kind: "btc5m", mode: "paper", ts: Date.now(), question: view.m.question, outcome: sig2.side === "UP" ? "Up" : "Down",
        token_id: view.m.tokens[sig2.side === "UP" ? 0 : 1], condition_id: view.m.conditionId, url: `https://polymarket.com/event/btc-updown-5m-${start}`,
        price: sig2.ask, amount: amt, shares: amt / sig2.ask, source: "btc5m", status: "open" });
      localStorage.setItem("pm_trades_v1", JSON.stringify(tr)); if (window.toast) window.toast("Trade logged");
    };
  }
  function bindSettings() {
    const bind = (id, k, scale = 1) => { const el = document.querySelector(id); if (!el) return;
      if (el.type === "checkbox") el.checked = !!cfg[k]; else el.value = Math.round(cfg[k] * scale);
      el.onchange = () => { cfg[k] = el.type === "checkbox" ? el.checked : +el.value / scale; saveCfg(); }; };
    bind("#b5-edge", "edge", 100); bind("#b5-min", "minTau"); bind("#b5-max", "maxTau"); bind("#b5-hold", "hold"); bind("#b5-vib", "vibrate");
  }
  bindSettings();
  window.btc5m = { start: loop, stop };
})();
