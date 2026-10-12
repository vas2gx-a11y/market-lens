import json
import os
import re

import anthropic
from flask import Flask, jsonify, render_template, request

import analysis
import news

app = Flask(__name__)

SYMBOL_RE = re.compile(r"^[A-Za-z0-9^=.\-]{1,20}$")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")


def _symbol(value: str | None) -> str:
    s = (value or "").strip().upper()
    if not SYMBOL_RE.match(s):
        raise ValueError("銘柄コードが不正です")
    return s


@app.errorhandler(ValueError)
def bad_request(e):
    return jsonify({"error": str(e)}), 400


@app.get("/")
def index():
    return render_template("index.html", ai_enabled=bool(os.environ.get("ANTHROPIC_API_KEY")))


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/api/analyze")
def api_analyze():
    symbol = _symbol(request.args.get("symbol"))
    period = request.args.get("period", "1y")
    horizon = max(5, min(int(request.args.get("horizon", 20)), 60))
    interval = request.args.get("interval", "1d")
    if interval != "1d" and interval not in analysis.INTRADAY:
        raise ValueError("足種が不正です")
    return jsonify(analysis.analyze(symbol, period, horizon, interval))


@app.get("/api/backtest")
def api_backtest():
    symbol = _symbol(request.args.get("symbol"))
    period = request.args.get("period", "10y")
    if period not in ("2y", "5y", "10y", "max"):
        raise ValueError("期間が不正です")
    threshold = max(10, min(int(request.args.get("threshold", 30)), 90))
    return jsonify(analysis.backtest(symbol, period, threshold))


def _corr_params():
    period = request.args.get("period", "5y")
    freq = request.args.get("freq", "W")
    if period not in ("1y", "3y", "5y") or freq not in ("W", "D"):
        raise ValueError("期間または頻度が不正です")
    return period, freq


@app.get("/api/correlation")
def api_correlation():
    return jsonify(analysis.correlation(*_corr_params()))


@app.get("/api/correlation/pair")
def api_correlation_pair():
    period, freq = _corr_params()
    a, b = _symbol(request.args.get("a")), _symbol(request.args.get("b"))
    return jsonify(analysis.rolling_correlation(a, b, period, freq))


@app.get("/api/fundamental")
def api_fundamental():
    return jsonify(analysis.fundamental_analysis(_symbol(request.args.get("symbol"))))


@app.get("/api/news")
def api_news():
    symbol = _symbol(request.args.get("symbol"))
    name = analysis.fetch_info(symbol)["name"]
    return jsonify(news.symbol_news(symbol, name))


@app.get("/api/policy")
def api_policy():
    return jsonify(news.policy_news())


@app.get("/api/quotes")
def api_quotes():
    symbols = [s for s in (request.args.get("symbols") or "").split(",") if s][:30]
    out = []
    for s in symbols:
        try:
            out.append(analysis.quote(_symbol(s)))
        except Exception as e:
            out.append({"symbol": s, "error": str(e)})
    return jsonify(out)


SYSTEM_PROMPT = """あなたは金融市場のテクニカル分析アナリストです。
与えられた指標データだけを根拠に、日本語で簡潔な分析コメントを書いてください。

形式（Markdown）:
## 概況
## テクニカル評価
## 予測モデルの解釈
## 注目ポイント・リスク

ルール:
- 出来高・ファンダメンタル（PER/PBR/配当利回り等）があれば評価に含める
- 数値を引用して根拠を示す。データに無い情報（決算・ニュース等）は推測しない
- 売買の推奨や断定的な将来予測はせず、シナリオ（強気/弱気）として述べる
- 全体で400〜600字程度"""


def _fa_summary(symbol):
    fa = analysis.fundamental_analysis(symbol)
    if not fa["available"]:
        return "対象外"
    return {"スコア": fa["score"], **{c["name"]: {i["name"]: i["value"] for i in c["items"]} for c in fa["categories"]},
            "業績推移": fa["history"], "アナリスト": fa["analyst"]}


@app.post("/api/ai")
def api_ai():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({"error": "ANTHROPIC_API_KEY が設定されていません"}), 503
    body = request.get_json(silent=True) or {}
    symbol = _symbol(body.get("symbol"))
    horizon = max(5, min(int(body.get("horizon", 20)), 60))
    data = analysis.analyze(symbol, "1y", horizon)
    fc = data["forecast"]
    summary = {
        "銘柄": f'{data["name"]} ({symbol})',
        "日付": data["date"],
        "終値": data["last"],
        "前日比%": data["change_pct"],
        "騰落率%": data["perf"],
        "最新指標": data["latest"],
        "シグナル": data["signals"],
        "テクニカル分析": {c["name"]: {i["name"]: i["value"] for i in c["items"]} for c in data["technical"]["categories"]},
        "ファンダメンタル分析": _fa_summary(symbol),
        "出来高": data["volume_stats"],
        "ファンダメンタル": data["fundamentals"],
        "予測": {
            "期間(営業日)": horizon,
            "中央値": fc["target"],
            "変化率%": fc["change_pct"],
            "95%区間": fc["range95"],
            "上昇確率%": fc["prob_up"],
            "年率ボラティリティ%": fc["volatility_annual"],
            "モデル": "対数価格の線形回帰(120日)＋ボラティリティ帯",
        },
    }

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": json.dumps(summary, ensure_ascii=False)}],
        )
    except anthropic.RateLimitError:
        return jsonify({"error": "APIのレート制限に達しました。少し待って再試行してください"}), 429
    except anthropic.APIStatusError as e:
        return jsonify({"error": f"Claude APIエラー ({e.status_code})"}), 502
    except anthropic.APIConnectionError:
        return jsonify({"error": "Claude APIに接続できませんでした"}), 502

    if response.stop_reason == "refusal":
        return jsonify({"error": "AIがこのリクエストへの回答を控えました"}), 422
    text = "".join(b.text for b in response.content if b.type == "text")
    return jsonify({"comment": text, "model": response.model})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
