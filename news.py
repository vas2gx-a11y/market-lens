"""ニュース取得：銘柄ニュース（Googleニュース）と中央銀行・IMF等の公式発表＋市場の反応"""
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

import pandas as pd

from analysis import _cached, fetch_history

UA = {"User-Agent": "Mozilla/5.0 (compatible; MarketLens/1.0)"}
_TTL = 900  # 秒
_down_until: dict[str, float] = {}  # 取得元 → この時刻まではスキップ


def _unwrap(link: str) -> str:
    """Bing のクリック計測用URLから元記事のURLを取り出す"""
    if "bing.com/news/apiclick" in link:
        real = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url")
        if real:
            return real[0]
    return link


def _fetch_rss(url: str) -> list[dict]:
    def load():
        req = urllib.request.Request(url, headers=UA)
        for attempt in range(2):  # 一時的な失敗に備えて1回だけ再試行
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    root = ET.fromstring(r.read())
                break
            except Exception:
                if attempt:
                    raise
        out = []
        for it in root.iter():
            if it.tag.split("}")[-1] != "item":
                continue
            f = {c.tag.split("}")[-1]: (c.text or "").strip() for c in it}
            try:
                pub = parsedate_to_datetime(f.get("pubDate", ""))
            except (TypeError, ValueError):
                continue
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=pd.Timestamp.now(tz="UTC").tzinfo)
            out.append({"title": f.get("title", ""), "link": _unwrap(f.get("link", "")),
                        "source": f.get("source") or f.get("Source"),
                        "published": pd.Timestamp(pub).tz_convert("UTC")})
        return out

    return _cached(("rss", url), load, _TTL)


# ---------- 銘柄ニュース ----------

# Googleニュース検索用の日本語クエリ（未登録は銘柄名で検索）
NEWS_QUERY = {
    "7203.T": "トヨタ自動車", "6758.T": "ソニーグループ", "8306.T": "三菱UFJフィナンシャル",
    "AAPL": "アップル 米国株", "NVDA": "エヌビディア", "MSFT": "マイクロソフト 米国株",
    "BTC-USD": "ビットコイン 価格", "BTC-JPY": "ビットコイン 価格", "ETH-USD": "イーサリアム 価格",
    "XRP-USD": "XRP リップル 価格", "SOL-USD": "ソラナ 暗号資産", "BNB-USD": "BNB 暗号資産",
    "DOGE-USD": "ドージコイン", "ADA-USD": "カルダノ ADA", "LTC-USD": "ライトコイン",
    "^N225": "日経平均", "^GSPC": "S&P500", "^IXIC": "ナスダック", "^GDAXI": "ドイツ株 DAX",
    "JPY=X": "ドル円 為替", "EURJPY=X": "ユーロ円 為替", "GBPJPY=X": "ポンド円 為替", "AUDJPY=X": "豪ドル円 為替", "CHFJPY=X": "スイスフラン円 為替",
    "EURUSD=X": "ユーロドル 為替", "GBPUSD=X": "ポンドドル 為替", "CNY=X": "人民元 為替", "DX-Y.NYB": "ドル指数",
    "GC=F": "金価格", "CL=F": "原油価格",
}


_BLOG_SOURCES = {"note", "Ameba", "アメーバブログ", "はてなブログ", "livedoor Blog"}
_QUOTE_PAGE = re.compile(r"株価・株式情報|企業情報|レート・チャート|株価チャート|株主優待")


def symbol_news(symbol: str, name: str | None = None, limit: int = 10) -> dict:
    q = NEWS_QUERY.get(symbol) or (name or symbol)
    # クラウド環境では Google が拒否することがあるため、Bing → Yahoo Finance（英語）の順に切り替える
    sources = [
        ("Googleニュース", "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": f"{q} when:7d", "hl": "ja", "gl": "JP", "ceid": "JP:ja"})),
        ("Bingニュース", "https://www.bing.com/news/search?" + urllib.parse.urlencode(
            {"q": q, "format": "rss", "setlang": "ja", "cc": "JP", "mkt": "ja-JP"})),
    ]
    feed, provider, errors = [], None, []
    now = time.time()
    for label, url in sources:
        if _down_until.get(label, 0) > now:
            errors.append(f"{label}: 一時停止中（直近で取得失敗）")
            continue
        try:
            feed = _fetch_rss(url)
        except Exception as e:
            # 失敗した取得元は30分間スキップして、毎回のタイムアウト待ちを避ける
            _down_until[label] = now + 1800
            errors.append(f"{label}: {e}")
            continue
        if feed:
            provider = label
            break
    if not feed:
        feed, provider = _yahoo_news(symbol, name), "Yahoo Finance"
    error = " / ".join(errors) or None
    week_ago = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)
    feed = [it for it in feed if it["published"] >= week_ago] or feed
    out, seen = [], set()
    for it in sorted(feed, key=lambda x: x["published"], reverse=True):
        title = it["title"]
        # Googleニュースのタイトル末尾「 - 媒体名」を分離
        if it["source"] and title.endswith(" - " + it["source"]):
            title = title[: -len(it["source"]) - 3]
        # 同じ記事の転載と、株価・レートの情報ページは除外
        key = re.sub(r"\W", "", title)[:25]
        if key in seen or _QUOTE_PAGE.search(title) or (it["source"] or "") in _BLOG_SOURCES:
            continue
        seen.add(key)
        if len(out) >= limit:
            break
        out.append({"title": title, "link": it["link"], "source": it["source"],
                    "published": it["published"].isoformat()})
    return {"symbol": symbol, "query": q, "provider": provider, "error": error, "items": out}


def _yahoo_news(symbol: str, name: str | None) -> list[dict]:
    import yfinance as yf

    def load():
        try:
            news = yf.Search(symbol, news_count=10, max_results=0).news or []
            if not news and name:
                news = yf.Search(name, news_count=10, max_results=0).news or []
        except Exception:
            return []
        return [{"title": n.get("title", ""), "link": n.get("link", ""), "source": n.get("publisher"),
                 "published": pd.Timestamp(n.get("providerPublishTime", 0), unit="s", tz="UTC")} for n in news]

    return _cached(("ynews", symbol), load, _TTL)


# ---------- 中央銀行・国際機関 ----------

MARKETS = {
    # 銘柄: (表示名, 取引所タイムゾーン, 引け時刻)  FX・先物はほぼ24時間なのでUTC日付で判定
    "JPY=X": ("ドル円", "UTC", None),
    "EURUSD=X": ("ユーロドル", "UTC", None),
    "GBPUSD=X": ("ポンドドル", "UTC", None),
    "DX-Y.NYB": ("ドル指数", "America/New_York", 17),
    "GC=F": ("金", "America/New_York", 17),
    "^N225": ("日経225", "Asia/Tokyo", 15.5),
    "^GSPC": ("S&P500", "America/New_York", 16),
    "^GDAXI": ("DAX", "Europe/Berlin", 17.5),
    "^FTSE": ("FTSE100", "Europe/London", 16.5),
}

SOURCES = [
    {"id": "boj", "name": "日本銀行", "feed": "https://www.boj.or.jp/rss/whatsnew.xml",
     "page": "https://www.boj.or.jp/", "markets": ["JPY=X", "^N225"],
     "important": r"金融政策決定会合|当面の金融政策運営|金融市場調節方針|展望レポート|総裁|短観|基調的なインフレ|国債買入れ.*予定"},
    {"id": "mof", "name": "財務省", "feed": "https://www.mof.go.jp/news.rss",
     "page": "https://www.mof.go.jp/", "markets": ["JPY=X", "^N225"],
     "important": r"外国為替平衡操作|為替介入|財務大臣.*記者会見|国債発行計画|予算"},
    {"id": "fed", "name": "FRB", "feed": "https://www.federalreserve.gov/feeds/press_all.xml",
     "page": "https://www.federalreserve.gov/newsevents/pressreleases.htm", "markets": ["^GSPC", "DX-Y.NYB"],
     "important": r"FOMC|Federal Open Market Committee|monetary policy|discount rate|Beige Book|stress test"},
    {"id": "ecb", "name": "ECB", "feed": "https://www.ecb.europa.eu/rss/press.html",
     "page": "https://www.ecb.europa.eu/press/html/index.en.html", "markets": ["EURUSD=X", "^GDAXI"],
     "important": r"[Mm]onetary policy|Meeting of|press conference|Lagarde|interest rate"},
    {"id": "boe", "name": "英中銀", "feed": "https://www.bankofengland.co.uk/rss/news",
     "page": "https://www.bankofengland.co.uk/news", "markets": ["GBPUSD=X", "^FTSE"],
     "important": r"Monetary Policy|Bank Rate|Financial Stability|Bailey"},
    {"id": "imf", "name": "IMF", "feed": "https://mediacenter.imf.org/rss",
     "page": "https://www.imf.org/en/News", "markets": ["^GSPC", "GC=F"],
     "important": r"World Economic Outlook|Global Financial Stability|Fiscal Monitor|Georgieva|Japan|Article IV"},
]


def _reaction(symbol: str, published: pd.Timestamp) -> dict:
    """発表の前営業日終値 → 発表日（引け後なら翌営業日）終値の騰落と、5営業日後までの騰落"""
    name, tz, close_hour = MARKETS[symbol]
    out = {"symbol": symbol, "name": name, "d1": None, "d5": None}
    try:
        close = fetch_history(symbol, "2y")["Close"]
    except ValueError:
        return out
    local = published.tz_convert(tz)
    day = local.normalize().tz_localize(None)
    if close_hour is not None and local.hour + local.minute / 60 >= close_hour:
        day += pd.Timedelta(days=1)
    before = close[close.index < day]
    after = close[close.index >= day]
    if before.empty or after.empty:
        return out  # 未確定（市場がまだ開いていない等）
    base = before.iloc[-1]
    out["d1"] = round(float((after.iloc[0] / base - 1) * 100), 2)
    if len(after) >= 5:
        out["d5"] = round(float((after.iloc[4] / base - 1) * 100), 2)
    return out


def policy_news(days: int = 180) -> dict:
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)

    def load_source(src):
        try:
            return src, _fetch_rss(src["feed"]), None
        except Exception as e:  # 1つのサイトが落ちていても他は表示する
            return src, [], str(e)

    with ThreadPoolExecutor(max_workers=len(SOURCES)) as ex:
        results = list(ex.map(load_source, SOURCES))

    items, sources = [], []
    for src, feed, err in results:
        sources.append({"id": src["id"], "name": src["name"], "page": src["page"], "error": err,
                        "markets": [MARKETS[m][0] for m in src["markets"]]})
        pat = re.compile(src["important"])
        for it in feed:
            if it["published"] < cutoff:
                continue
            items.append({
                "source": src["id"],
                "title": it["title"],
                "link": re.sub(r"^http://", "https://", it["link"]).replace("europa.eu//", "europa.eu/"),
                "published": it["published"].isoformat(),
                "important": bool(pat.search(it["title"])),
                "_markets": src["markets"],
                "_ts": it["published"],
            })
    items.sort(key=lambda x: x["_ts"], reverse=True)
    # 価格データを先に並列取得してキャッシュに載せる
    with ThreadPoolExecutor(max_workers=len(MARKETS)) as ex:
        list(ex.map(lambda s: _reaction(s, pd.Timestamp.now(tz="UTC")), MARKETS))
    for it in items:
        ts = it.pop("_ts")
        it["reaction"] = [_reaction(m, ts) for m in it.pop("_markets")]
    return {"days": days, "sources": sources, "items": items}
