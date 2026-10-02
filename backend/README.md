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

```sh
cd front
npm ci
npm run build
```

フロントの単体テストは `cd front && npm test` で実行できます。ブラウザテストは一時DBを指定して上記のFastAPIコマンドを起動した状態で `cd front && npm run test:e2e` を実行してください。ブラウザテストは取引を追加・削除するため、普段使いのDBでは実行しないでください。

取引は既定で `backend/data/kakei.sqlite3` に保存します。別の保存先を使う場合は `KAKEI_DB_PATH=/path/to/kakei.sqlite3 backend/.venv/bin/fastapi run backend/server.py --host 127.0.0.1 --port 8765` を実行してください。DBはGitに含めません。

画面から取引の追加・削除、サンプル削除、月別の表示、検索、CSV保存ができます。APIは `GET /api/status`、`POST /api/initialize`、`GET /api/transactions`、`GET /api/transactions/{id}`、`POST /api/transactions`、`DELETE /api/transactions/{id}`、`DELETE /api/samples`、`GET /api/trajectory/{date}` を提供します。追加する取引のIDはサーバーが発行します。

`GET /api/trajectory/2026-09-02` は固定の `front/src/data/september-timeline.json` から指定日の時系列を返します。返却形式は `{ "places": { ... }, "days": [{ "date": "2026-09-02", "events": [ ... ], "legs": [ ... ] }] }` で、`places` にはその日の訪問地点と経由地点だけを含めます。取引 DB の初期化は不要です。日付は `YYYY-MM-DD` 形式で指定し、不正な日付は 400、サンプルにない日付は 404 を返します。軌跡ページと mock API は引き続きフロントの JSON を直接使用します。

新しいDBでは、画面が同じ `http://localhost:8765/` のブラウザ保存キー `kakei-transactions-v1` を一度だけ取り込みます。キーがなければサンプル取引を入れます。空配列が保存されていれば空の家計として始めます。取り込み元の `localStorage` は削除しませんが、その後の追加・削除はSQLiteだけに反映されます。

DBを削除して初期化し直すと、ブラウザに残る古いスナップショットが再び取り込み候補になります。取引を復旧するときはDBファイルのバックアップを優先してください。ローカル専用で、外部公開や複数利用者向けではありません。

通信やDBの読み込みに失敗したときは、画面の再試行ボタンから再取得できます。追加・削除後の再取得だけが失敗した場合、その操作はサーバーに保存済みです。画面の「表示を再読み込み」を押し、同じ操作を繰り返さないでください。

バックエンドのテストには `backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt` を追加実行し、`backend/.venv/bin/python -m unittest discover -s backend/tests -v` を使います。
