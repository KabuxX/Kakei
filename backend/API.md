# Kakei backend API リファレンス

この文書は、FastAPI で提供するローカル API の現行仕様です。Vite の mock API とは別のものです。起動入口は [`server.py`](server.py)、API 実装は [`api/app.py`](api/app.py)、取引の入力条件は [`services/validation.py`](services/validation.py) を参照してください。軌跡データはサーバー生成時に JSON から SQLite へ同期します。

## 接続と共通ルール

- 基本 URL は `http://localhost:8765` です。`127.0.0.1:8765` も利用できます。ポートはサーバー起動時の設定に合わせてください。
- `Host` は `localhost:<ポート>` または `127.0.0.1:<ポート>` に限ります。`POST`・`DELETE` などの変更リクエストには、同じアドレスの `Origin: http://<Host>` が必要です。条件を満たさない場合は `403 forbidden_origin` を返します。
- JSON の本文を送るときは `Content-Type: application/json` と正しい `Content-Length` が必要です。一般的な HTTP クライアントは後者を自動設定します。
- `GET /api/status`、`POST /api/initialize`、`GET /api/trajectory/{date}` は取引 DB の初期化前にも利用できます。それ以外の `/api/*` は初期化前に `409 not_initialized` を返します。
- 金額は円単位の整数です。日付は実在する日付を `YYYY-MM-DD` で指定します。
- JSON レスポンスには `Cache-Control: no-store` が付きます。`DELETE /api/transactions/{id}` の成功時は本文なしの `204` です。

## エンドポイント一覧

| メソッド | パス | 成功時 | 内容 |
| --- | --- | --- | --- |
| `GET` | `/api/status` | `200` | 取引 DB の初期化状態 |
| `POST` | `/api/initialize` | `201` | 取引を一度だけ一括登録 |
| `GET` | `/api/transactions` | `200` | 全取引を日付、ID の降順で取得 |
| `GET` | `/api/transactions/{id}` | `200` | ID に一致する取引を取得 |
| `POST` | `/api/transactions` | `201` | 取引を追加し、サーバーで ID を発行 |
| `DELETE` | `/api/transactions/{id}` | `204` | ID に一致する取引を削除 |
| `DELETE` | `/api/samples` | `200` | ID が `sample-` で始まる取引を DB から削除 |
| `GET` | `/api/trajectory/{date}` | `200` | 指定日の固定軌跡サンプルを取得 |

`{id}` は取引 ID です。URL のパスに使う際は必要に応じて URL エンコードしてください。`{date}` は `YYYY-MM-DD` 形式です。

## 初期化と取引

### `GET /api/status`

```json
{"initialized": false}
```

初期化済みなら `true` を返します。

### `POST /api/initialize`

新しい DB に取引の配列を一度だけ取り込みます。空配列も指定できます。登録は一括処理で、途中の取引が不正なら全件を取り消します。二度目の呼び出しは `409 already_initialized` です。本文の上限は 8 MiB です。

```json
{
  "transactions": [
    {
      "id": "example-income-20260901",
      "title": "給与",
      "date": "2026-09-01",
      "type": "income",
      "category": "収入",
      "amount": 300000
    }
  ]
}
```

成功時は `{"count": 1}` を返します。各取引には重複しない文字列の `id` が必要です。`title`、`date`、`type`、`category`、`amount` も必要です。支出の `merchant`・`paymentMethod` が欠けるか不正な場合は `null`、不正な `items` は空配列に正規化して取り込みます。初期化時は既存データの移行を考慮し、カテゴリと文字列長には新規追加時の制限を適用しません。ただし、日付・取引種別・金額の条件は新規追加時と共通です。

### 取引の形式

収入の例:

```json
{
  "id": "example-income-20260901",
  "title": "給与",
  "date": "2026-09-01",
  "type": "income",
  "category": "収入",
  "amount": 300000
}
```

支出の例:

```json
{
  "id": "example-expense-20260901",
  "title": "昼食",
  "date": "2026-09-01",
  "type": "expense",
  "category": "食費",
  "amount": 1200,
  "merchant": "店舗名",
  "paymentMethod": "e_money",
  "items": [{"name": "定食", "amount": 1200}]
}
```

`POST /api/transactions` では `id` を送らず、残りの項目を送ります。返却する `id` はサーバー生成の UUID です。新規追加時の条件は次のとおりです。

| 項目 | 条件 |
| --- | --- |
| `title` | 空白を除き 1〜60 文字 |
| `date` | 実在する `YYYY-MM-DD` 形式の日付 |
| `type` | `income` または `expense` |
| `category` | 収入は `収入`。支出は `食費`、`住まい`、`日用品`、`交通`、`娯楽`、`その他` のいずれか |
| `amount` | 1〜999,999,999 の整数。真偽値は不可 |
| `merchant` | 支出では必須。空白を除き 1〜60 文字 |
| `paymentMethod` | 支出では必須。`cash`、`credit_card`、`e_money`、`bank_account` のいずれか |
| `items` | 支出の品目配列。省略時は空配列。各品目は 1〜60 文字の `name` と正の整数 `amount` を持つ。空でない場合は品目金額の合計が取引金額と一致すること |

収入のレスポンスには `merchant`、`paymentMethod`、`items` は含まれません。初期化で取り込んだ支出のレスポンスでは、`merchant` と `paymentMethod` が `null` の場合があります。

### 取引の取得・追加・削除

- `GET /api/transactions` は `{"transactions": [取引, ...]}` を返します。日付の降順、同じ日付では ID の降順です。
- `GET /api/transactions/{id}` は `{"transaction": 取引}` を返します。見つからない場合は `404 not_found` です。
- `POST /api/transactions` は `id` 以外の取引項目を JSON 本文で受け取り、`{"transaction": 作成した取引}` を返します。本文の上限は 64 KiB です。`id` を送ると `400 validation_error` です。
- `DELETE /api/transactions/{id}` は成功時に `204` を返します。見つからない場合は `404 not_found` です。
- `DELETE /api/samples` は DB 内の ID が `sample-` で始まる取引を削除し、`{"deletedCount": 削除件数}` を返します。軌跡テーブルとその同期元 JSON は変更しません。

例えば、新しい DB を空で初期化し、支出を追加するには次のようにします。

```sh
curl -X POST http://localhost:8765/api/initialize \
  -H 'Origin: http://localhost:8765' \
  -H 'Content-Type: application/json' \
  --data '{"transactions":[]}'

curl -X POST http://localhost:8765/api/transactions \
  -H 'Origin: http://localhost:8765' \
  -H 'Content-Type: application/json' \
  --data '{"title":"昼食","date":"2026-09-01","type":"expense","category":"食費","amount":1200,"merchant":"店舗名","paymentMethod":"e_money","items":[{"name":"定食","amount":1200}]}'
```

## 日付別の軌跡サンプル

### `GET /api/trajectory/{date}`

取引サンプルは重複整理済み37件、軌跡は9月19〜30日の12日分です。サーバー生成時に `front/src/data/september-timeline.json` の固定サンプルを検証して SQLite に完全同期します。この GET は軌跡テーブルから指定日 1 日分を返します。JSON の変更は次のサーバー生成時に反映され、同期に失敗するとサーバー生成も失敗します。取引 DB の初期化や取引の更新には依存しません。形式が不正または実在しない日付は `400 invalid_date`、サンプルにない日付は `404 not_found` です。

```sh
curl http://localhost:8765/api/trajectory/2026-09-19
```

レスポンス例:

```json
{
  "places": {
    "shibuyaStarbucks": {
      "name": "スターバックス コーヒー 渋谷フクラス店",
      "address": "東京都渋谷区道玄坂1-2-3 渋谷フクラス1F",
      "coordinates": [139.6998, 35.6575],
      "sourceUrl": "https://store.starbucks.co.jp/detail-1651/"
    },
    "shibuyaMuji": {
      "name": "無印良品 渋谷公園通り",
      "address": "東京都渋谷区宇田川町19-7",
      "coordinates": [139.6991, 35.6623],
      "sourceUrl": "https://www.muji.com/jp/ja/shop/detail/045231"
    },
    "shibuyaLife": {
      "name": "ライフ 渋谷東店",
      "address": "東京都渋谷区東1-26-22",
      "coordinates": [139.7048, 35.654],
      "sourceUrl": "https://store.lifecorp.jp/detail/east829/"
    }
  },
  "days": [
    {
      "date": "2026-09-19",
      "events": [
        {"id": "2026-09-19-1", "time": "09:10", "placeId": "shibuyaStarbucks", "transactionId": "sample-20260919-a"},
        {"id": "2026-09-19-2", "time": "13:05", "placeId": "shibuyaMuji", "transactionId": "sample-20260919-b"},
        {"id": "2026-09-19-3", "time": "18:30", "placeId": "shibuyaLife", "transactionId": "sample-20260919-c"}
      ],
      "legs": [
        {"fromEventId": "2026-09-19-1", "toEventId": "2026-09-19-2", "modeHint": "walk"},
        {"fromEventId": "2026-09-19-2", "toEventId": "2026-09-19-3", "modeHint": "walk"}
      ]
    }
  ]
}
```

| 項目 | 内容 |
| --- | --- |
| `places` | その日の地点と経由地点だけを含む、地点 ID をキーとするオブジェクト。各地点には `name`、`address`、`coordinates`、`sourceUrl` があり、座標の順序は `[経度, 緯度]` |
| `days` | 指定日 1 件を含む配列。要素は `date`、`events`、`legs` を持つ |
| `events[]` | 時刻順の地点記録。`id`、`time`（`HH:mm`）、`placeId` を持ち、取引に対応する場合は `transactionId` も持つ。`placeId` は `places` のキーを参照する |
| `legs[]` | 2 件の記録間の区間。`fromEventId` と `toEventId` は `events` の ID を参照する。`modeHint` は移動手段のヒントで、現行サンプルでは `walk` または `train`。交通取引に対応する場合は `transportTransactionId`、経由地点がある場合は `viaPlaceIds` も持つ |

例えば 9 月 29 日の鉄道区間には次の値が含まれます。

```json
{"fromEventId": "2026-09-29-2", "toEventId": "2026-09-29-3", "modeHint": "train", "transportTransactionId": "sample-20260929-train"}
```

`transactionId` と `transportTransactionId` はサンプル取引の ID を示しますが、この API は取引本体を返しません。実際の SQLite の取引を削除・変更しても、軌跡テーブルの参照 ID は更新されません。軌跡テーブルを直接編集した場合は、次のサーバー生成時に JSON の値で上書きされます。軌跡の座標と区間はサンプルデータであり、道路や鉄道に沿った経路形状は返しません。

## エラー

エラーの JSON 形式は共通です。入力検証エラーでは `field` が付く場合があります。

```json
{"error": {"code": "validation_error", "message": "正しい日付を入力してください。", "field": "date"}}
```

| HTTP | `code` | 主な条件 |
| --- | --- | --- |
| `400` | `validation_error` | 取引・初期化データの入力条件違反 |
| `400` | `invalid_date` | 軌跡の日付の形式が不正、または実在しない |
| `400` | `invalid_content_type`、`invalid_body`、`invalid_json` | JSON 本文のヘッダーまたは内容が不正 |
| `403` | `forbidden_origin` | `Host` または変更リクエストの `Origin` が許可外 |
| `404` | `not_found` | 取引、軌跡サンプル、API が見つからない |
| `405` | `method_not_allowed` | 対象 API に使用できないメソッド |
| `409` | `not_initialized` | 取引 DB の初期化が必要 |
| `409` | `already_initialized` | 初期化済み DB に再度初期化を要求 |
| `413` | `body_too_large` | JSON 本文が上限を超過 |
| `500` | `database_error` | SQLite にアクセスできない |
