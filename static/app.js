const PRESETS = [
  ["株", [["トヨタ", "7203.T"], ["ソニーG", "6758.T"], ["三菱UFJ", "8306.T"],
    ["Apple", "AAPL"], ["NVIDIA", "NVDA"], ["Microsoft", "MSFT"]]],
  ["指数", [["日経平均", "^N225"], ["S&P500", "^GSPC"], ["NASDAQ", "^IXIC"]]],
  ["為替", [["USD/JPY", "JPY=X"], ["EUR/JPY", "EURJPY=X"], ["GBP/JPY", "GBPJPY=X"], ["AUD/JPY", "AUDJPY=X"],
    ["CHF/JPY", "CHFJPY=X"], ["EUR/USD", "EURUSD=X"], ["GBP/USD", "GBPUSD=X"], ["USD/CNY", "CNY=X"],
    ["ドル指数", "DX-Y.NYB"]]],
  ["暗号資産", [["Bitcoin", "BTC-USD"], ["BTC/円", "BTC-JPY"], ["Ethereum", "ETH-USD"], ["XRP", "XRP-USD"],
    ["Solana", "SOL-USD"], ["BNB", "BNB-USD"], ["Dogecoin", "DOGE-USD"], ["Cardano", "ADA-USD"], ["Litecoin", "LTC-USD"]]],
];
const LS_KEY = "marketlens.watchlist";
const $ = (id) => document.getElementById(id);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

let current = null;

// ---------- utils ----------
function fmt(v, digits) {
  if (v == null || isNaN(v)) return "—";
  const d = digits ?? (Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 10 ? 2 : 4);
  return Number(v).toLocaleString("ja-JP", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function pct(v) {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}
function cls(v) { return v > 0 ? "up" : v < 0 ? "down" : ""; }
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 3500);
}
function loadWatch() {
  try { return JSON.parse(localStorage.getItem(LS_KEY)) || ["7203.T", "NVDA", "BTC-USD", "JPY=X"]; }
  catch { return ["7203.T", "NVDA", "BTC-USD", "JPY=X"]; }
}
function saveWatch(list) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(list)); } catch {}
}

// ---------- charts ----------
const baseOpts = () => ({
  layout: { background: { color: "transparent" }, textColor: css("--muted"), fontFamily: css("--mono") },
  grid: { vertLines: { color: "#1a2234" }, horzLines: { color: "#1a2234" } },
  rightPriceScale: { borderColor: css("--line") },
  // 全期間（数千〜1万本以上）でも1画面に収められるようにする
  timeScale: { borderColor: css("--line"), minBarSpacing: 0.01 },
  crosshair: { mode: 0 },
  autoSize: true,
});

const LC = LightweightCharts;
const mainChart = LC.createChart($("chart-main"), baseOpts());
const volChart = LC.createChart($("chart-vol"), { ...baseOpts(), timeScale: { visible: false, minBarSpacing: 0.01 } });
const rsiChart = LC.createChart($("chart-rsi"), { ...baseOpts(), timeScale: { visible: false, minBarSpacing: 0.01 } });
const macdChart = LC.createChart($("chart-macd"), { ...baseOpts(), timeScale: { visible: false, minBarSpacing: 0.01 } });

const S = {
  candle: mainChart.addCandlestickSeries({
    upColor: css("--up"), downColor: css("--down"), borderVisible: false,
    wickUpColor: css("--up"), wickDownColor: css("--down"),
  }),
  volume: volChart.addHistogramSeries({ priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false }),
  VOL_MA20: volChart.addLineSeries({ color: css("--sma50"), lineWidth: 1, priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false }),
  SMA20: mainChart.addLineSeries({ color: css("--sma20"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
  SMA50: mainChart.addLineSeries({ color: css("--sma50"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
  SMA200: mainChart.addLineSeries({ color: css("--sma200"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
  BB_UP: mainChart.addLineSeries({ color: css("--bb"), lineWidth: 1, lineStyle: LC.LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false }),
  BB_LO: mainChart.addLineSeries({ color: css("--bb"), lineWidth: 1, lineStyle: LC.LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false }),
  FC_MID: mainChart.addLineSeries({ color: css("--fc"), lineWidth: 2, priceLineVisible: false }),
  FC_U68: mainChart.addLineSeries({ color: "rgba(245,185,66,.55)", lineWidth: 1, lineStyle: LC.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }),
  FC_L68: mainChart.addLineSeries({ color: "rgba(245,185,66,.55)", lineWidth: 1, lineStyle: LC.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }),
  FC_U95: mainChart.addLineSeries({ color: "rgba(245,185,66,.25)", lineWidth: 1, lineStyle: LC.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }),
  FC_L95: mainChart.addLineSeries({ color: "rgba(245,185,66,.25)", lineWidth: 1, lineStyle: LC.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }),
  RSI: rsiChart.addLineSeries({ color: "#a78bfa", lineWidth: 1, priceLineVisible: false }),
  MACD: macdChart.addLineSeries({ color: css("--sma20"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
  MACD_SIG: macdChart.addLineSeries({ color: css("--sma50"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
  MACD_HIST: macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }),
};
S.RSI.createPriceLine({ price: 70, color: "rgba(239,68,68,.5)", lineStyle: LC.LineStyle.Dashed, axisLabelVisible: false });
S.RSI.createPriceLine({ price: 30, color: "rgba(34,197,94,.5)", lineStyle: LC.LineStyle.Dashed, axisLabelVisible: false });

// 3つのチャートの横スクロールを同期
const charts = [mainChart, volChart, rsiChart, macdChart];
let syncing = false;
charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((r) => {
  if (syncing || !r) return;
  syncing = true;
  charts.forEach((o) => o !== c && o.timeScale().setVisibleLogicalRange(r));
  syncing = false;
}));

function applyToggles() {
  const on = {};
  document.querySelectorAll("#toggles input").forEach((i) => (on[i.dataset.k] = i.checked));
  ["SMA20", "SMA50", "SMA200"].forEach((k) => S[k].applyOptions({ visible: on[k] }));
  ["BB_UP", "BB_LO"].forEach((k) => S[k].applyOptions({ visible: on.BB }));
  ["FC_MID", "FC_U68", "FC_L68", "FC_U95", "FC_L95"].forEach((k) => S[k].applyOptions({ visible: on.FC }));
}
document.querySelectorAll("#toggles input").forEach((i) => i.addEventListener("change", applyToggles));

function renderCharts(d) {
  const precision = d.last >= 1000 ? 0 : d.last >= 10 ? 2 : 4;
  const pf = { type: "price", precision, minMove: 1 / 10 ** precision };
  S.candle.applyOptions({ priceFormat: pf });

  // 日足(日付)と分足(UNIX秒)で時刻の型が変わるため、先に全系列を空にする
  Object.values(S).forEach((s) => s.setData([]));
  S.candle.setData(d.candles);
  const up = css("--up"), down = css("--down");
  S.volume.setData(d.volume.map((v, i) => ({
    ...v, color: (d.candles[i].close >= d.candles[i].open ? up : down) + "40",
  })));
  for (const k of ["SMA20", "SMA50", "SMA200", "BB_UP", "BB_LO", "RSI", "MACD", "MACD_SIG", "VOL_MA20"]) {
    S[k].setData(d.indicators[k]);
  }
  S.MACD_HIST.setData(d.indicators.MACD_HIST.map((p) => ({ ...p, color: p.value >= 0 ? up + "99" : down + "99" })));

  // 予測線は日足のみ。最終終値から接続
  const fcKeys = { FC_MID: "mid", FC_U68: "upper68", FC_L68: "lower68", FC_U95: "upper95", FC_L95: "lower95" };
  const anchor = { time: d.candles.at(-1).time, value: d.last };
  S.FC_MID.applyOptions({ priceFormat: pf });
  for (const [k, f] of Object.entries(fcKeys)) {
    S[k].setData(d.interval === "1d" ? [anchor, ...d.forecast[f]] : []);
  }

  applyToggles();
  const intraday = d.interval !== "1d";
  mainChart.applyOptions({ timeScale: { timeVisible: intraday, secondsVisible: false } });
  $("chart-note").textContent = intraday
    ? `${$("interval").selectedOptions[0].text}・最終 ${d.updated}（取引所の現地時刻）`
    : "";
  charts.forEach((c) => c.timeScale().fitContent());
}

// ---------- panels ----------
function renderPanels(d) {
  $("q-name").textContent = d.name;
  $("q-sym").textContent = `${d.symbol} ・ ${d.date}`;
  $("q-price").textContent = fmt(d.last);
  $("q-chg").textContent = pct(d.change_pct);
  $("q-chg").className = `q-chg mono ${cls(d.change_pct)}`;
  updateStar();

  const labels = { "1w": "1週間", "1m": "1ヶ月", "3m": "3ヶ月", "1y": "1年" };
  $("perf").innerHTML = Object.entries(labels).map(([k, l]) =>
    `<div><div class="k">${l}</div><div class="v ${cls(d.perf[k])}">${pct(d.perf[k])}</div></div>`).join("");

  const sg = d.signals;
  $("g-needle").style.left = `${(sg.score + 100) / 2}%`;
  $("sig-label").innerHTML = `<span class="${sg.score >= 30 ? "up" : sg.score <= -30 ? "down" : ""}">${sg.label}</span> <small class="mono" style="color:var(--muted);font-size:13px">${sg.score > 0 ? "+" : ""}${sg.score}</small>`;
  $("sig-list").innerHTML = sg.items.map((i) =>
    `<li><b>${i.name}</b><span class="${cls(i.score)}">${i.note}</span></li>`).join("");

  const vs = d.volume_stats;
  $("vol-stat").innerHTML = vs
    ? `${fmtVol(vs.last)}（20日平均の <span class="${vs.ratio >= 1.5 ? "up" : ""}">${vs.ratio ?? "—"}倍</span>）`
    : "（データなし）";
  renderFundamentals(d.fundamentals || {});

  const fc = d.forecast;
  $("fc-h").textContent = `${fc.horizon}日後`;
  $("fc-target").textContent = fmt(fc.target);
  $("fc-chg").textContent = pct(fc.change_pct);
  $("fc-chg").className = `v mono ${cls(fc.change_pct)}`;
  $("fc-prob").textContent = `${fc.prob_up}%`;
  $("fc-vol").textContent = `${fc.volatility_annual}%`;
  $("fc-range").textContent = `${fmt(fc.range95[0])} 〜 ${fmt(fc.range95[1])}`;
}

function fmtVol(v) {
  if (v == null) return "—";
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}兆`;
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}億`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(1)}万`;
  return fmt(v, 0);
}

function renderFundamentals(f) {
  const cur = f.currency === "JPY" ? "円" : f.currency === "USD" ? "ドル" : (f.currency || "");
  const rows = [
    ["時価総額", f.marketCap != null && `${fmtVol(f.marketCap)}${cur}`],
    ["PER（実績）", f.trailingPE != null && `${f.trailingPE.toFixed(1)}倍`],
    ["PER（予想）", f.forwardPE != null && `${f.forwardPE.toFixed(1)}倍`],
    ["PBR", f.priceToBook != null && `${f.priceToBook.toFixed(2)}倍`],
    ["EPS", f.trailingEps != null && fmt(f.trailingEps, 2)],
    ["ROE", f.returnOnEquity != null && `${(f.returnOnEquity * 100).toFixed(1)}%`],
    ["配当利回り", f.dividendYield != null && `${f.dividendYield.toFixed(2)}%`],
    ["ベータ", f.beta != null && f.beta.toFixed(2)],
    ["52週高値", f.fiftyTwoWeekHigh != null && fmt(f.fiftyTwoWeekHigh)],
    ["52週安値", f.fiftyTwoWeekLow != null && fmt(f.fiftyTwoWeekLow)],
    ["平均出来高", f.averageVolume ? fmtVol(f.averageVolume) : false],
    ["業種", f.industry || false],
  ].filter(([, v]) => v);
  $("fund-card").style.display = rows.length ? "" : "none";
  $("fund").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}

// ---------- interval / period ----------
const PERIODS = {
  daily: [["3mo", "3ヶ月"], ["6mo", "6ヶ月"], ["1y", "1年"], ["2y", "2年"], ["5y", "5年"], ["10y", "10年"], ["max", "全期間"]],
  // Yahoo Finance の取得上限：5分・15分足は約60日〜3ヶ月、1時間足は約2〜3年（「全期間」は取れる分すべて）
  "60m": [["1d", "1日"], ["5d", "5日"], ["1mo", "1ヶ月"], ["3mo", "3ヶ月"], ["6mo", "6ヶ月"], ["1y", "1年"], ["2y", "2年"], ["max", "全期間"]],
  short: [["1d", "1日"], ["5d", "5日"], ["1mo", "1ヶ月"], ["60d", "60日"], ["max", "全期間"]],
};
function setPeriodOptions() {
  const iv = $("interval").value;
  const intraday = iv !== "1d";
  const opts = PERIODS[iv === "1d" ? "daily" : iv === "60m" ? "60m" : "short"];
  const prev = $("period").value;
  $("period").innerHTML = opts.map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
  $("period").value = opts.some(([v]) => v === prev) ? prev : intraday ? "5d" : "1y";
  // 予測は日足チャートにのみ描画
  const fc = document.querySelector('#toggles input[data-k="FC"]').closest("label");
  fc.style.display = intraday ? "none" : "";
}

// ---------- load ----------
async function load(symbol) {
  symbol = symbol.trim().toUpperCase();
  if (!symbol) return;
  $("symbol").value = symbol;
  document.body.classList.add("loading");
  const params = new URLSearchParams({
    symbol, period: $("period").value, horizon: $("horizon").value, interval: $("interval").value,
  });
  try {
    const res = await fetch(`/api/analyze?${params}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || "取得に失敗しました");
    current = d;
    renderCharts(d);
    renderPanels(d);
    $("ai-out").innerHTML = "";
    loadNews(symbol);
    renderTechnical(d.technical);
    if (current.symbol !== $("fa-body").dataset.s) {
      $("fa-body").dataset.s = current.symbol;
      loadFundamental(symbol);
    }
    if (current.symbol !== $("bt-rows").dataset.s) resetBacktest();
    document.querySelectorAll("#presets button").forEach((b) => b.classList.toggle("active", b.dataset.s === symbol));
    const q = new URLSearchParams(location.search);
    q.set("s", symbol);
    history.replaceState(null, "", `?${q}`);
  } catch (e) {
    toast(e.message);
  } finally {
    document.body.classList.remove("loading");
  }
}

$("search").addEventListener("submit", (e) => { e.preventDefault(); load($("symbol").value); });
$("period").addEventListener("change", () => current && load(current.symbol));
$("horizon").addEventListener("change", () => current && load(current.symbol));
$("interval").addEventListener("change", () => { setPeriodOptions(); current && load(current.symbol); });

$("presets").innerHTML = PRESETS.map(([g, list]) =>
  `<span class="p-grp">${g}</span>${list.map(([n, s]) => `<button data-s="${s}">${n}</button>`).join("")}`).join("");
$("presets").addEventListener("click", (e) => { if (e.target.dataset.s) load(e.target.dataset.s); });

// ---------- backtest ----------
const BT_COLORS = { trend: "--sma20", reversion: "--sma200", buy_hold: "--muted" };
const btChart = LC.createChart($("chart-bt"), {
  ...baseOpts(),
  rightPriceScale: { borderColor: css("--line"), mode: LC.PriceScaleMode.Logarithmic },
});
const BT = Object.fromEntries(Object.entries(BT_COLORS).map(([k, c]) => [k, btChart.addLineSeries({
  color: css(c), lineWidth: k === "buy_hold" ? 1 : 2, priceLineVisible: false,
  lineStyle: k === "buy_hold" ? LC.LineStyle.Dashed : LC.LineStyle.Solid,
})]));

function resetBacktest() {
  $("bt-body").hidden = true;
  $("bt-note").textContent = "";
}

async function runBacktest() {
  if (!current) return;
  const btn = $("bt-btn");
  btn.disabled = true;
  btn.textContent = "検証中…";
  const params = new URLSearchParams({ symbol: current.symbol, period: $("bt-period").value, threshold: $("bt-th").value });
  try {
    const res = await fetch(`/api/backtest?${params}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || "バックテストに失敗しました");
    if (d.symbol !== current.symbol) return;
    renderBacktest(d);
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "検証する";
  }
}

function renderBacktest(d) {
  $("bt-rows").dataset.s = d.symbol;
  $("bt-note").textContent = `${d.from} 〜 ${d.to}`;
  const sign = (v) => (v > 0 ? "+" : "") + v;
  $("bt-rows").innerHTML = Object.keys(BT_COLORS).map((k) => [k, d.strategies[k]]).map(([k, s]) => `
    <tr class="${k === d.best ? "best" : ""}">
      <td><i style="background:${css(BT_COLORS[k])}"></i>${s.name}</td>
      <td class="${cls(s.cagr_pct)}">${sign(s.cagr_pct)}%</td>
      <td class="${cls(s.total_pct)}">${sign(s.total_pct)}%</td>
      <td>${s.sharpe ?? "—"}</td>
      <td class="down">${s.max_dd_pct}%</td>
      <td>${s.trades}回</td>
      <td>${s.exposure_pct}%</td>
    </tr>`).join("");
  $("bt-body").hidden = false;
  for (const [k, series] of Object.entries(BT)) series.setData(d.equity[k]);
  // 非表示から表示に切り替えた直後はサイズ確定を待ってから全期間を表示
  requestAnimationFrame(() => btChart.timeScale().fitContent());

  $("bt-h").textContent = d.horizon;
  $("bt-fwd").innerHTML = ["強気", "中立", "弱気"].map((lb) => {
    const f = d.forward_by_label[lb];
    if (!f) return `<div><div class="k">${lb}</div><div class="v">—</div></div>`;
    return `<div><div class="k">${lb} <small>(${f.count}日)</small></div>
      <div class="v ${cls(f.avg_pct)}">${pct(f.avg_pct)}</div><small>勝率 ${f.win_pct}%</small></div>`;
  }).join("");
}

$("bt-btn").addEventListener("click", runBacktest);
["bt-period", "bt-th"].forEach((id) => $(id).addEventListener("change", () => !$("bt-body").hidden && runBacktest()));

// ---------- AI ----------
const aiBtn = $("ai-btn");
if (aiBtn) {
  aiBtn.addEventListener("click", async () => {
    if (!current) return;
    aiBtn.disabled = true;
    aiBtn.textContent = "分析中…";
    $("ai-out").innerHTML = "";
    try {
      const res = await fetch("/api/ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: current.symbol, horizon: Number($("horizon").value) }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error || "AI分析に失敗しました");
      $("ai-out").innerHTML = DOMPurify.sanitize(marked.parse(d.comment));
    } catch (e) {
      toast(e.message);
    } finally {
      aiBtn.disabled = false;
      aiBtn.textContent = "Claudeで分析する";
    }
  });
}

// ---------- watchlist ----------
function updateStar() {
  const on = current && loadWatch().includes(current.symbol);
  $("star").textContent = on ? "★" : "☆";
  $("star").title = on ? "ウォッチリストから外す" : "ウォッチリストに追加";
}
$("star").addEventListener("click", () => {
  if (!current) return;
  const list = loadWatch();
  const i = list.indexOf(current.symbol);
  i >= 0 ? list.splice(i, 1) : list.push(current.symbol);
  saveWatch(list);
  updateStar();
  renderWatch();
});

function spark(values, color) {
  if (!values?.length) return "";
  const min = Math.min(...values), max = Math.max(...values), w = 64, h = 22;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * h}`).join(" ");
  return `<svg width="${w}" height="${h}"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/></svg>`;
}

async function renderWatch() {
  const list = loadWatch();
  $("watch-empty").style.display = list.length ? "none" : "block";
  if (!list.length) { $("watch").innerHTML = ""; return; }
  $("watch").innerHTML = list.map((s) => `<li data-s="${s}"><span class="w-sym">${s}</span><span></span><span class="w-px">…</span><button class="w-x" data-x="${s}">×</button></li>`).join("");
  try {
    const res = await fetch(`/api/quotes?symbols=${encodeURIComponent(list.join(","))}`);
    const quotes = await res.json();
    for (const q of quotes) {
      const li = $("watch").querySelector(`li[data-s="${CSS.escape(q.symbol)}"]`);
      if (!li) continue;
      if (q.error) { li.children[2].textContent = "取得失敗"; continue; }
      li.children[1].innerHTML = spark(q.spark, q.change_pct >= 0 ? css("--up") : css("--down"));
      li.children[2].innerHTML = `${fmt(q.last)}<br><span class="${cls(q.change_pct)}">${pct(q.change_pct)}</span>`;
    }
  } catch {}
}
$("watch").addEventListener("click", (e) => {
  if (e.target.dataset.x) {
    saveWatch(loadWatch().filter((s) => s !== e.target.dataset.x));
    updateStar();
    renderWatch();
    return;
  }
  const li = e.target.closest("li");
  if (li) load(li.dataset.s);
});

// ---------- correlation ----------
let corr = null;
let pair = null;
const pairChart = LC.createChart($("chart-pair"), {
  ...baseOpts(),
  timeScale: { borderColor: css("--line"), minBarSpacing: 0.01 },
});
const pairLine = pairChart.addBaselineSeries({
  baseValue: { type: "price", price: 0 },
  topLineColor: css("--accent"), topFillColor1: "rgba(245,185,66,.25)", topFillColor2: "rgba(245,185,66,0)",
  bottomLineColor: css("--sma20"), bottomFillColor1: "rgba(96,165,250,0)", bottomFillColor2: "rgba(96,165,250,.25)",
  lineWidth: 2, priceLineVisible: false,
  autoscaleInfoProvider: () => ({ priceRange: { minValue: -1, maxValue: 1 } }),
});

function setView(view) {
  document.body.classList.toggle("view-sub", view !== "analyze");
  $("corr-view").hidden = view !== "corr";
  $("policy-view").hidden = view !== "policy";
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  if (view === "corr" && !corr) loadCorrelation();
  if (view === "policy" && !policy) loadPolicy();
  // 非表示中に描画したチャートは幅0で計算されているため、表示後に合わせ直す
  const visible = { analyze: charts, corr: [pairChart] }[view] || [];
  requestAnimationFrame(() => visible.forEach((c) => c.timeScale().fitContent()));
}
$("tabs").addEventListener("click", (e) => {
  const v = e.target.dataset.view;
  if (!v) return;
  setView(v);
  const q = new URLSearchParams(location.search);
  v === "analyze" ? q.delete("view") : q.set("view", v);
  history.replaceState(null, "", `?${q}`);
});

function corrCell(v, a, b) {
  if (a === b) return `<td class="diag">—</td>`;
  if (v == null) return `<td class="diag">n/a</td>`;
  const c = v >= 0 ? "pos" : "neg";
  const sel = pair && ((pair[0] === a && pair[1] === b) || (pair[0] === b && pair[1] === a)) ? " sel" : "";
  return `<td class="${c}${Math.abs(v) >= 0.5 ? " strong" : ""}${sel}" style="--a:${(Math.abs(v) * 0.85).toFixed(2)}"
    data-a="${a}" data-b="${b}">${v > 0 ? "+" : ""}${v.toFixed(2)}</td>`;
}

async function loadCorrelation() {
  const params = new URLSearchParams({ period: $("corr-period").value, freq: $("corr-freq").value });
  $("corr-note").textContent = "読み込み中…";
  try {
    const res = await fetch(`/api/correlation?${params}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || "相関の取得に失敗しました");
    corr = d;
    renderCorrelation();
    loadPair(...(pair || ["^GSPC", "GC=F"]));
  } catch (e) {
    $("corr-note").textContent = "";
    toast(e.message);
  }
}

function renderCorrelation() {
  const d = corr;
  const unit = d.freq === "W" ? "週" : "日";
  $("corr-note").textContent = `${d.from} 〜 ${d.to}・${unit}次 ${d.n}本`;
  const assets = d.groups.flatMap((g) => g.assets.map((a) => ({ ...a, group: g.name })));
  const head1 = `<tr><th></th><th></th>${d.groups.map((g) => `<th class="grp" colspan="${g.assets.length}">${g.name}</th>`).join("")}</tr>`;
  const head2 = `<tr><th></th><th></th>${assets.map((a) => `<th>${a.name}</th>`).join("")}</tr>`;
  const body = d.groups.map((g) => g.assets.map((a, i) => `<tr>
      ${i === 0 ? `<th class="grp" rowspan="${g.assets.length}">${g.name}</th>` : ""}
      <th>${a.name}</th>${assets.map((b) => corrCell(d.matrix[a.symbol][b.symbol], a.symbol, b.symbol)).join("")}
    </tr>`).join("")).join("");
  $("corr-table").innerHTML = `<thead>${head1}${head2}</thead><tbody>${body}</tbody>`;

  const names = d.groups.map((g) => g.name);
  $("corr-avg").innerHTML = `<thead><tr><th></th>${names.map((n) => `<th>${n}</th>`).join("")}</tr></thead><tbody>${
    names.map((a) => `<tr><th>${a}</th>${names.map((b) => {
      const v = d.group_avg[a][b];
      return v == null ? `<td class="diag">—</td>` : `<td class="${v >= 0 ? "pos" : "neg"}" style="--a:${(Math.abs(v) * 0.85).toFixed(2)}">${v > 0 ? "+" : ""}${v.toFixed(2)}</td>`;
    }).join("")}</tr>`).join("")}</tbody>`;
}

async function loadPair(a, b) {
  pair = [a, b];
  if (corr) renderCorrelation();
  const params = new URLSearchParams({ a, b, period: $("corr-period").value, freq: $("corr-freq").value });
  try {
    const res = await fetch(`/api/correlation/pair?${params}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || "推移の取得に失敗しました");
    if (pair[0] !== a || pair[1] !== b) return;
    $("pair-title").textContent = `${d.a.name} × ${d.b.name}`;
    pairLine.setData(d.series);
    const last = d.series.at(-1)?.value;
    $("pair-note").textContent = `直近${d.window}${d.unit}のローリング相関。最新値 ${last != null ? (last > 0 ? "+" : "") + last.toFixed(2) : "—"}。相関は時期によって変わり、分散の効果は常に一定ではありません。`;
    requestAnimationFrame(() => pairChart.timeScale().fitContent());
  } catch (e) {
    toast(e.message);
  }
}

$("corr-table").addEventListener("click", (e) => {
  const td = e.target.closest("td[data-a]");
  if (td) loadPair(td.dataset.a, td.dataset.b);
});
["corr-period", "corr-freq"].forEach((id) => $(id).addEventListener("change", loadCorrelation));

// ---------- news ----------
function ago(iso) {
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 60) return `${Math.max(m, 1)}分前`;
  if (m < 1440) return `${Math.round(m / 60)}時間前`;
  return `${Math.round(m / 1440)}日前`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(u) {
  return /^https?:\/\//.test(u) ? esc(u) : "#";
}

async function loadNews(symbol) {
  $("news").innerHTML = `<li class="muted">読み込み中…</li>`;
  $("news-q").textContent = "";
  try {
    const res = await fetch(`/api/news?symbol=${encodeURIComponent(symbol)}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || "ニュースの取得に失敗しました");
    if (current?.symbol !== symbol) return;
    $("news-q").textContent = d.query;
    $("news").innerHTML = d.items.length
      ? d.items.map((n) => `<li><a href="${safeUrl(n.link)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a>
          <span>${esc(n.source || "")}・${ago(n.published)}</span></li>`).join("")
      : `<li class="muted">直近7日のニュースはありません。</li>`;
  } catch (e) {
    $("news").innerHTML = `<li class="muted">${esc(e.message)}</li>`;
  }
}

// ---------- policy ----------
let policy = null;
const policyOff = new Set();

async function loadPolicy() {
  $("policy-note").textContent = "読み込み中…";
  try {
    const res = await fetch("/api/policy");
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || "取得に失敗しました");
    policy = d;
    renderPolicy();
  } catch (e) {
    $("policy-note").textContent = "";
    toast(e.message);
  }
}

function fmtJst(iso) {
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function reactChip(r) {
  const v = (x) => (x == null ? `<span class="muted">—</span>` : `<span class="${cls(x)}">${pct(x)}</span>`);
  return `<span class="react"><b>${esc(r.name)}</b>当日 ${v(r.d1)}<i></i>5日 ${v(r.d5)}</span>`;
}

function renderPolicy() {
  const d = policy;
  const srcName = Object.fromEntries(d.sources.map((s) => [s.id, s.name]));
  $("policy-src").innerHTML = d.sources.map((s) => `
    <span class="src ${policyOff.has(s.id) ? "off" : ""}" data-src="${s.id}">
      <button data-src="${s.id}">${esc(s.name)}</button>
      <a href="${safeUrl(s.page)}" target="_blank" rel="noopener noreferrer" title="公式ページを開く">↗</a>
      ${s.error ? `<em title="${esc(s.error)}">取得失敗</em>` : ""}
    </span>`).join("");
  const imp = $("policy-imp").checked;
  const items = d.items.filter((i) => !policyOff.has(i.source) && (!imp || i.important));
  $("policy-note").textContent = `${items.length}件／過去${d.days}日・時刻は日本時間`;
  $("policy-list").innerHTML = items.length ? items.map((i) => `
    <li>
      <div class="p-meta"><span class="badge b-${i.source}">${esc(srcName[i.source])}</span>
        <span class="mono">${fmtJst(i.published)}</span>${i.important ? `<span class="imp">重要</span>` : ""}</div>
      <a href="${safeUrl(i.link)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a>
      <div class="p-react">${i.reaction.map(reactChip).join("")}</div>
    </li>`).join("") : `<li class="muted">該当する発表はありません。</li>`;
}

$("policy-src").addEventListener("click", (e) => {
  const id = e.target.tagName === "BUTTON" && e.target.dataset.src;
  if (!id) return;
  policyOff.has(id) ? policyOff.delete(id) : policyOff.add(id);
  renderPolicy();
});
$("policy-imp").addEventListener("change", () => policy && renderPolicy());

// ---------- technical / fundamental ----------
function scoreSpan(score, label) {
  if (score == null) return "—";
  const c = score >= 30 ? "up" : score <= -30 ? "down" : "";
  return `<span class="${c}">${label} ${score > 0 ? "+" : ""}${score}</span>`;
}
function renderCategories(cats) {
  return cats.map((c) => {
    const s = c.score;
    const bar = s == null ? "" : `<span style="${s >= 0 ? `left:50%;width:${s * 50}%` : `left:${50 + s * 50}%;width:${-s * 50}%`};background:${css(s >= 0 ? "--up" : "--down")}"></span>`;
    const items = c.items.map((i) => {
      const mk = i.score == null ? "" : i.score > 0 ? `<span class="mk up">＋</span>` : i.score < 0 ? `<span class="mk down">−</span>` : `<span class="mk muted">0</span>`;
      return `<li><span>${esc(i.name)}</span><span class="v">${esc(i.value ?? "—")}</span>${mk || "<span></span>"}<small>${esc(i.note)}</small></li>`;
    }).join("");
    return `<details class="fa-cat"><summary><span>${esc(c.name)}</span><div class="fa-bar">${bar}</div>
      <span class="s ${cls(s)}">${s == null ? (c.items.length ? "参考" : "—") : (s > 0 ? "+" : "") + s.toFixed(2)}</span></summary>
      <ul class="fa-items">${items || `<li class="muted">データなし</li>`}</ul></details>`;
  }).join("");
}

function renderTechnical(t) {
  $("ta-score").innerHTML = scoreSpan(t.score, t.label);
  $("ta-body").innerHTML = renderCategories(t.categories);
}

function fmtBig(v, cur) {
  if (v == null) return "—";
  const unit = cur === "JPY" ? "円" : cur === "USD" ? "ドル" : "";
  const a = Math.abs(v);
  if (a >= 1e12) return `${(v / 1e12).toFixed(1)}兆${unit}`;
  if (a >= 1e8) return `${(v / 1e8).toFixed(0)}億${unit}`;
  return `${fmt(v, 0)}${unit}`;
}

async function loadFundamental(symbol) {
  $("fa-score").textContent = "…";
  $("fa-body").innerHTML = `<div class="fa-na">読み込み中…</div>`;
  try {
    const res = await fetch(`/api/fundamental?symbol=${encodeURIComponent(symbol)}`);
    const f = await res.json();
    if (!res.ok) throw new Error(f.error || "取得に失敗しました");
    if (current?.symbol !== symbol) return;
    if (!f.available) {
      $("fa-score").textContent = "対象外";
      $("fa-body").innerHTML = `<div class="fa-na">${esc(f.reason)}</div>`;
      return;
    }
    $("fa-score").innerHTML = scoreSpan(f.score, f.label);
    let html = renderCategories(f.categories);

    if (f.history.length) {
      const max = Math.max(...f.history.map((h) => Math.abs(h.revenue || 0)));
      const w = (v) => `${Math.max(0, (v || 0) / max * 100)}%`;
      html += `<div class="fa-sub">業績の推移（決算期）</div><div class="fa-hist">${f.history.map((h) => `
        <div class="row"><span class="mono">${h.year}</span>
          <div class="bars"><i style="width:${w(h.revenue)};background:${css("--sma20")}"></i>
            <i style="width:${w(h.net)};background:${h.net < 0 ? css("--down") : css("--accent")}"></i></div>
          <span class="lab" title="純利益 ${fmtBig(h.net, f.currency)}">${fmtBig(h.revenue, f.currency)}</span></div>`).join("")}</div>
        <div class="fa-legend"><span><i style="background:${css("--sma20")}"></i>売上高</span><span><i style="background:${css("--accent")}"></i>純利益</span></div>`;
    }
    const a = f.analyst;
    if (a) {
      html += `<div class="fa-sub">アナリスト予想（${a.count ?? "—"}人）</div><div class="fa-analyst">
        <div><div class="k">平均目標株価</div><div class="v">${fmt(a.target)}</div></div>
        <div><div class="k">現在値からの差</div><div class="v ${cls(a.upside_pct)}">${pct(a.upside_pct)}</div></div>
        <div><div class="k">推奨（平均）</div><div class="v">${esc(a.recommendation ?? "—")}</div></div></div>`;
    }
    $("fa-body").innerHTML = html;
  } catch (e) {
    $("fa-score").textContent = "—";
    $("fa-body").innerHTML = `<div class="fa-na">${esc(e.message)}</div>`;
  }
}

// ---------- init ----------
setPeriodOptions();
load(new URLSearchParams(location.search).get("s") || "7203.T");
const initView = new URLSearchParams(location.search).get("view");
if (["corr", "policy"].includes(initView)) setView(initView);
renderWatch();
