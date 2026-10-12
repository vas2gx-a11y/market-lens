"""価格データ取得・テクニカル指標・予測ロジック"""
import time

import numpy as np
import pandas as pd
import yfinance as yf

_CACHE: dict = {}
_CACHE_TTL = 300  # 秒


def _cached(key, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    value = fn()
    _CACHE[key] = (now, value)
    return value


def is_24x7(symbol: str) -> bool:
    """暗号資産は土日も取引される"""
    return symbol.upper().endswith(("-USD", "-JPY", "-USDT"))


def fetch_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    def load():
        df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
        if df.empty:
            raise ValueError(f"データが取得できませんでした: {symbol}")
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        return df

    return _cached(("hist", symbol, period), load)


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


# ---------- まとめ ----------

def _series(df, col):
    s = df[col].dropna()
    return [{"time": d.strftime("%Y-%m-%d"), "value": round(float(v), 6)} for d, v in s.items()]


def analyze(symbol: str, period: str = "1y", horizon: int = 20) -> dict:
    # 指標計算（SMA200）のために表示期間より長めに取得
    fetch_period = {"3mo": "1y", "6mo": "2y", "1y": "2y", "2y": "5y", "5y": "10y"}.get(period, "2y")
    full = add_indicators(fetch_history(symbol, fetch_period))
    days = {"3mo": 63, "6mo": 126, "1y": 252, "2y": 504, "5y": 1260}.get(period, 252)
    if is_24x7(symbol):
        days = int(days * 365 / 252)
    df = full.iloc[-days:]

    last, prev = full.iloc[-1], full.iloc[-2]
    candles = [
        {"time": d.strftime("%Y-%m-%d"), "open": round(float(r.Open), 6), "high": round(float(r.High), 6),
         "low": round(float(r.Low), 6), "close": round(float(r.Close), 6)}
        for d, r in df.iterrows()
    ]
    volume = [{"time": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in df["Volume"].items()]

    info = fetch_info(symbol)
    has_volume = bool(full["Volume"].iloc[-60:].sum() > 0)
    vol_ma = last["VOL_MA20"]
    return {
        "symbol": symbol,
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
        "indicators": {c: _series(df, c) for c in
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
