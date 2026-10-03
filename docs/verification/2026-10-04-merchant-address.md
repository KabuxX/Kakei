# 取引先住所機能の検証（2026-10-04）

実装範囲: 任意住所の入力・編集・消去、SQLite移行、レシート抽出・確認、agent検索の住所条件、取引と軌跡の対応判定、CSV出力。

## 固定テスト

- Backend: `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests`。260件成功。旧DB移行、省略維持と明示消去、旧提案の競合互換、住所専用PATCH、共有地点、検索条件と履歴、レシート原本の紐づきを確認。
- Front: `npm --prefix front test`。117件成功。住所入力の500コードポイント境界、保存失敗時の入力保持、保存先別のレシート編集状態、差分、地図の中間訪問除外、CSVエスケープ・取得失敗を確認。
- Browser: `KAKEI_TEST_PYTHON=/Users/spco/Kakei/backend/.venv/bin/python npm --prefix front run test:e2e -- --config playwright.agent-search.config.cjs`。20件成功。一時DBを使用。住所保存→再読込→消去→参照住所のコピー→住所変更→位置要確認→agent提案の地点選択・保存→matchedへの復帰まで操作。
- `npm --prefix front run build` 成功。既存のバンドルサイズ警告あり。
- `git diff --check` 成功。

既存BackendテストにSQLite ResourceWarningあり。初回のFrontテストはsandboxによるloopbackのEPERMで失敗し、許可済み環境で再実行した。Browserのテスト準備ではAPI作成後の画面再読込と、非表示フォームを除外するrole selectorへ修正した。

## 実API

本番DBを使用せず、一時DBに架空の検証取引を作成。画像読取1回・agent会話1回。既存.envは変更せず、キーは出力していない。

- 提供済みレシート画像 `recipt.png`: 店舗「セブン-イレブン 千代田店」、住所「東京都千代田区二番町8-8」を抽出。
- 「ドトールコーヒーショップ 西鉄福岡駅店」の保存住所「福岡県福岡市中央区天神2-11-3」が、search_placeのaddressとtransaction由来evidenceへ渡ったことを検索記録で確認。根拠のないcountry_codeは指定されていない。
- 同住所の公式店舗候補を取得。Mapbox照合情報が不十分なため、利用者確認が必要な候補として説明された。自動的な座標確定・保存はしていない。
- 会話後に元の取引が変更されていないことを確認。

## 画面

375px・1440pxで長い住所の折返し、入力エラー、フォーカス枠、保存・キャンセルを確認。ダッシュボードの最初の表示に選択期間と収支が出る既存ブラウザ検証も成功。

- [住所編集・phone](2026-10-04-merchant-address/address-edit-phone.png)
- [住所編集・desktop](2026-10-04-merchant-address/address-edit-desktop.png)
- [取引住所・phone](2026-10-04-merchant-address/transaction-address-phone.png)

## 実装上の判断

- 旧提案の互換化はfingerprint計算だけに適用。通常のJSONでnullを削ると明示消去の意味が失われるため、コマンドではnullを保持。
- 入力正規化では住所の省略を維持し、支出の読取応答ではnullを返す。
- サンプル置換の安全確認にも住所を含め、住所を編集したサンプルの上書きを防ぐ。
- 保存用のStore読取と、locationStatusを付ける表示用読取を分離。
- 軌跡住所のコピーは入力欄へ表示してから保存する。確認のため操作が1回増える。
- UIテストは既存ファイルとMerchantAddress.test.jsxへまとめ、同じ振る舞いを重複検証しない。

## 最終レビュー

独立したレビュアーが 1f88174..b74dc0d を確認。Criticalなし、Important 1件、Minor 1件。

- Important: レシート住所を長さ検証前に共通正規化。保存済みreviewの空白住所も未読取として扱い、未編集時は住所キーを送信しない。既存住所の保持と明示消去、CRLF正規化後500文字を回帰検証。Backend / Frontで失敗を確認後に修正し、全体260 / 117件、Browser20件成功。
- Minor（保留）: mockの住所照合はNFKCと空白除去のみで、本番が同じ住所と認める「丁目・番・号」等を要確認と判定する場合がある。実API利用には影響しない。
- 判断: distはレビュー対象外だったため、修正後の生成物をブラウザ20件で検証し、main統合後にも再生成する。誤りがあれば配信画面がソースとずれる。
- 判断: 稼働環境への反映はレビュー後の工程として、DBバックアップ・再起動・読取検証を行う。誤りがあれば実アプリに未反映となる。

mainへの反映結果は作業完了時に追記する。
