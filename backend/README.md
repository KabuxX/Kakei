# Kakei ローカルサーバー

Python 3.14 系で、リポジトリのルートから次を実行してください。`backend/.python-version` に使用する系列を指定し、起動時にも Python 3.14 以上であることを確認します。FastAPI CLI と Uvicorn の対応版は `backend/requirements.txt` に固定しています。

```sh
python3.14 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/fastapi run backend/server.py --host 127.0.0.1 --port 8765
```

以前の Python 3.9 で作った `backend/.venv` が残っている場合は、その仮想環境を作り直してください。`backend/.venv/bin/python --version` で 3.14 系になっていることを確認できます。

`http://localhost:8765/` を開いてください。FastAPI が画面とAPIを同じアドレスから配信します。既に8765番ポートで旧サーバーが動いている場合は、先に停止してください。

画面はReact製で、ビルド済みの `front/dist/` をFastAPIが配信します。サーバー起動と既存機能にはNode.jsは不要です。AgentのGeolonia座標検索を使う場合は、下記のNode.js依存を導入してください。`front/dist/` はGitに含めています。画面のソースを変更したときだけ、リポジトリのルートから次を実行して、更新された `front/dist/` もコミットしてください。

フロントを開発するときは、[mock 環境と API 環境](../front/README.md) を選んで起動できます。

```sh
cd front
npm ci
npm run build
```

フロントの単体テストは `cd front && npm test` で実行できます。ブラウザテストは一時DBを指定して上記のFastAPIコマンドを起動した状態で `cd front && npm run test:e2e` を実行してください。ブラウザテストは取引を追加・削除するため、普段使いのDBでは実行しないでください。

取引は既定で `backend/data/kakei.sqlite3` に保存します。別の保存先を使う場合は `KAKEI_DB_PATH=/path/to/kakei.sqlite3 backend/.venv/bin/fastapi run backend/server.py --host 127.0.0.1 --port 8765` を実行してください。DBはGitに含めません。

画面から取引の追加・削除、サンプル削除、月別の表示、検索、CSV保存ができます。APIは `GET /api/status`、`POST /api/initialize`、`GET /api/transactions`、`GET /api/transactions/{id}`、`POST /api/transactions`、`DELETE /api/transactions/{id}`、`DELETE /api/samples`、`GET /api/trajectory/{date}`、`POST`・`PUT`・`DELETE /api/trajectory` を提供します。追加する取引のIDはサーバーが発行します。

取引サンプルは重複整理済み37件、軌跡サンプルは9月19〜30日の12日分です。

各エンドポイントの入出力、入力条件、エラーは [API ドキュメント](API.md) を参照してください。

最初のサーバー生成時に、軌跡テーブルが空なら `front/src/data/september-timeline.json` を検証し、地点・日・イベント・区間・経由地点を SQLite に投入します。既存軌跡があれば維持します。以後は SQLite が正本で、JSON を変更して再起動しても保存済み軌跡を上書きしません。初回投入に失敗した場合は起動を止め、軌跡テーブルの更新をロールバックします。取引テーブルには影響しません。

`GET /api/trajectory/2026-09-29` は SQLite から指定日の時系列を返します。返却形式は `{ "places": { ... }, "days": [{ "date": "2026-09-29", "events": [ ... ], "legs": [ ... ] }] }` で、`places` にはその日の訪問地点と経由地点だけを含めます。`POST`・`PUT`・`DELETE /api/trajectory` は日、訪問イベント、移動区間、地点を操作し、再起動後も保存します。未完成の日も保存できます。いずれも取引 DB の初期化は不要です。軌跡画面は日付一覧と指定日の API を読み、保存済みの変更を表示します。mock 環境は独立した固定サンプルを返します。

新しいDBでは、画面が同じ `http://localhost:8765/` のブラウザ保存キー `kakei-transactions-v1` を一度だけ取り込みます。キーがなければサンプル取引を入れます。空配列が保存されていれば空の家計として始めます。取り込み元の `localStorage` は削除しませんが、その後の追加・削除はSQLiteだけに反映されます。

DBを削除して初期化し直すと、ブラウザに残る古いスナップショットが再び取り込み候補になります。取引を復旧するときはDBファイルのバックアップを優先してください。ローカル専用で、外部公開や複数利用者向けではありません。

## 既存DBの旧サンプルを一度だけ置換する

旧サンプル16件が入った既存DBを、整理済みの取引37件と軌跡12日分へ更新する場合は、サーバーを停止し、リポジトリのルートから次を実行してください。

```sh
backend/.venv/bin/python backend/replace_samples.py \
  --db backend/data/kakei.sqlite3 \
  --backup backend/data/kakei-before-september-dedup.sqlite3
```

スクリプトはリポジトリ内の `front/src/data/old-samples.json`、`september-transactions.json`、`september-timeline.json` を読み、取引・品目・重複・軌跡の同日参照を検証します。`--db` は既存ファイル、`--backup` はまだ存在しないファイル名を指定してください。入力検証後、SQLite のバックアップ API で更新前のDB全体を保存してから、1つのトランザクションで置換します。利用者が登録した `sample-` 以外の取引と初期化状態は維持します。旧JSONは変更しません。DBとバックアップはGitに含めません。

正常終了時は `{"deleted": 16, "inserted": 37, "days": 12}` を出力します。既に整理済みの37件と全項目が一致するDBでは取引を維持して軌跡だけを同期し、`{"deleted": 0, "inserted": 0, "days": 12}` を出力します。再実行にも別のバックアップ名が必要です。軌跡を API で編集済みの場合は上書きを防ぐため、このコマンドは停止します。サンプルの編集・削除・追加によって旧JSONにも新JSONにも一致しない場合や、同期・書き込みが失敗した場合も処理を止め、DB更新をロールバックします。更新前のバックアップは残ります。JSON検証や既存バックアップの確認で止まった場合はDBを更新しません。置換後はサーバーを起動してください。

通信やDBの読み込みに失敗したときは、画面の再試行ボタンから再取得できます。追加・削除後の再取得だけが失敗した場合、その操作はサーバーに保存済みです。画面の「表示を再読み込み」を押し、同じ操作を繰り返さないでください。

バックエンドのテストには `backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt` を追加実行し、`backend/.venv/bin/python -m unittest discover -s backend/tests -v` を使います。

## 実装の配置

`server.py` と `replace_samples.py` は互換性を保つ入口です。実装は次の5つのパッケージに分けています。

- `api/`: HTTPルート、応答、アクセス制限、静的配信。
- `services/`: 取引・軌跡・サンプルJSONの検証とサンプル置換の調停。
- `db/`: SQLiteスキーマ、保存・読取、バックアップと原子的なサンプル置換。
- `cli/`: サンプル置換の引数処理、終了コード、JSON結果出力。
- `config/`: Python実行環境の検査と、作業ディレクトリに依存しない既定パス。

上記のサーバー起動・サンプル置換コマンドは引き続き利用できます。テストでは実DBを避けるため、`KAKEI_DB_PATH=/private/tmp/kakei-backend-layout-tests.sqlite3 backend/.venv/bin/python -m unittest discover -s backend/tests -v` を使ってください。

## Agent Chat

### Geolonia の住所対応座標

Node.js 22以上を用意し、リポジトリルートで次を実行します。公式 `@geolonia/normalize-japanese-addresses` 3.1.3 と依存は専用lockで固定しています。

```sh
npm ci --prefix backend/geolonia
npm test --prefix backend/geolonia
```

日本の根拠住所がある場合、AgentはGeolonia japanese-addresses-v2を先に照合します。住所が不明ならWebで店舗と住所を確認してからGeoloniaを試します。郵便番号・全半角・丁目/番/号・建物名・根拠のある行政区分を、番地を変えずに最大6種類試します。住所認識と座標の粒度が両方8の場合だけ候補にし、町丁目代表点などは補助情報としてWebで詳細位置を探します。

Geoloniaは合計30秒、同時worker2個、Web用に残り35秒を留保し、検索145秒・turn180秒の共通期限を延長しません。通信は固定公式HTTPSホストに限定し、Range/公開IP/取得サイズを検証します。1応答8 MiB・検索合計32 MiB、同じ取得対象は初回と最大2回の一時障害再送までです。公開npm版に再送処理がないため、専用取得処理が上限を管理します。

Nodeや依存がない場合、起動失敗・通信障害・時間切れの場合は理由を履歴に残してWebへ進みます。アプリやWeb検索を無効にはしません。APIキーの追加は不要です。通常の地図表示は引き続きMapboxです。

候補・保存後の軌跡には「住所に対応する座標」、照合住所、Geoloniaの出典、[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)と加工表示を残します。住居表示・地番の座標は店舗の入口や訪問当時の所在地の確認を保証しません。地図確認と変更案承認を経て保存してください。

### モデル設定と変更案

リポジトリルートの `.env` またはサーバー環境に `OPENAI_API_KEY` と `KAKEI_AGENT_MODEL`（利用可能な OpenAI の画像入力対応モデル名）を設定して起動します。`server.py` は起動時にルートの `.env` を読み込みます。既に export した環境変数が優先されます。キーを `VITE_` 接頭辞の環境変数に入れないでください。未設定でも既存機能と承認済みデータは利用できます。LangChain 1.4.3 / langchain-openai 1.6.7 を使用します。

1ターンは180秒・8ツール呼び出しまで。外部 LangSmith tracing は各ターンで無効にしています。会話の直近20件と必要な公開SQLの結果をモデルに送ります。取引・軌跡は変更案の承認時だけ保存されます。変更案は24時間で期限切れになります。同じ送信IDや承認IDの再送は保存済み結果を返します。

agentには「指定日の軌跡を削除」「この訪問を削除」「この移動区間を削除」と依頼できます。削除案で対象日・訪問・区間への影響を確認してから承認します。訪問削除では接続区間も削除し、取引と共有地点は維持します。残った訪問間の区間は自動生成しません。

レシート原本は SQLite の BLOB に保存します。画像/PDFと読み取り依頼を OpenAI に送信しますが、原本を LangSmith に送信する設定は使用しません。画像/PDF入力と構造化出力を扱えるモデルを `KAKEI_AGENT_MODEL` に指定してください。対応通貨は日本円です。暗号化PDF、複数画像の一括添付には対応しません。

未知の店舗は OpenAI Responses API の Web検索で住所・出典・公開マップを幅広く調べ、取得済みページの本文、構造化geo、店舗ピンのリンクから座標を検証します。Mapbox Geocoding、Geoapify等の地理検索APIは使用しません。公開サイトが取得を拒否したり座標を掲載していない場合は、検証済みの同一建物、明記された直線距離と8方位、小さな地区から位置を推定します。基準も不明なら位置未確認として残します。

検索設定は `OPENAI_API_KEY` と既存の `KAKEI_AGENT_MODEL` のみ。任意の `KAKEI_AGENT_SEARCH_MODEL` を指定できます。`MAPBOX_GEOCODING_ACCESS_TOKEN` は新規検索に不要です。地図描画用の公開Mapboxトークンは引き続き使用します。旧Mapbox地点・提案・履歴は読める状態を維持します。

検索予算はturn内で共有し、Web最大6要求（各35秒、内蔵ツール最大3回）、抽出最大6要求（各15秒）、公開ページ最大16 HTTP要求（各5秒・同時3）です。検索は145秒かつturn終了15秒前まで。リダイレクトもHTTP要求へ数え、最大3回。公開HTTPSのみ、内部IP・認証付きURL・地理検索API・内部RPCは拒否し、本文は512KiBまで。外部ページへキーやCookieを送信しません。会話リースは190秒です。

店舗の掲載座標と推定位置はいずれも住所・出典・地図を確認して選択します。推定は保存後も推定として表示し、基準地点と誤差範囲が未確認であることを保持します。100mを超える掲載値の食い違いは比較対象として示します。地図の表示中心は店舗ピンと区別します。検索先へ支払額やレシート原本を送信しません。

### 取引先住所

任意の店舗住所を取引に保存します。起動時に `merchant_address` 列を既存SQLiteへ追加し、旧取引の値はnullです。レシートの `merchant_address` とagentの `merchantAddress` を変更案で確認できます。`search_place` の `address` は根拠付き条件としてWeb検索・候補照合・履歴再利用に適用されます。取引住所を変更しても共有地点の記録は変更せず、対応不明の訪問を要確認とします。詳細は `API.md` を参照。
