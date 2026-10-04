# フロント開発環境

## ソースの配置

`src` 内の JSX は役割ごとに分類しています。

| フォルダ | 内容 |
| --- | --- |
| `src/app/` | `main.jsx` とアプリ全体を組み立てる `App.jsx` |
| `src/pages/` | 概要、軌跡、Agent Chat、取引詳細・編集・削除の各ページ |
| `src/components/layout/` | サイドバーとトップバーを含む共通レイアウト |
| `src/components/agent/` | 会話操作、変更案、地点候補、軌跡作成結果 |
| `src/components/transactions/` | 取引フォーム、ダイアログ、住所、添付レシート |
| `src/components/trajectory/` | 地図、軌跡入力、削除内容 |
| `src/components/places/` | 座標の根拠、出典、Google検索結果 |
| `src/components/receipts/` | レシート確認と計算結果 |
| `src/tests/` | JSX のテスト。フックと API のモックもここから参照 |

状態管理のフックは `src/use*.js`、API と純粋関数は `src/lib/`、
固定データは `src/data/` に置いています。JavaScript のテストは既存の場所にあります。
HTML の入口は `/src/app/main.jsx` です。

## 起動

依存パッケージを入れてから、使うデータ元に合わせて起動します。

```sh
cd front
npm ci
```

## mock 環境（固定 JSON データ）

```sh
npm run dev:mock
```

`http://127.0.0.1:5173/` を開きます。バックエンドは不要です。mock API の初期データは `src/data/september-transactions.json` の2026年9月の重複整理済み37件の取引で、軌跡は `src/data/september-timeline.json` の9月19〜30日の12日分を組み合わせて表示します。旧16件の `src/data/old-samples.json` は保存用で、mock 環境には読み込みません。画面からの追加・削除は開発サーバーのメモリに反映され、サーバーを再起動すると JSON の内容に戻ります。JSON ファイルを書き換えても画面に反映するには開発サーバーを再起動してください。

## 実際の API データ

別のターミナルで [バックエンドの起動手順](../backend/README.md) に従い、API を `127.0.0.1:8765` で起動します。その後、フロントを起動します。

```sh
cd front
npm run dev:api
```

`http://127.0.0.1:5173/` を開きます。`/api` のリクエストはバックエンドへ転送され、取引の追加・削除は SQLite に保存されます。別の API アドレスを使う場合は `KAKEI_API_TARGET=http://127.0.0.1:8765 npm run dev:api` のように指定できます。

通常の `npm run build` と、バックエンドが配信する `front/dist/` は実際の API を使います。

軌跡画面は `GET /api/trajectory` の記録日一覧と `GET /api/trajectory/{date}` の保存内容を読み込みます。月や年は固定せず、訪問地点が0件・1件の日も表示できます。APIへの変更は日付の選択時または画面を開き直したときに反映されます。

Agent Chat は `#agent` で開きます。会話履歴、変更前後の確認、取引案の修正・保存・却下を扱います。保存後は取引を再取得し、軌跡の表示も更新します。通常のメッセージ入力で Enter を押しても変更案は保存されません。モデルの設定方法は backend/README.md を参照してください。

隔離された SQLite と偽の AI 応答でのブラウザ検証:
`npm run test:e2e -- --config=playwright.agent.config.cjs tests/e2e/app.spec.cjs`

レシートは添付後に送信すると読み取りが始まります。不明項目を補い、保存先（新規追加または一致候補）を選んで「変更案を確認」、差分を見て「確認して保存」と進みます。品目合計の不一致は手動修正または「品目を保存しない」で解決します。保存した原本は取引詳細のレシート欄から開けます。

軌跡の変更案では、同名店でも住所・出典を確認して地点候補を選びます。地点検索が使えない場合は確認した経度・緯度を入力できます。時刻不明・推定の訪問が複数あるときは並び順を確認します。「内容を修正」で時刻・根拠・順序を直すと、再確認が必要です。軌跡ページはAPI保存済みの日付と根拠を表示し、線と距離を概算として示します。

### 地図の公開トークン

ルート `.env` の `VITE_MAPBOX_ACCESS_TOKEN=pk.…` を FastAPI が起動時に読み込みます。
本番画面は `GET /api/map-config` で公開トークンを取得するため、トークンはフロントのビルド成果物に埋め込まれません。
設定変更後は FastAPI を再起動し、画面を再読み込みしてください。再ビルドは不要です。
`dev:api` は同じAPIを使用し、`dev:mock` はViteサーバーが読み込んだ公開トークンを返します。
`sk.` で始まる秘密トークンは使用できません。

### 住所の入力・確認

取引追加の「住所（任意）」と取引詳細の「住所を追加／編集」から記録できます。空欄で保存すると取引の住所だけを消去します。関連軌跡の住所は別の表示として残り、選んで編集欄へ取り込み、保存できます。

住所と保存地点が一致しない場合は地図リンク・訪問ピン・接続区間を非表示にし、「Agentで位置を再確認」で依頼文を準備します。自動送信はしません。CSVの末尾に「取引先住所」「関連軌跡住所」を追加し、住所API失敗時は再試行を案内します。mockモードでも住所のGET/PATCHとCSVを利用できます。

軌跡の通常地図はGoogle Maps JavaScript APIとAdvanced Markerを使います。`/api/map-config`の`googleMapsBrowserKey`と`googleMapId`を読みます。サーバーのPlacesキーをフロントへ組み込まないでください。キーの用途・制限はbackend/README.mdを参照してください。地図が使えない場合も訪問時系列を表示します。利用・データ取扱説明は`/google-maps-usage.html`から常時閲覧できます。旧`TrajectoryMap.jsx`とMapbox依存は保存しています。
