"""価格データ取得・テクニカル指標・予測ロジック"""
import time

import numpy as np
import pandas as pd
import yfinance as yf

_CACHE: dict = {}
_CACHE_TTL = 300  # 秒


INTRADAY = {"5m": "5分足", "15m": "15分足", "60m": "1時間足"}


def _cached(key, fn, ttl=_CACHE_TTL):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn()
    _CACHE[key] = (now, value)
    return value


def is_24x7(symbol: str) -> bool:
    """暗号資産は土日も取引される"""
    return symbol.upper().endswith(("-USD", "-JPY", "-USDT"))


def fetch_history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    def load():
        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            raise ValueError(f"データが取得できませんでした: {symbol}")
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        # 取引所の現地時刻のまま扱う（チャートにはそのまま表示される）
        df.index = pd.to_datetime(df.index).tz_localize(None)
        if interval == "1d":
            df.index = df.index.normalize()
        return df

    # 分足は更新頻度が高いのでキャッシュを短くする
    ttl = 60 if interval in INTRADAY else _CACHE_TTL
    return _cached(("hist", symbol, period, interval), load, ttl)


FUNDAMENTAL_KEYS = (
    "currency", "marketCap", "trailingPE", "forwardPE", "priceToBook", "dividendYield",
    "trailingEps", "returnOnEquity", "beta", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "averageVolume", "sector", "industry",
    # 詳細ファンダメンタル分析用
    "quoteType", "pegRatio", "trailingPegRatio", "enterpriseToEbitda", "operatingMargins", "profitMargins",
    "revenueGrowth", "earningsGrowth", "debtToEquity", "currentRatio", "freeCashflow", "payoutRatio",
    "targetMeanPrice", "targetHighPrice", "targetLowPrice", "recommendationKey", "numberOfAnalystOpinions",
)


def fetch_info(symbol: str) -> dict:
    def load():
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception:
            info = {}
        return {
            "name": info.get("shortName") or info.get("longName") or symbol,
            **{k: info.get(k) for k in FUNDAMENTAL_KEYS},
        }

    return _cached(("info", symbol), load)


# ---------- テクニカル指標 ----------

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]
    df["SMA20"] = close.rolling(20).mean()
    df["SMA50"] = close.rolling(50).mean()
    df["SMA200"] = close.rolling(200).mean()

    std20 = close.rolling(20).std()
    df["BB_UP"] = df["SMA20"] + 2 * std20
    df["BB_LO"] = df["SMA20"] - 2 * std20

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - 100 / (1 + rs)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_SIG"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIG"]

    vol = df["Volume"].fillna(0)
    df["VOL_MA20"] = vol.rolling(20).mean()
    df["OBV"] = (np.sign(delta).fillna(0) * vol).cumsum()
    return df


def signals(df: pd.DataFrame) -> dict:
    """指標から強気/弱気スコア（-100〜100）を算出"""
    last, prev = df.iloc[-1], df.iloc[-2]
    items = []

    def add(name, score, note):
        items.append({"name": name, "score": score, "note": note})

    rsi = last["RSI"]
    if rsi >= 70:
        add("RSI", -1, f"RSI {rsi:.1f}：買われすぎ")
    elif rsi <= 30:
        add("RSI", 1, f"RSI {rsi:.1f}：売られすぎ")
    else:
        add("RSI", 0, f"RSI {rsi:.1f}：中立")

    if prev["MACD"] <= prev["MACD_SIG"] and last["MACD"] > last["MACD_SIG"]:
        add("MACD", 1, "ゴールデンクロス発生")
    elif prev["MACD"] >= prev["MACD_SIG"] and last["MACD"] < last["MACD_SIG"]:
        add("MACD", -1, "デッドクロス発生")
    elif last["MACD_HIST"] > 0:
        add("MACD", 0.5, "MACDがシグナル線の上")
    else:
        add("MACD", -0.5, "MACDがシグナル線の下")

    for col in ("SMA20", "SMA50", "SMA200"):
        if pd.notna(last[col]):
            up = last["Close"] > last[col]
            add(col, 0.5 if up else -0.5, f"価格が{col}の{'上' if up else '下'}")

    if pd.notna(last["SMA50"]) and pd.notna(last["SMA200"]):
        up = last["SMA50"] > last["SMA200"]
        add("トレンド", 1 if up else -1, "SMA50 > SMA200（上昇基調）" if up else "SMA50 < SMA200（下降基調）")

    if pd.notna(last["BB_UP"]):
        if last["Close"] > last["BB_UP"]:
            add("ボリンジャー", -0.5, "+2σ超え：過熱")
        elif last["Close"] < last["BB_LO"]:
            add("ボリンジャー", 0.5, "-2σ割れ：売られすぎ")

    if pd.notna(last["VOL_MA20"]) and last["VOL_MA20"] > 0:
        ratio = last["Volume"] / last["VOL_MA20"]
        up = last["Close"] >= prev["Close"]
        if ratio >= 1.5:
            add("出来高", 0.5 if up else -0.5,
                f"平均の{ratio:.1f}倍の出来高で{'上昇' if up else '下落'}")
        else:
            add("出来高", 0, f"平均の{ratio:.1f}倍（通常水準）")
        obv = df["OBV"]
        obv_up = obv.iloc[-1] > obv.iloc[-21] if len(obv) > 21 else None
        if obv_up is not None:
            add("OBV", 0.5 if obv_up else -0.5, f"OBVが20日前より{'増加（買い優勢）' if obv_up else '減少（売り優勢）'}")

    total = sum(i["score"] for i in items)
    max_abs = sum(abs(i["score"]) if i["score"] else 0.5 for i in items) or 1
    score = round(100 * total / max_abs)
    label = "強気" if score >= 30 else "弱気" if score <= -30 else "中立"
    return {"score": score, "label": label, "items": items}


# ---------- 予測 ----------

def forecast(df: pd.DataFrame, symbol: str, horizon: int = 20, lookback: int = 120) -> dict:
    """
    対数価格の線形回帰でトレンドを推定し、日次リターンの標準偏差から
    予測区間（68% / 95%）を算出する簡易モデル。
    """
    close = df["Close"].dropna().iloc[-lookback:]
    y = np.log(close.values)
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)

    # ドリフトは回帰傾きを半分に減衰（トレンドの過信を抑える）
    drift = slope * 0.5
    sigma = np.diff(y).std(ddof=1)

    last_date = close.index[-1]
    freq = "D" if is_24x7(symbol) else "B"
    future = pd.date_range(last_date, periods=horizon + 1, freq=freq)[1:]

    base = y[-1]
    h = np.arange(1, horizon + 1)
    mid = base + drift * h
    band = sigma * np.sqrt(h)

    def pts(arr):
        return [{"time": d.strftime("%Y-%m-%d"), "value": round(float(np.exp(v)), 6)} for d, v in zip(future, arr)]

    last_price = float(close.iloc[-1])
    target = float(np.exp(mid[-1]))
    # 上昇確率（対数正規の近似）
    from math import erf, sqrt
    z = (drift * horizon) / (sigma * np.sqrt(horizon)) if sigma > 0 else 0
    p_up = 0.5 * (1 + erf(z / sqrt(2)))

    return {
        "horizon": horizon,
        "mid": pts(mid),
        "upper68": pts(mid + band),
        "lower68": pts(mid - band),
        "upper95": pts(mid + 1.96 * band),
        "lower95": pts(mid - 1.96 * band),
        "target": round(target, 6),
        "change_pct": round((target / last_price - 1) * 100, 2),
        "range95": [round(float(np.exp(mid[-1] - 1.96 * band[-1])), 6),
                    round(float(np.exp(mid[-1] + 1.96 * band[-1])), 6)],
        "prob_up": round(p_up * 100, 1),
        "volatility_annual": round(float(sigma * np.sqrt(365 if is_24x7(symbol) else 252) * 100), 1),
    }


# ---------- バックテスト ----------

def _metrics(ret: pd.Series, ann: int) -> dict:
    equity = (1 + ret).cumprod()
    years = len(ret) / ann
    cagr = equity.iloc[-1] ** (1 / years) - 1 if years > 0 else 0
    sd = ret.std(ddof=1)
    return {
        "total_pct": round(float((equity.iloc[-1] - 1) * 100), 1),
        "cagr_pct": round(float(cagr * 100), 1),
        "sharpe": round(float(ret.mean() / sd * np.sqrt(ann)), 2) if sd > 0 else None,
        "max_dd_pct": round(float((equity / equity.cummax() - 1).min() * 100), 1),
    }


def _positions(scores: pd.Series, threshold: int, mode: str) -> pd.Series:
    """当日のスコアで決めた保有フラグ（実際の保有は翌日から）"""
    if mode == "trend":
        return (scores >= threshold).astype(float)
    # 逆張り: スコア <= -threshold で買い、>= threshold で手仕舞い
    pos, held = [], 0.0
    for v in scores:
        if v <= -threshold:
            held = 1.0
        elif v >= threshold:
            held = 0.0
        pos.append(held)
    return pd.Series(pos, index=scores.index)


def backtest(symbol: str, period: str = "10y", threshold: int = 30, cost: float = 0.001,
             horizon: int = 20) -> dict:
    """
    シグナル総合スコアの検証。翌日から売買（先読みなし）、売買ごとに片道 cost を控除。
    - 順張り: スコア >= threshold で保有、未満で手仕舞い
    - 逆張り: スコア <= -threshold で買い、>= threshold で手仕舞い
    - Buy&Hold: 常に保有
    あわせて判定ラベル別に、その後 horizon 日リターンの平均と勝率を集計する。
    """
    df = add_indicators(fetch_history(symbol, period))
    start = 200  # SMA200 が揃うまでは除外
    if len(df) <= start + horizon:
        raise ValueError("バックテストに十分なデータがありません")

    def run():
        return pd.Series([signals(df.iloc[: i + 1])["score"] for i in range(start, len(df))],
                         index=df.index[start:])

    scores = _cached(("scores", symbol, period, df.index[-1]), run, 3600)
    ret = df["Close"].pct_change().loc[scores.index].fillna(0)
    ann = 365 if is_24x7(symbol) else 252

    strategies, curves = {}, {}
    for key, name in (("trend", "順張り"), ("reversion", "逆張り"), ("buy_hold", "Buy&Hold")):
        if key == "buy_hold":
            pos = pd.Series(1.0, index=scores.index)
        else:
            pos = _positions(scores, threshold, key).shift(1).fillna(0)
        trades = pos.diff().abs().fillna(pos.iloc[0])
        r = pos * ret - trades * cost
        strategies[key] = {"name": name, **_metrics(r, ann), "trades": int(trades.sum()),
                           "exposure_pct": round(float(pos.mean() * 100), 1)}
        curves[key] = [{"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
                       for d, v in (1 + r).cumprod().items()]

    fwd = (df["Close"].shift(-horizon) / df["Close"] - 1).loc[scores.index].dropna()
    labels = np.where(scores >= 30, "強気", np.where(scores <= -30, "弱気", "中立"))
    by_label = {}
    for lb in ("強気", "中立", "弱気"):
        r = fwd[labels[: len(fwd)] == lb]
        if len(r):
            by_label[lb] = {"count": int(len(r)), "avg_pct": round(float(r.mean() * 100), 2),
                            "win_pct": round(float((r > 0).mean() * 100), 1)}

    return {
        "symbol": symbol,
        "from": scores.index[0].strftime("%Y-%m-%d"),
        "to": scores.index[-1].strftime("%Y-%m-%d"),
        "threshold": threshold,
        "cost_pct": cost * 100,
        "strategies": strategies,
        "best": max(strategies, key=lambda k: strategies[k]["sharpe"] or -99),
        "horizon": horizon,
        "forward_by_label": by_label,
        "equity": curves,
    }


# ---------- 相関 ----------

CORR_GROUPS = {
    "株": {"^N225": "日経225", "^GSPC": "S&P500", "^IXIC": "NASDAQ", "^GDAXI": "DAX", "000001.SS": "上海総合"},
    "為替": {"JPY=X": "ドル円", "EURJPY=X": "ユーロ円", "GBPJPY=X": "ポンド円", "AUDJPY=X": "豪ドル円",
           "EURUSD=X": "ユーロドル", "GBPUSD=X": "ポンドドル", "CNY=X": "ドル人民元", "DX-Y.NYB": "ドル指数"},
    "コモディティ": {"GC=F": "金", "SI=F": "銀", "CL=F": "原油", "HG=F": "銅", "NG=F": "天然ガス"},
    "暗号資産": {"BTC-USD": "ビットコイン", "ETH-USD": "イーサリアム", "XRP-USD": "XRP", "SOL-USD": "ソラナ"},
}
CORR_SYMBOLS = {s: n for g in CORR_GROUPS.values() for s, n in g.items()}


def _corr_returns(period: str, freq: str) -> pd.DataFrame:
    days = {"1y": 365, "3y": 365 * 3, "5y": 365 * 5}[period]
    px = {}
    for s in CORR_SYMBOLS:
        try:
            px[s] = fetch_history(s, "5y")["Close"]
        except ValueError:
            continue
    px = pd.DataFrame(px)
    px = px[px.index >= px.index[-1] - pd.Timedelta(days=days)]
    # 市場ごとに終値時刻が違うため、週次（金曜終値）が既定
    if freq == "W":
        last = px.index[-1]
        px = px.resample("W-FRI").last()
        px.index = px.index[:-1].append(pd.DatetimeIndex([min(px.index[-1], last)]))
    return px.pct_change(fill_method=None).iloc[1:]


def correlation(period: str = "5y", freq: str = "W") -> dict:
    ret = _corr_returns(period, freq)
    c = ret.corr(min_periods=20)
    syms = list(c.columns)
    group_of = {s: g for g, d in CORR_GROUPS.items() for s in d}

    groups = {}
    for a in CORR_GROUPS:
        groups[a] = {}
        for b in CORR_GROUPS:
            vals = [c.loc[i, j] for i in syms for j in syms
                    if i != j and group_of[i] == a and group_of[j] == b and pd.notna(c.loc[i, j])]
            groups[a][b] = round(float(np.mean(vals)), 2) if vals else None

    return {
        "period": period,
        "freq": freq,
        "from": ret.index[0].strftime("%Y-%m-%d"),
        "to": ret.index[-1].strftime("%Y-%m-%d"),
        "n": int(len(ret)),
        "groups": [{"name": g, "assets": [{"symbol": s, "name": n} for s, n in d.items() if s in syms]}
                   for g, d in CORR_GROUPS.items()],
        "matrix": {i: {j: (None if pd.isna(c.loc[i, j]) else round(float(c.loc[i, j]), 2)) for j in syms}
                   for i in syms},
        "group_avg": groups,
    }


def rolling_correlation(a: str, b: str, period: str = "5y", freq: str = "W") -> dict:
    if a not in CORR_SYMBOLS or b not in CORR_SYMBOLS:
        raise ValueError("対象外の銘柄です")
    ret = _corr_returns(period, freq)
    window = 26 if freq == "W" else 60
    r = ret[a].rolling(window, min_periods=window // 2).corr(ret[b]).dropna()
    return {
        "a": {"symbol": a, "name": CORR_SYMBOLS[a]},
        "b": {"symbol": b, "name": CORR_SYMBOLS[b]},
        "window": window,
        "unit": "週" if freq == "W" else "日",
        "series": [{"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 3)} for d, v in r.items()],
    }


# ---------- テクニカル／ファンダメンタル分析 ----------

def _rate(value, good, bad, higher_is_better=True):
    """しきい値で +1（良い）/ 0 / -1（悪い）を返す"""
    if higher_is_better:
        return 1 if value >= good else -1 if value < bad else 0
    return 1 if value <= good else -1 if value > bad else 0


def _summarize(categories):
    scored = [c for c in categories if c["score"] is not None]
    total = round(100 * sum(c["score"] for c in scored) / len(scored)) if scored else None
    label = None if total is None else "良好" if total >= 30 else "弱い" if total <= -30 else "中立"
    return {"score": total, "label": label, "categories": categories}


def _category(name, items):
    rated = [i["score"] for i in items if i["score"] is not None]
    return {"name": name, "score": round(sum(rated) / len(rated), 2) if rated else None, "items": items}


def technical_analysis(df: pd.DataFrame, symbol: str) -> dict:
    """日足から、トレンド・モメンタム・ボラティリティ・価格位置を評価"""
    close = df["Close"]
    last = df.iloc[-1]
    ann = 365 if is_24x7(symbol) else 252
    per_month = 30 if is_24x7(symbol) else 21

    def ret(n, skip=0):
        if len(close) <= n:
            return None
        return float(close.iloc[-1 - skip] / close.iloc[-1 - n] - 1) * 100

    def item(name, value, score, note):
        return {"name": name, "value": value, "score": score, "note": note}

    trend = []
    if pd.notna(last["SMA200"]):
        gap = float(last["Close"] / last["SMA200"] - 1) * 100
        trend.append(item("SMA200との乖離", f"{gap:+.1f}%", 1 if gap > 0 else -1,
                          "長期移動平均の上（上昇トレンド）" if gap > 0 else "長期移動平均の下（下降トレンド）"))
        slope = float(df["SMA200"].iloc[-1] / df["SMA200"].iloc[-per_month - 1] - 1) * 100
        trend.append(item("SMA200の傾き(1ヶ月)", f"{slope:+.2f}%", 1 if slope > 0 else -1,
                          "長期線が上向き" if slope > 0 else "長期線が下向き"))
    if pd.notna(last["SMA50"]) and pd.notna(last["SMA200"]):
        up = last["SMA50"] > last["SMA200"]
        trend.append(item("SMA50 / SMA200", "GC" if up else "DC", 1 if up else -1,
                          "中期線が長期線の上（ゴールデンクロス状態）" if up else "中期線が長期線の下（デッドクロス状態）"))

    momentum = []
    m12 = ret(12 * per_month, per_month)
    if m12 is not None:
        momentum.append(item("12-1ヶ月リターン", f"{m12:+.1f}%", _rate(m12, 10, 0),
                             "直近1ヶ月を除く過去1年の騰落。学術的に効果が確認されているモメンタム指標"))
    m3 = ret(3 * per_month)
    if m3 is not None:
        momentum.append(item("3ヶ月リターン", f"{m3:+.1f}%", _rate(m3, 5, -5), "中期の勢い"))
    rsi = float(last["RSI"])
    momentum.append(item("RSI(14)", f"{rsi:.1f}", -1 if rsi >= 70 else 1 if rsi <= 30 else 0,
                         "買われすぎ（過熱）" if rsi >= 70 else "売られすぎ" if rsi <= 30 else "中立圏"))

    risk = []
    daily = close.pct_change().dropna()
    vol60 = float(daily.iloc[-60:].std() * np.sqrt(ann) * 100)
    vol_hist = (daily.rolling(60).std() * np.sqrt(ann) * 100).dropna().iloc[-ann:]
    pctile = float((vol_hist < vol60).mean() * 100) if len(vol_hist) else None
    risk.append(item("ボラティリティ(60日・年率)", f"{vol60:.1f}%", None,
                     f"過去1年の中で低い方から{pctile:.0f}%の水準" if pctile is not None else "変動の大きさ"))
    peak = close.cummax()
    dd = float((close.iloc[-ann:] / peak.iloc[-ann:] - 1).min() * 100)
    risk.append(item("最大下落率(1年)", f"{dd:.1f}%", None, "過去1年で高値から最も下げた幅"))

    position = []
    hi, lo = float(close.iloc[-ann:].max()), float(close.iloc[-ann:].min())
    pos = (float(last["Close"]) - lo) / (hi - lo) * 100 if hi > lo else 50
    position.append(item("52週レンジ内の位置", f"{pos:.0f}%", None, "0%=52週安値、100%=52週高値"))
    from_hi = (float(last["Close"]) / hi - 1) * 100
    position.append(item("52週高値からの乖離", f"{from_hi:+.1f}%", None,
                         "高値圏" if from_hi > -5 else "高値から調整中" if from_hi > -20 else "高値から大きく下落"))

    # スコアはトレンドとモメンタムのみ（リスク・位置は参考情報）
    return _summarize([_category("トレンド", trend), _category("モメンタム", momentum),
                       _category("リスク", risk), _category("価格の位置", position)])


def fundamental_analysis(symbol: str) -> dict:
    info = fetch_info(symbol)
    no_data = info.get("trailingPE") is None and info.get("returnOnEquity") is None
    if info.get("quoteType") not in ("EQUITY", None) or no_data:
        return {"available": False, "reason": "株式以外（為替・暗号資産・指数・先物など）は財務諸表がないため対象外です"}

    def item(name, value, fmt, score, note):
        return {"name": name, "value": None if value is None else fmt(value), "score": score, "note": note}

    pct = lambda v: f"{v * 100:.1f}%"
    times = lambda v: f"{v:.1f}倍"
    g = info.get

    value_items = []
    pe = g("trailingPE")
    if pe is not None and pe > 0:
        value_items.append(item("PER（実績）", pe, times, _rate(pe, 12, 25, False), "利益に対する株価。低いほど割安"))
    pb = g("priceToBook")
    if pb is not None and pb > 0:
        value_items.append(item("PBR", pb, lambda v: f"{v:.2f}倍", _rate(pb, 1, 3, False), "純資産に対する株価。1倍割れは解散価値以下"))
    peg = g("trailingPegRatio") or g("pegRatio")
    if peg is not None and peg > 0:
        value_items.append(item("PEG", peg, lambda v: f"{v:.2f}", _rate(peg, 1, 2, False), "PERを利益成長率で割った値。1未満は成長に対して割安"))
    ev = g("enterpriseToEbitda")
    if ev is not None and ev > 0:
        value_items.append(item("EV/EBITDA", ev, times, _rate(ev, 8, 15, False), "買収コストの何年分の稼ぎか。低いほど割安"))

    profit = []
    if g("returnOnEquity") is not None:
        profit.append(item("ROE", g("returnOnEquity"), pct, _rate(g("returnOnEquity"), 0.15, 0.08), "自己資本でどれだけ稼いだか。15%以上が優良の目安"))
    if g("operatingMargins") is not None:
        profit.append(item("営業利益率", g("operatingMargins"), pct, _rate(g("operatingMargins"), 0.15, 0.05), "本業の稼ぐ力"))
    if g("profitMargins") is not None:
        profit.append(item("純利益率", g("profitMargins"), pct, _rate(g("profitMargins"), 0.10, 0.03), "売上に対する最終利益"))

    growth = []
    if g("revenueGrowth") is not None:
        growth.append(item("売上成長率（前年同期比）", g("revenueGrowth"), pct, _rate(g("revenueGrowth"), 0.10, 0), "直近四半期の売上の伸び"))
    if g("earningsGrowth") is not None:
        growth.append(item("利益成長率（前年同期比）", g("earningsGrowth"), pct, _rate(g("earningsGrowth"), 0.10, 0), "直近四半期の利益の伸び"))

    history = []
    try:
        stmt = _cached(("income", symbol), lambda: yf.Ticker(symbol).income_stmt, 3600)
        rows = {"revenue": "Total Revenue", "operating": "Operating Income", "net": "Net Income", "eps": "Diluted EPS"}
        for col in sorted(stmt.columns)[-5:]:
            rec = {"year": col.strftime("%Y/%m")}
            for k, r in rows.items():
                v = stmt.at[r, col] if r in stmt.index else None
                rec[k] = None if v is None or pd.isna(v) else float(v)
            if rec["revenue"] is not None:
                history.append(rec)
    except Exception:
        history = []
    revs = [h["revenue"] for h in history if h["revenue"]]
    if len(revs) >= 3 and revs[0] > 0:
        cagr = (revs[-1] / revs[0]) ** (1 / (len(revs) - 1)) - 1
        growth.append(item(f"売上の年平均成長率（{len(revs) - 1}年）", cagr, pct, _rate(cagr, 0.07, 0), "数年単位で見た成長"))

    health = []
    de = g("debtToEquity")
    if de is not None:
        health.append(item("D/Eレシオ", de / 100, times, _rate(de, 50, 150, False), "自己資本に対する有利子負債。低いほど安全（金融業は高くなりやすい）"))
    cr = g("currentRatio")
    if cr is not None:
        health.append(item("流動比率", cr, times, _rate(cr, 1.5, 1.0), "1年以内に払う負債を流動資産でまかなえるか"))
    fcf = g("freeCashflow")
    if fcf is not None:
        health.append(item("フリーキャッシュフロー", fcf, lambda v: f"{v / 1e8:,.0f}億", 1 if fcf > 0 else -1,
                           "本業の現金収入から投資を引いた額。マイナスは投資先行か資金流出"))

    payout = []
    dy = g("dividendYield")
    if dy is not None:
        payout.append(item("配当利回り", dy, lambda v: f"{v:.2f}%", _rate(dy, 3, 1), "株価に対する年間配当"))
    pr = g("payoutRatio")
    if pr is not None and pr > 0:
        payout.append(item("配当性向", pr, pct, -1 if pr > 1 else 0, "利益のうち配当に回す割合。100%超は持続性に注意"))

    analyst = None
    tgt, price = g("targetMeanPrice"), None
    try:
        price = float(fetch_history(symbol, "1mo")["Close"].iloc[-1])
    except ValueError:
        pass
    if tgt and price:
        rec_ja = {"strong_buy": "強い買い", "buy": "買い", "hold": "中立", "underperform": "やや売り",
                  "sell": "売り", "strong_sell": "強い売り"}
        analyst = {"target": tgt, "high": g("targetHighPrice"), "low": g("targetLowPrice"),
                   "upside_pct": round((tgt / price - 1) * 100, 1),
                   "recommendation": rec_ja.get(g("recommendationKey"), g("recommendationKey")),
                   "count": g("numberOfAnalystOpinions")}

    return {"available": True, "currency": g("currency"),
            **_summarize([_category("割安度", value_items), _category("収益性", profit), _category("成長性", growth),
                          _category("財務健全性", health), _category("株主還元", payout)]),
            "history": history, "analyst": analyst}


# ---------- まとめ ----------

def _t(d, intraday):
    # 分足はUNIX秒（現地時刻をUTCとみなす）、日足は日付文字列
    return int(pd.Timestamp(d).timestamp()) if intraday else d.strftime("%Y-%m-%d")


def _series(df, col, intraday=False):
    s = df[col].dropna()
    return [{"time": _t(d, intraday), "value": round(float(v), 6)} for d, v in s.items()]


# 足種ごとに Yahoo Finance から取得できる最大期間
INTRADAY_MAX = {"5m": "60d", "15m": "60d", "60m": "730d"}
PERIOD_DAYS = {"1d": 1, "5d": 5, "1mo": 21, "60d": 42, "3mo": 63, "6mo": 126, "1y": 252, "2y": 504,
               "5y": 1260, "10y": 2520}


def _chart_frame(symbol, period, interval):
    if interval in INTRADAY:
        # 指標計算用に表示期間より長めに取得（足種ごとの上限まで）
        fetch_period = {"1d": "5d", "5d": "1mo"}.get(period, INTRADAY_MAX[interval])
        if interval == "60m" and period in ("1d", "5d", "1mo"):
            fetch_period = {"1d": "1mo", "5d": "3mo", "1mo": "6mo"}[period]
        df = add_indicators(fetch_history(symbol, fetch_period, interval))
        if period == "max":
            # 上限ちょうどを指定すると、Yahoo は上限より少し長い期間を返す（為替なら約3ヶ月／約2.8年）
            return df
        days = PERIOD_DAYS.get(period, 5)
        if is_24x7(symbol):
            days = int(days * 7 / 5) if days > 1 else 1
        sessions = pd.Index(df.index.normalize().unique())
        return df[df.index.normalize() >= sessions[-min(days, len(sessions))]]

    if period == "max":
        return add_indicators(fetch_history(symbol, "max"))
    fetch_period = {"3mo": "1y", "6mo": "2y", "1y": "2y", "2y": "5y", "5y": "10y", "10y": "max"}.get(period, "2y")
    df = add_indicators(fetch_history(symbol, fetch_period))
    days = PERIOD_DAYS.get(period, 252)
    if is_24x7(symbol):
        days = int(days * 365 / 252)
    return df.iloc[-days:]


def analyze(symbol: str, period: str = "1y", horizon: int = 20, interval: str = "1d") -> dict:
    intraday = interval in INTRADAY
    # シグナル・予測・騰落率は常に日足ベース
    full = add_indicators(fetch_history(symbol, "2y"))
    df = _chart_frame(symbol, period, interval)

    last, prev = full.iloc[-1], full.iloc[-2]
    candles = [
        {"time": _t(d, intraday), "open": round(float(r.Open), 6), "high": round(float(r.High), 6),
         "low": round(float(r.Low), 6), "close": round(float(r.Close), 6)}
        for d, r in df.iterrows()
    ]
    volume = [{"time": _t(d, intraday), "value": float(v)} for d, v in df["Volume"].items()]

    info = fetch_info(symbol)
    has_volume = bool(full["Volume"].iloc[-60:].sum() > 0)
    vol_ma = last["VOL_MA20"]
    return {
        "symbol": symbol,
        "interval": interval,
        "updated": df.index[-1].strftime("%Y-%m-%d %H:%M") if intraday else None,
        "name": info["name"],
        "fundamentals": {k: v for k, v in info.items() if k != "name" and v is not None},
        "volume_stats": {
            "last": float(last["Volume"]),
            "ma20": None if pd.isna(vol_ma) else float(vol_ma),
            "ratio": None if pd.isna(vol_ma) or not vol_ma else round(float(last["Volume"] / vol_ma), 2),
        } if has_volume else None,
        "last": round(float(last["Close"]), 6),
        "change_pct": round(float((last["Close"] / prev["Close"] - 1) * 100), 2),
        "date": full.index[-1].strftime("%Y-%m-%d"),
        "candles": candles,
        "volume": volume,
        "indicators": {c: _series(df, c, intraday) for c in
                       ("SMA20", "SMA50", "SMA200", "BB_UP", "BB_LO", "RSI", "MACD", "MACD_SIG", "MACD_HIST",
                        "VOL_MA20", "OBV")},
        "latest": {c: (None if pd.isna(last[c]) else round(float(last[c]), 4)) for c in
                   ("SMA20", "SMA50", "SMA200", "BB_UP", "BB_LO", "RSI", "MACD", "MACD_SIG")},
        "signals": signals(full),
        "technical": technical_analysis(full, symbol),
        "forecast": forecast(full, symbol, horizon),
        "perf": {
            k: round(float((full["Close"].iloc[-1] / full["Close"].iloc[-n - 1] - 1) * 100), 2)
            for k, n in (("1w", 5), ("1m", 21), ("3m", 63), ("1y", 252)) if len(full) > n
        },
    }


def quote(symbol: str) -> dict:
    df = fetch_history(symbol, "1mo")
    last, prev = df["Close"].iloc[-1], df["Close"].iloc[-2]
    return {
        "symbol": symbol,
        "last": round(float(last), 6),
        "change_pct": round(float((last / prev - 1) * 100), 2),
        "spark": [round(float(v), 6) for v in df["Close"].iloc[-20:]],
    }
