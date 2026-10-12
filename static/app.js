const PRESETS = [
  ["トヨタ", "7203.T"], ["ソニーG", "6758.T"], ["三菱UFJ", "8306.T"],
  ["Apple", "AAPL"], ["NVIDIA", "NVDA"], ["Microsoft", "MSFT"],
  ["Bitcoin", "BTC-USD"], ["Ethereum", "ETH-USD"],
  ["USD/JPY", "JPY=X"], ["日経平均", "^N225"], ["S&P500", "^GSPC"], ["NASDAQ", "^IXIC"],
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
  timeScale: { borderColor: css("--line") },
  crosshair: { mode: 0 },
  autoSize: true,
});

const LC = LightweightCharts;
const mainChart = LC.createChart($("chart-main"), baseOpts());
const volChart = LC.createChart($("chart-vol"), { ...baseOpts(), timeScale: { visible: false } });
const rsiChart = LC.createChart($("chart-rsi"), { ...baseOpts(), timeScale: { visible: false } });
const macdChart = LC.createChart($("chart-macd"), { ...baseOpts(), timeScale: { visible: false } });

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
  daily: [["3mo", "3ヶ月"], ["6mo", "6ヶ月"], ["1y", "1年"], ["2y", "2年"], ["5y", "5年"]],
  intraday: [["1d", "1日"], ["5d", "5日"], ["1mo", "1ヶ月"]],
};
function setPeriodOptions() {
  const intraday = $("interval").value !== "1d";
  const opts = PERIODS[intraday ? "intraday" : "daily"];
  $("period").innerHTML = opts.map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
  $("period").value = intraday ? "5d" : "1y";
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
    if (current.symbol !== $("bt-rows").dataset.s) resetBacktest();
    document.querySelectorAll("#presets button").forEach((b) => b.classList.toggle("active", b.dataset.s === symbol));
    history.replaceState(null, "", `?s=${encodeURIComponent(symbol)}`);
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

$("presets").innerHTML = PRESETS.map(([n, s]) => `<button data-s="${s}">${n}</button>`).join("");
$("presets").addEventListener("click", (e) => { if (e.target.dataset.s) load(e.target.dataset.s); });

// ---------- backtest ----------
const BT_COLORS = { trend: "--sma20", reversion: "--sma200", buy_hold: "--muted" };
const btChart = LC.createChart($("chart-bt"), {
  ...baseOpts(),
  rightPriceScale: { borderColor: css("--line"), mode: LC.PriceScaleMode.Logarithmic },
  timeScale: { borderColor: css("--line"), minBarSpacing: 0.01 },  // 10年分を1画面に収める
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

// ---------- init ----------
setPeriodOptions();
load(new URLSearchParams(location.search).get("s") || "7203.T");
renderWatch();
