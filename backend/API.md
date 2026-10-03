# Kakei backend API リファレンス

この文書は、FastAPI で提供するローカル API の現行仕様です。Vite の mock API とは別のものです。起動入口は [`server.py`](server.py)、API 実装は [`api/app.py`](api/app.py)、取引の入力条件は [`services/validation.py`](services/validation.py) を参照してください。軌跡データは初回だけ JSON から SQLite に投入し、その後は SQLite に保存します。

## 接続と共通ルール

- 基本 URL は `http://localhost:8765` です。`127.0.0.1:8765` も利用できます。ポートはサーバー起動時の設定に合わせてください。
- `Host` は `localhost:<ポート>` または `127.0.0.1:<ポート>` に限ります。`POST`・`DELETE` などの変更リクエストには、同じアドレスの `Origin: http://<Host>` が必要です。条件を満たさない場合は `403 forbidden_origin` を返します。
- JSON の本文を送るときは `Content-Type: application/json` と正しい `Content-Length` が必要です。一般的な HTTP クライアントは後者を自動設定します。
- `GET /api/status`、`POST /api/initialize`、`GET /api/trajectory/{date}`、`POST`・`PUT`・`DELETE /api/trajectory` は取引 DB の初期化前にも利用できます。それ以外の `/api/*` は初期化前に `409 not_initialized` を返します。
- 金額は円単位の整数です。取引の `date` は実在する日付と時刻を `YYYY-MM-DDTHH:mm` で指定します。これはタイムゾーンのないローカル日時で、秒や UTC オフセットは含みません。
- JSON レスポンスには `Cache-Control: no-store` が付きます。`DELETE /api/trajectory` の `204` にも付きます。削除成功時の `204` は本文なしです。

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
| `GET` | `/api/trajectory/{date}` | `200` | 指定日の保存済み軌跡を取得 |
| `POST` | `/api/trajectory` | `201` | 日、イベント、区間、地点のいずれかを作成 |
| `PUT` | `/api/trajectory` | `200` | 指定した要素の内容を全体置換 |
| `DELETE` | `/api/trajectory` | `204` | 指定した要素を削除 |

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

成功時は `{"count": 1}` を返します。各取引には重複しない文字列の `id` が必要です。`title`、`date`、`type`、`category`、`amount` も必要です。初期化では従来データとの互換性のため `YYYY-MM-DD` も受け付け、同じ日付のレコードごとに安定した仮時刻を割り当て、`timeEstimated: true` として保存します。日時付きレコードの `timeEstimated` は `false` です。支出の `merchant`・`paymentMethod` が欠けるか不正な場合は `null`、不正な `items` は空配列に正規化して取り込みます。初期化時は既存データの移行を考慮し、カテゴリと文字列長には新規追加時の制限を適用しません。ただし、日付の実在性・取引種別・金額の条件は新規追加時と共通です。

### 取引の形式

収入の例:

```json
{
  "id": "example-income-20260901",
  "title": "給与",
  "date": "2026-09-01T09:17",
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
  "date": "2026-09-01T12:30",
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
| `date` | 実在する `YYYY-MM-DDTHH:mm` 形式のローカル日時 |
| `type` | `income` または `expense` |
| `category` | 収入は `収入`。支出は `食費`、`住まい`、`日用品`、`交通`、`娯楽`、`その他` のいずれか |
| `amount` | 1〜999,999,999 の整数。真偽値は不可 |
| `merchant` | 支出では必須。空白を除き 1〜60 文字 |
| `paymentMethod` | 支出では必須。`cash`、`credit_card`、`e_money`、`bank_account` のいずれか |
| `items` | 支出の品目配列。省略時は空配列。各品目は 1〜60 文字の `name` と正の整数 `amount` を持つ。空でない場合は品目金額の合計が取引金額と一致すること |

取引レスポンスにはサーバー管理の boolean `timeEstimated` が含まれます。日付だけの初期取込値や移行で補完した値では `true`、分単位で入力した値では `false` です。新規作成リクエストにはこのプロパティを含めません。収入のレスポンスには `merchant`、`paymentMethod`、`items` は含まれません。初期化で取り込んだ支出のレスポンスでは、`merchant` と `paymentMethod` が `null` の場合があります。

### 取引の取得・追加・削除

- `GET /api/transactions` は `{"transactions": [取引, ...]}` を返します。分単位日時の降順、同じ日時では ID の降順です。
- `GET /api/transactions/{id}` は `{"transaction": 取引}` を返します。見つからない場合は `404 not_found` です。
- `POST /api/transactions` は `id` 以外の取引項目を JSON 本文で受け取り、`{"transaction": 作成した取引}` を返します。本文の上限は 64 KiB です。`id` を送ると `400 validation_error` です。
- `DELETE /api/transactions/{id}` は成功時に `204` を返します。見つからない場合は `404 not_found` です。
- `DELETE /api/samples` は DB 内の ID が `sample-` で始まる取引を削除し、`{"deletedCount": 削除件数}` を返します。軌跡テーブルと初回投入元の JSON は変更しません。

例えば、新しい DB を空で初期化し、支出を追加するには次のようにします。

```sh
curl -X POST http://localhost:8765/api/initialize \
  -H 'Origin: http://localhost:8765' \
  -H 'Content-Type: application/json' \
  --data '{"transactions":[]}'

curl -X POST http://localhost:8765/api/transactions \
  -H 'Origin: http://localhost:8765' \
  -H 'Content-Type: application/json' \
  --data '{"title":"昼食","date":"2026-09-01T12:30","type":"expense","category":"食費","amount":1200,"merchant":"店舗名","paymentMethod":"e_money","items":[{"name":"定食","amount":1200}]}'
```

## 軌跡データ

### `GET /api/trajectory/{date}`

初回の DB 作成では `front/src/data/september-timeline.json` の固定軌跡12日分を検証して投入します。既存 DB に軌跡行があれば維持し、それ以降のサーバー生成時に JSON で上書きしません。初回投入に使う JSON が不正なら、そのサーバー生成は失敗します。この GET は SQLite から指定日 1 日分を返し、取引 DB の初期化や取引の更新には依存しません。形式が不正または実在しない日付は `400 invalid_date`、保存されていない日付は `404 not_found` です。

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
| `days` | 指定日 1 件を含む配列。要素は `date`、`events`、`legs` を持つ。編集中の日では両配列が空、または区間が一部欠ける場合がある |
| `events[]` | 時刻順の地点記録。`id`、`time`（`HH:mm`）、`placeId` を持ち、取引に対応する場合は `transactionId` も持つ。`placeId` は `places` のキーを参照する |
| `legs[]` | 2 件の記録間の区間。`fromEventId` と `toEventId` は `events` の ID を参照する。`modeHint` は移動手段のヒントで、現行サンプルでは `walk` または `train`。交通取引に対応する場合は `transportTransactionId`、経由地点がある場合は `viaPlaceIds` も持つ |

例えば 9 月 29 日の鉄道区間には次の値が含まれます。

```json
{"fromEventId": "2026-09-29-2", "toEventId": "2026-09-29-3", "modeHint": "train", "transportTransactionId": "sample-20260929-train"}
```

`transactionId` と `transportTransactionId` は取引 ID を示しますが、この API は取引本体を返しません。実際の SQLite の取引を削除・変更しても、軌跡テーブルの参照 ID は更新されません。軌跡の座標と区間は参考データであり、道路や鉄道に沿った経路形状は返しません。

### `POST`・`PUT`・`DELETE /api/trajectory`

変更用 API はこの3本です。どれも `Content-Type: application/json` の本文を要求し、上限は 1 MiB です。`kind` で `day`、`event`、`leg`、`place` を選びます。`POST` と `PUT` は `data` が必須、`DELETE` では指定できません。`PUT` は対象全体を置換するため、任意項目を省くと保存済みの値も外れます。識別子は変更できず、変更が必要な場合は削除と作成を行います。未知の項目は `400 validation_error` です。

| `kind` | 本文の識別子 | `data` |
| --- | --- | --- |
| `day` | `date` | `events` と `legs` の配列。各配列は空にできる。イベントには `id`、`time`、`placeId` と任意の `transactionId`、区間には `fromEventId`、`toEventId` と任意の区間属性を指定する |
| `event` | `date`、`id` | `time`、`placeId`、任意の `transactionId` |
| `leg` | `date`、`fromEventId`、`toEventId` | 任意の `modeHint`、`transportTransactionId`、`viaPlaceIds`。空の `{}` も可 |
| `place` | `id` | `name`、`address`、`coordinates`、`sourceUrl` |

次の4つは `POST` の本文例です。`PUT` でも同じ形を使います。`DELETE` では `data` を除きます。

```json
{"kind":"place","id":"example-place","data":{"name":"渋谷の店","address":"東京都渋谷区渋谷1-1-1","coordinates":[139.7,35.65],"sourceUrl":"https://example.com/place"}}
```

```json
{"kind":"day","date":"2026-10-03","data":{"events":[],"legs":[]}}
```

```json
{"kind":"event","date":"2026-10-03","id":"visit-1","data":{"time":"09:00","placeId":"example-place"}}
```

```json
{"kind":"leg","date":"2026-10-03","fromEventId":"visit-1","toEventId":"visit-2","data":{"modeHint":"walk"}}
```

例の区間を作る前に、同じ日の `visit-2` を登録してください。区間は隣接するイベント間に1件だけ登録できます。区間が参照中のイベント、イベントや経由地点が参照中の地点は個別に削除できません。日全体の削除ではその日のイベントと区間をまとめて削除し、共有地点は残します。時刻の変更で既存区間が隣接イベントを結ばなくなるときは `409 conflict` です。日全体の `PUT` を使えば、イベントと区間を原子的に組み替えられます。

`POST` は `201`、`PUT` は `200` と、識別子・正規化された `data` を含む操作本文と同じ形の JSON を返します。`day` のイベントは時刻順、区間は始点イベント順です。`DELETE` は本文なしの `204` です。作成・編集・削除は再起動後も残ります。全日を削除しても初期 JSON は再投入されません。現在の React 軌跡画面と Vite の mock API は固定 JSON を直接読み、この API の編集結果を表示しません。

## エラー

エラーの JSON 形式は共通です。入力検証エラーでは `field` が付く場合があります。

```json
{"error": {"code": "validation_error", "message": "正しい日時を入力してください。", "field": "date"}}
```

| HTTP | `code` | 主な条件 |
| --- | --- | --- |
| `400` | `validation_error` | 取引・軌跡・初期化データの入力条件違反 |
| `400` | `invalid_date` | 軌跡の日付の形式が不正、または実在しない |
| `400` | `invalid_content_type`、`invalid_body`、`invalid_json` | JSON 本文のヘッダーまたは内容が不正 |
| `403` | `forbidden_origin` | `Host` または変更リクエストの `Origin` が許可外 |
| `404` | `not_found` | 取引、指定日の軌跡、編集・削除対象、API が見つからない |
| `405` | `method_not_allowed` | 対象 API に使用できないメソッド |
| `409` | `not_initialized` | 取引 DB の初期化が必要 |
| `409` | `already_initialized` | 初期化済み DB に再度初期化を要求 |
| `409` | `conflict` | 軌跡の ID 重複、参照中の削除、イベントと区間の順序衝突 |
| `413` | `body_too_large` | JSON 本文が上限を超過 |
| `500` | `database_error` | SQLite にアクセスできない |
# Agent foundation additions

`PUT /api/transactions/{id}` replaces a transaction's editable fields and items while preserving its ID. The request uses the creation fields, plus optional boolean `confirmTime`. An unchanged estimated timestamp remains estimated unless explicitly confirmed. Referenced transactions cannot move to another day without a corresponding trajectory update.

`GET /api/trajectory` returns `{ "dates": ["YYYY-MM-DD", ...] }` in ascending order, including before transaction initialization. It reflects SQLite changes immediately and returns `Cache-Control: no-store`.

## Agent

すべて同じローカル Host / Origin 制約、JSONエラー形式、`Cache-Control: no-store` を使用します。

- `GET /api/agent/status` → `{available, missing, message, placesAvailable, placesMissing, placesMessage}`。モデル未設定でも取得可能。
- `GET /api/agent/threads` → `{threads}`。`POST` に `{}` → `201 {thread}`。
- `GET /api/agent/threads/{id}` → `{thread}`（messages, proposals含む）。`DELETE` → `204`。適用済み監査記録と取引は残ります。
- `POST /api/agent/threads/{id}/messages` に `{clientMessageId,text,receiptId?}` → `{message,proposal}`。再送時は同じIDと本文を使います。会話内の同時送信は409。
- `GET /api/agent/proposals/{id}` → `{proposal}`。
- `PUT /api/agent/proposals/{id}` に `{revision,commands}` → `{proposal}`。版が増え、再確認が必要。
- `POST /api/agent/proposals/{id}/approve` に `{revision}` → `{result}`。一括保存、同じ版の再送は同じ結果。
- `POST /api/agent/proposals/{id}/reject` に `{revision}` → `{proposal}`。

未設定503、モデル通信失敗502、時間切れ504、回数超過422。元データ・版・状態の競合は409です。生成中に家計データが変わった場合も409として再送を案内します。モデルは書き込み接続を持ちません。

### レシートのアップロード

`POST /api/agent/threads/{id}/receipts` は multipart の `file` 一つを受け取り、`201 {id,mimeType,sha256,pageCount,createdAt,duplicateReceiptIds}` を返します。JPEG/PNG/WebP/PDF、10 MiB以内、PDFは暗号化なし・3ページまで。拡張子と実内容が違うもの、破損、画像末尾への付加データを拒否します。
`GET /api/agent/threads/{id}/receipts/{receiptId}` は同じ会話のプレビュー、`GET /api/receipts/{id}` は取引に保存済みのファイルだけを返します。未保存ファイルは24時間で削除されます。

`GET /api/transactions/{id}/receipts` → `{receipts:[{id,mimeType,sha256,pageCount,createdAt}]}`。取引操作の変更案は `data.receiptIds` に同じ会話の未保存レシートIDを持てます。取引と添付は同じトランザクションで保存され、再承認でも増えません。却下・期限切れ・会話削除で未保存バイトを削除し、取引削除ではその添付も削除します。

レシートを添付したメッセージの結果は `receiptReview`（candidate, missingFields, itemMismatch, matches, receiptId, mimeType）を含みます。会話取得時は `receiptReviews` に戻ります。`POST /api/agent/threads/{id}/receipt-proposals` に `{receiptId,target:"new"|候補の取引ID,draft,currency:"JPY"}` を送ると確認用変更案を作成します。同じレシートの未保存・適用済み案があればその案を返し、内容変更は既存のPUTで行います。この時点では取引は保存しません。

### 軌跡の根拠

地点は世界座標（経度±180、緯度±90）に対応し、`placeEvidence: provider|user|legacy` と `attribution` を返します。ユーザー座標は住所・sourceUrlをnullにできます。訪問は `timeEvidence: exact|estimated|unknown|legacy`、`timeEvidenceNote` を持ち、unknown時だけtimeがnullです。推定には説明を付けます。取引の仮時刻をexactへ昇格する案は拒否します。
区間は `modeEvidence: fare|user|inferred|legacy` と `modeEvidenceNote` を持ちます。fareは交通費参照が必須、inferredは説明が必須です。交通費削除時は参照を外し推定へ変更します。新しい根拠付きイベントは送信した順序を保存し、既知の時刻が逆順なら拒否します。既存形式だけの操作では従来の時刻順整列を維持します。0・1地点の日も保存できます。

### 地点選択

未解決の地点を含む変更案は `metadata.placeCandidates` に `{placeId,query,candidates,selectedCandidateId?}` を持ち、承認できません。`POST /api/agent/proposals/{id}/places/selection` に `{revision,candidateId}` を送るとサーバー保存の座標を使って案を改訂します。クライアント座標は受け付けません。手動指定は `/places/manual` に `{revision,placeId,place:{name,coordinates:[longitude,latitude]}}`。どちらも `{proposal}` を返し、版が増えます。元データの変更や古い版は409です。

時刻不明・推定の訪問が複数ある案は `metadata.orderRequired=true` です。`POST /api/agent/proposals/{id}/order/confirmation` に `{revision}` を送ると表示順の確認を記録し、版を増やします。案の修正で確認は解除されます。地点・順序が未確認なら承認は409です。指定日だけの読み取りは `trajectory_context` ツール（100取引、64 KiBまで）が提供します。

### `GET /api/map-config`

初期化前も取得できるローカル画面用の地図設定。`Cache-Control: no-store`。
`{"mapboxPublicToken":"pk.…"}` を返します。`VITE_MAPBOX_ACCESS_TOKEN` が未設定、
または公開トークン形式でない場合は `null` です。他の環境変数や秘密キーは返しません。
ルート `.env` の変更はサーバー再起動後に反映されます。


## Web店舗検索の出典

assistantメッセージに `sources: [{id,title,url,kind,retrievedAt}]` を追加します。送信直後・再送・会話読込で同じ出典を返し、旧メッセージは空配列です。本文の `[source:<id>]` は当該メッセージの出典だけに解決します。

候補グループには `pipelineVersion: "web-mapbox-v1"`、`unlocatedCandidates`、`sources` が加わります。位置未確認の候補IDは `/places/selection` に使えません。旧候補IDの選択は維持します。地点には任意の `sources` と `geocoding`（Mapboxの住所・精度・永久保存情報）が追加され、軌跡読込と更新で保持します。

Agent処理期限120秒、processingリース130秒。検索停止でも保存済み検索履歴を参照できます。設定不足時も会話や既存地点の利用は可能で、追加の検索設定は `placesMissing` に返します。HTTP応答で資格情報を返しません。

### 住所表記の再検索と利用者による位置確認

`search_place.address_format` は `original`（省略時）、`without_postcode`、`japanese`。日本の同じ住所の表記を変えてMapboxへ再照会する。同一turn・同一店舗条件のWeb調査と抽出は共有し、座標照会は形式別に予算内で実施。海外住所は元の表記を維持する。`reuse_search_id` は結果のコピーで、再照会ではない。

日本の住所点が国・地域・番地と一致し一意でも、Mapboxの照合情報だけが未確認の場合、候補の `geocoding.verification` は `needs_confirmation`。選択APIで `{revision,candidateId,confirmed:true}` が必要で、未確認・文字列・数値は拒否する。選択後は `user_confirmed` として保存し、元の `matchCode` を変更しない。旧候補の選択には追加属性不要。別番地・郵便番号矛盾・国不一致・街区中心・複数の住所点は引き続き選択不可。

## 取引先住所

支出の任意項目 `merchantAddress`（文字列/null、500 Unicodeコードポイント以内）。前後空白・改行コードを正規化。POST/初期取込の省略はnull、PUT/agent更新の省略は既存値維持、明示null/空白は消去。保存住所のある取引の店名変更では住所を明示する。収入に住所は保存しない。

- `GET /api/transaction-addresses`: `{addresses:[{transactionId,places:[{placeId,name,address,coordinates,status}]}]}`。関連地点のない取引は省略。
- `GET /api/transaction-addresses/{id}`: `{address:{transactionId,places:[]}}`。IDはURLエンコード。取引なし404、未初期化409。
- `PATCH /api/transaction-addresses/{id}`: `{merchantAddress,expected:{merchant,merchantAddress}}`。住所列のみ更新し `{transaction:...}` を返す。expectedは読取値そのもの。店名・住所の競合409、収入/不正入力400。

statusは `matched` / `trajectory_only` / `needs_review`。日別軌跡の各eventに同じ派生値を `locationStatus` として返す（保存コマンドへ含めない）。needs_reviewの旧座標は記録として返るが、新住所の地図表示には使用しない。
