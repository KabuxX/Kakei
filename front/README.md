# フロント開発環境

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
