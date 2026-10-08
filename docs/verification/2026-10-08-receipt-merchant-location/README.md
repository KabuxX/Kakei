# レシート店舗・住所登録の検証

2026-10-09 に、一時 SQLite と固定クライアントを使って確認した。普段使いの DB、OpenAI、Google の実サービスには接続していない。

## 結果

| チェック | 結果 |
| --- | --- |
| バックエンド全体 | 504 tests、成功 |
| frontend 全体 | 52 files / 293 tests、成功 |
| mock・DEMO 最終追試 | 3 files / 26 tests、成功 |
| 新レシート店舗 E2E | 5 tests、成功 |
| 既存税・iPhone・Agent 削除 E2E | 5 tests 成功、任意ローカル写真1件スキップ |
| 通常 build / DEMO build | 成功。通常 `front/dist` と `front/dist-demo` は別出力 |
| git diff --check | 成功 |

backend のテストは親環境の locked 依存を共有する `backend/.venv/bin/python` と `KAKEI_DB_PATH` の一時パスで実行した。frontend のポートを使うテストは sandbox の EPERM 後、承認済みコマンドで実行した。

```sh
KAKEI_DB_PATH="$(mktemp -d)/kakei.sqlite3" backend/.venv/bin/python -m unittest discover -s backend/tests -v
cd front
npm test
npm run build
npm run build:demo
npx playwright test --config playwright.receipt-location.config.cjs tests/e2e/receipt-location.spec.cjs
npx playwright test --config playwright.agent.config.cjs tests/e2e/receipt-tax.spec.cjs tests/e2e/iphone-receipts.spec.cjs tests/e2e/agent-delete.spec.cjs
npm test -- src/lib/mock-merchant-place.test.js src/lib/demo-api.test.js src/lib/demo-validation.test.js
```

専用サーバーは 127.0.0.1:8768、`TemporaryDirectory` の DB、`reuseExistingServer: false`。`create_app` の service/runner factory と Google Details の固定クライアントを使用する。検証専用 HTTP endpoint はその DB の取引数・関連行数・最終取引を読み出す。未解決時は件数が増えず、Google 採用後は住所欄 `null` と関連行1件を確認した。二重承認でも取引数は増えない。

## フローと画面確認

住所なし添付 → 地域入力 → 候補選択 → 変更案 → 保存 → 取引詳細を通した。名前だけの一意候補でも同一性不足では選択を求める仕様を維持し、地域を補う一意検索を別途検証した。店舗変更後は変更案を確認できず、本人住所を確認して同じ変更案を更新すると保存できる。

変更案の再確認では古い読取時 snapshot が使われる不具合を E2E で発見した。現在の確認を GET するよう修正し、現在版で再確認・同じ変更案 ID・版更新・保存をテストした。GET 中の店舗・金額編集を保持し、古い応答を拒否する unit regression も成功した。

アプリ内画面として `DESIGN.md` の白・淡青の表面、丸い操作部品、`MASTER.md` と ui-ux-pro-max のラベル、フォーカス、入力保持、再試行、横スクロールの基準を使って画像を開き目視確認した。ダッシュボードは変更していない。デスクトップ 1440×900、電話 375×812 を確認した。

- [デスクトップ候補](desktop-candidates.png)：地域入力を保持。候補の店舗名・住所・Google Maps 帰属と選択ボタンを表示。
- [電話の未解決入力](phone-unresolved.png)：縦並びのラベル、入力保持、住所欄の青いフォーカスリングが見える。
- [デスクトップの取得失敗](desktop-retry.png)：失敗理由と再読み込みボタン。再試行後に住所表示・選択・保存が成功。
- [デスクトップ保存後](desktop-saved.png)：取引状態と保存済み住所・帰属を表示。
- [電話の初期取引詳細](phone-saved.png)：金額・店舗・日時が直ちに見える。
- [電話の保存済み住所](phone-saved-address.png)：スクロール後に住所と Google Maps 帰属が収まる。

地域欄から Tab で住所欄へ移動し、候補ボタンをフォーカスして Enter で選択した。操作部品はチャット内のスクロールで到達できる。電話幅では document の横幅が viewport 以下であることも assert した。controller も候補・電話未解決・電話住所の画像を開いて確認した。

## 限界

実サービスへの接続、物理 iPhone のソフトウェアキーボード、実写真を指定する任意テストは未実施。電話幅は Chromium viewport とキーボード操作で確認した。画面全体のコントラスト測定・スクリーンリーダー監査は実施していない。既存の Node module type 警告、DEMO の chunk size 警告、Playwright の NO_COLOR/FORCE_COLOR 警告は残る。mock は架空の保存済み店舗参照と固定 Details のみを持ち、Agent 全体の mock 機能は追加していない。
