# Kakei ローカルサーバー

リポジトリのルートで `python3 backend/server.py` を実行し、`http://localhost:8765/` を開いてください。Python 3.9 以上の標準ライブラリだけを使います。画面とAPIは同じアドレスから配信されます。

取引は既定で `backend/data/kakei.sqlite3` に保存します。別の保存先を使う場合は `python3 backend/server.py --db /path/to/kakei.sqlite3` を実行してください。DBはGitに含めません。

新しいDBでは、画面が同じ `http://localhost:8765/` のブラウザ保存キー `kakei-transactions-v1` を一度だけ取り込みます。キーがなければサンプル取引を入れます。空配列が保存されていれば空の家計として始めます。取り込み元の `localStorage` は削除しませんが、その後の追加・削除はSQLiteだけに反映されます。

DBを削除して初期化し直すと、ブラウザに残る古いスナップショットが再び取り込み候補になります。取引を復旧するときはDBファイルのバックアップを優先してください。ローカル専用で、外部公開や複数利用者向けではありません。
