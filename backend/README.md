# Kakei ローカルサーバー

Python 3.14 系で、リポジトリのルートから次を実行してください。`backend/.python-version` に使用する系列を指定し、起動時にも Python 3.14 以上であることを確認します。FastAPI CLI と Uvicorn の対応版は `backend/requirements.txt` に固定しています。

```sh
python3.14 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/fastapi run backend/server.py --host 127.0.0.1 --port 8765
```

以前の Python 3.9 で作った `backend/.venv` が残っている場合は、その仮想環境を作り直してください。`backend/.venv/bin/python --version` で 3.14 系になっていることを確認できます。

`http://localhost:8765/` を開いてください。FastAPI が画面とAPIを同じアドレスから配信します。既に8765番ポートで旧サーバーが動いている場合は、先に停止してください。

画面はReact製で、ビルド済みの `front/dist/` をFastAPIが配信します。通常の起動にNode.jsは不要です。`front/dist/` はGitに含めています。画面のソースを変更したときだけ、リポジトリのルートから次を実行して、更新された `front/dist/` もコミットしてください。

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

`GET /api/trajectory/2026-09-29` は SQLite から指定日の時系列を返します。返却形式は `{ "places": { ... }, "days": [{ "date": "2026-09-29", "events": [ ... ], "legs": [ ... ] }] }` で、`places` にはその日の訪問地点と経由地点だけを含めます。`POST`・`PUT`・`DELETE /api/trajectory` は日、訪問イベント、移動区間、地点を操作し、再起動後も保存します。未完成の日も保存できます。いずれも取引 DB の初期化は不要です。API の操作結果は、固定 JSON を読む現在の軌跡画面と mock API には反映されません。

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
