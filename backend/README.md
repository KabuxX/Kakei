# Kakei ローカルサーバー

リポジトリのルートで `python3 backend/server.py` を実行し、`http://localhost:8765/` を開いてください。Python 3.9 以上の標準ライブラリだけを使います。画面とAPIは同じアドレスから配信されます。

取引は既定で `backend/data/kakei.sqlite3` に保存します。別の保存先を使う場合は `python3 backend/server.py --db /path/to/kakei.sqlite3` を実行してください。DBはGitに含めません。

画面から取引の追加・削除、サンプル削除、月別の表示、検索、CSV保存ができます。APIは `GET /api/status`、`POST /api/initialize`、`GET /api/transactions`、`GET /api/transactions/{id}`、`POST /api/transactions`、`DELETE /api/transactions/{id}`、`DELETE /api/samples` を提供します。追加する取引のIDはサーバーが発行します。

新しいDBでは、画面が同じ `http://localhost:8765/` のブラウザ保存キー `kakei-transactions-v1` を一度だけ取り込みます。キーがなければサンプル取引を入れます。空配列が保存されていれば空の家計として始めます。取り込み元の `localStorage` は削除しませんが、その後の追加・削除はSQLiteだけに反映されます。

DBを削除して初期化し直すと、ブラウザに残る古いスナップショットが再び取り込み候補になります。取引を復旧するときはDBファイルのバックアップを優先してください。ローカル専用で、外部公開や複数利用者向けではありません。

通信やDBの読み込みに失敗したときは、画面の再試行ボタンから再取得できます。追加・削除後の再取得だけが失敗した場合、その操作はサーバーに保存済みです。画面の「表示を再読み込み」を押し、同じ操作を繰り返さないでください。
