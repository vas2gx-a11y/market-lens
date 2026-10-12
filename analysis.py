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


# ---------- まとめ ----------

def _t(d, intraday):
    # 分足はUNIX秒（現地時刻をUTCとみなす）、日足は日付文字列
    return int(pd.Timestamp(d).timestamp()) if intraday else d.strftime("%Y-%m-%d")


def _series(df, col, intraday=False):
    s = df[col].dropna()
    return [{"time": _t(d, intraday), "value": round(float(v), 6)} for d, v in s.items()]


def _chart_frame(symbol, period, interval):
    if interval in INTRADAY:
        # 5分足は最大60日分まで取得可能。指標計算用に表示期間より長めに取得
        fetch_period = {"1d": "5d", "5d": "1mo", "1mo": "60d"}.get(period, "1mo")
        if interval == "60m":
            fetch_period = {"1d": "1mo", "5d": "3mo", "1mo": "6mo"}.get(period, "3mo")
        df = add_indicators(fetch_history(symbol, fetch_period, interval))
        days = {"1d": 1, "5d": 5, "1mo": 21}.get(period, 5)
        if is_24x7(symbol):
            days = int(days * 7 / 5) if days > 1 else 1
        sessions = pd.Index(df.index.normalize().unique())
        return df[df.index.normalize() >= sessions[-min(days, len(sessions))]]

    fetch_period = {"3mo": "1y", "6mo": "2y", "1y": "2y", "2y": "5y", "5y": "10y"}.get(period, "2y")
    df = add_indicators(fetch_history(symbol, fetch_period))
    days = {"3mo": 63, "6mo": 126, "1y": 252, "2y": 504, "5y": 1260}.get(period, 252)
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
