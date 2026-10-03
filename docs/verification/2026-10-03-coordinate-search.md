# 柔軟な座標検索の検証

2026-10-03。`feat/web-place-search`、基点`b23946e`への追加改善。隔離worktreeで実装し、稼働アプリのDBと`.env`は変更していない。

## 実装と範囲

system promptに店名・支店名・根拠のある目印を使う検索方針と、Mapboxへ渡す住所表記を切り替える手順を追加した。`search_place.address_format`は`original`、`without_postcode`、`japanese`。同一条件のWeb調査結果を同一ターンで共有し、座標検索のみを別表記で再実行する。履歴にも形式を保存し、旧履歴の省略値はoriginalとして扱う。

日本の住所正規化を改善し、住所が一致して照合情報だけが不十分な場合は利用者の確認を求める。地図・住所確認前の候補選択はサーバーで拒否し、保存時はuser_confirmedを付ける。元のmatchCodeは保持する。異なる番地、明示的な郵便番号の矛盾、街区中心、国違い、曖昧な複数座標は選べない。

## 自動検証

- Backend: `python -m unittest discover -s backend/tests` — 244件成功。
- Front: `npm --prefix front test` — 21ファイル、104件成功。
- Build: `npm --prefix front run build` — 成功。既存Mapboxチャンクの500 kB警告あり。
- Browser: `playwright.agent-search.config.cjs`、一時DB、port8767。18件成功。
- 回帰テストで日本語住所の同値性、3形式の送信内容、Web結果の共有、不正形式、確認なし選択の拒否、保存後の根拠維持を検証した。

独立コードレビューで構造化郵便番号の矛盾を見逃す問題と、非objectのmatch_codeで例外になる問題を発見。両方とも失敗を再現するテストを先に追加し修正した。照合情報の欠落と不正な型を区別し、後者は候補にしない。

フロントテストの初回はサンドボックスのlisten制限により失敗し、許可後の再実行で成功。ブラウザの最初の起動はworktreeにvenvがないため失敗し、既存のKAKEI_TEST_PYTHON対応configで絶対パスを指定した。製品コードへの回避変更はない。

## 実API確認

Mapboxを3回、指定モデルgpt-6-lunaを1回呼び出した。Web検索の追加呼出しや本番DBへの書込みはない。[記録](2026-10-03-coordinate-search/live-results.json)には応答本文や暗号化された推論データを含めていない。

対象: ドトールコーヒーショップ 西鉄福岡駅店、`〒810-0001 福岡県福岡市中央区天神2-11-3`。

| 形式 | Mapboxの番地・街区・丁目照合 | この実装の結果 |
| --- | --- | --- |
| original | unmatched | 要確認候補 |
| without_postcode | unmatched | 要確認候補 |
| japanese | matched | 要確認候補 |

返却住所は`日本, 〒810-0001 福岡県福岡市中央区天神２丁目１１番３号`、座標は経度130.3990083・緯度33.5900778、address/rooftop。日本語表記への変更で番地等の照合が改善したが、confidenceがなく、郵便番号の照合情報も不足するため自動確認済みとは扱わない。利用者が地図と住所を確認する必要がある。元の照合情報を一致へ書き換えていない。

モデル検証は、合成した座標照合失敗のtool応答を実モデルへ渡す限定的な挙動確認である。同じplace_idと店舗条件を維持し、address_format=without_postcodeを選ぶことを確認。usageはinput2123/output74/total2197。実AgentRunner全体での再検索成功や、任意店舗の特定を保証するものではない。

## 画面確認

確認用fixtureを使い、1440pxと375pxで住所、地図リンク、確認チェックボックス、候補選択を目視確認した。横方向のはみ出しはなく、確認欄は会話のスクロール領域内で表示される。画像は実店舗の検索結果ではない。

- [Desktop](2026-10-03-coordinate-search/coordinate-review-desktop.png)
- [Phone](2026-10-03-coordinate-search/coordinate-review-phone.png)
