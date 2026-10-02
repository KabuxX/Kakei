# 軌跡 JSON と SQLite の同期設計

## 目的と範囲

`front/src/data/september-timeline.json` の軌跡データを、既存の取引 DB と同じ SQLite ファイルに保存する。サーバー生成時に JSON を正本として軌跡テーブルを完全同期し、`GET /api/trajectory/{date}` は DB から現在と同じレスポンス形式を返す。2026 年 9 月の 30 日分について、API の結果は JSON の日別データと一致する。

軌跡ページと Vite の mock API は今回変更せず、フロントの JSON を読み続ける。取引テーブル、取引の初期化・削除、既存の API 契約も維持する。軌跡データを編集する API は追加しない。JSON ファイルを変更した場合、次のサーバー生成時に DB に反映する。稼働中のファイル監視は行わない。

## 現状

- `backend/schema.py` は `meta`、`transactions`、`transaction_items` を作成し、古い `items_json` を子テーブルへ移行する。
- `backend/server.py` はアプリ生成時に軌跡 JSON を読み、`GET /api/trajectory/{date}` ではメモリ上の JSON を日付で検索する。取引 DB が未初期化でもこの GET を提供する。
- JSON は `places` 辞書と `days` 配列で構成される。各日は順序付きの `events` と `legs` を持つ。現行サンプルは地点 10 件、日 30 件、イベント 120 件、区間 90 件である。
- イベントと交通区間の取引 ID は、取引サンプルを参照するための文字列である。SQLite 上の取引は後から削除できる。

## 保存モデル

| テーブル | 主な列とキー | 役割 |
| --- | --- | --- |
| `trajectory_places` | `id` 主キー、`name`、`address`、`longitude`、`latitude`、`source_url` | `places` の地点。座標は JSON の `[経度, 緯度]` に戻せるよう別列で保存する |
| `trajectory_days` | `date` 主キー | `days[]` の日付を独立して表す |
| `trajectory_events` | `id` 主キー、`day_date` 外部キー、`position`、`time`、`place_id` 外部キー、`transaction_id` 任意 | その日のイベント。`(day_date, position)` は一意とし、JSON 配列の順序を保存する |
| `trajectory_legs` | `(day_date, position)` 主キー、`from_event_id`・`to_event_id` 外部キー、`mode_hint` 任意、`transport_transaction_id` 任意、`has_via_places` | その日の区間。JSON 配列の順序と、空の `viaPlaceIds` が明示されたかどうかを保存する |
| `trajectory_leg_via_places` | `(day_date, leg_position, via_position)` 主キー、区間への外部キー、`place_id` 外部キー | 任意の `viaPlaceIds` を順序付きで保存する |

地点・日・イベント・区間・経由地点の参照は DB 外部キーで守り、接続では既存どおり `PRAGMA foreign_keys = ON` を設定する。イベント間の順序、区間が隣り合うイベントを結ぶこと、時刻の昇順など、複数行にまたがる条件は同期前の検証で守る。

`transaction_id` と `transport_transaction_id` は `transactions.id` への外部キーにしない。固定軌跡サンプルと取引 DB は独立しており、サンプル取引の削除や、未初期化の取引 DB でも軌跡を取得できる必要があるためである。両 ID はレスポンスで元の値を返す。

## 同期の流れ

1. `create_app` のサーバー生成時に JSON を読み込む。テストで別のフィクスチャを渡せるよう、同期処理はファイルの読み込みと DB 書き込みを分ける。
2. 書き込み前に、トップレベルと各要素の既知の項目・型、必須文字列、実在する `YYYY-MM-DD` 日付、`HH:mm` 時刻、有限の東京範囲内の座標、HTTPS の出典 URL、JSON の重複キー・ID・日付、地点・イベントの参照、イベントと区間の順序を検証する。各日は 2 件以上のイベントと、隣接するイベントを結ぶ `イベント数 - 1` 件の区間を持つ。`modeHint` は省略、`walk`、`train`、`bus` を許可し、鉄道・バス区間には `transportTransactionId` を要求する。取引 DB の内容とは突き合わせない。未知の項目は黙って捨てず、同期を失敗させる。
3. `BEGIN IMMEDIATE` から始まる 1 回の DB トランザクションで、既存の軌跡行を子から親の順に削除し、検証済み JSON の全行を親から子の順に挿入する。これにより、追加・更新・削除を含め JSON と完全一致させる。取引関連テーブルには書き込まない。
4. 同期が失敗したらロールバックしてサーバー生成を失敗させる。既存の軌跡行を部分的に置き換えた状態では提供しない。再起動を繰り返しても同じ JSON から同じ API データになる。

JSON を変更しても稼働中のサーバーには反映しない。次にサーバーを生成した時点で同期する。DB 内の軌跡行を直接編集しても、次の同期で JSON の値に戻る。

## 読み取り API とエラー

`GET /api/trajectory/{date}` は現在の URL、日付検証、成功時の `{ "places": { ... }, "days": [{ "date": ..., "events": [...], "legs": [...] }] }`、`Cache-Control: no-store` を維持する。`places` には当日のイベントまたは経由地点から参照される地点だけを含める。イベント、区間、経由地点の配列は保存した `position` 順に組み立て、任意項目は元の JSON にある場合だけ返す。

日付の形式不正・存在しない日付は従来どおり `400 invalid_date`、保存されていない日付は `404 not_found` とする。取引 DB が未初期化でも取得できる。DB 読み取り失敗は既存の `500 database_error` 形式を使う。JSON 不正や同期失敗は起動時のエラーとして表面化させ、古い JSON や空レスポンスへの暗黙の切り替えは行わない。

## 検証とドキュメント

- 一時 DB に現行 JSON を同期し、30 日すべての GET レスポンスが JSON から期待される日別データと一致することを確認する。地点 10 件、日 30 件、イベント 120 件、区間 90 件も確認する。
- 変更したテスト用 JSON で再生成し、追加・更新・削除と二度目の同期が正しく動くことを確認する。経由地点の順序と任意項目も検証する。
- 不正な JSON と DB 挿入失敗で同期がロールバックし、既存の軌跡と取引データが残ることを確認する。
- 既存の取引 API、未初期化時の軌跡 GET、400・404・500、旧 `items_json` 移行のテストを実行する。
- `backend/README.md` と `backend/API.md` の説明を、API が DB から読み、JSON を起動時に同期する内容へ更新する。これらのファイルには現在の未コミット変更があるため、それを保持して編集する。

## 完了条件

サーバーを既存 DB で起動しても取引データは変わらず、軌跡用テーブルには JSON と一致する行が保存される。`GET /api/trajectory/{date}` の外部契約は維持され、同期失敗時には軌跡行の部分更新が起きない。軌跡ページと mock API の動作は現在のままである。
