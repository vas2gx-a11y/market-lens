# Market Lens — 投資分析・予測ページ

日本株・米国株・暗号資産・為替/指数のチャート、テクニカル指標、統計モデルによる価格予測、Claude による AI 分析コメントを表示する Flask アプリ。

## 機能
- ローソク足チャート + SMA20/50/200・ボリンジャーバンド・出来高
- RSI(14)・MACD(12,26,9)
- シグナル総合スコア（強気/中立/弱気）
- 価格予測：直近120日の対数価格トレンド + ボラティリティによる 68%/95% 予測区間、上昇確率
- AI分析コメント（`ANTHROPIC_API_KEY` 設定時のみ）
- ウォッチリスト（ブラウザに保存）

銘柄コードは Yahoo Finance 形式：`7203.T`（東証）、`AAPL`、`BTC-USD`、`JPY=X`、`^N225` など。

## ローカル実行
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-ant-... .venv/bin/python app.py   # http://localhost:5000
```

## Render へのデプロイ
1. このリポジトリを GitHub に push
2. Render ダッシュボード → **New → Blueprint** → リポジトリを選択（`render.yaml` を自動認識）
3. 環境変数 `ANTHROPIC_API_KEY` を入力（AI機能が不要なら空でOK）

## 注意
表示される情報・予測は参考情報であり、投資助言ではありません。
