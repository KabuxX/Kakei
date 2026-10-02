# Backend の API・サービス・DB 分割設計

## 目的と範囲

`backend/` 直下に並ぶ HTTP、入力検証、サンプル置換、SQLite の実装を、責務に応じて `api/`、`services/`、`db/` に整理する。それ以外の実装責務は `cli/` と `config/` に分ける。HTTP 契約、画面配信、起動時の軌跡同期、保存済みデータの形式と内容は維持する。利用者の既存 SQLite ファイルはこのリファクタリングでは更新しない。

既存の `fastapi run backend/server.py --host 127.0.0.1 --port 8765` と `python backend/replace_samples.py --db ... --backup ...` を維持する。`backend/server.py` は `app` と `create_app` を公開し、`backend/replace_samples.py` は `replace_samples` と CLI を公開する薄い入口として残す。README、API 文書、依存定義、`data/`、`tests/` も `backend/` 直下に残す。

## 配置と責務

| 配置 | 責務 |
| --- | --- |
| `backend/api/app.py` | `create_app`、ローカルアクセス制限、例外から HTTP エラーへの変換、ルート登録、`front/dist` の静的配信 |
| `backend/api/http.py` | JSON 本文のサイズ・形式検査、JSON 応答とエラー応答の共通処理 |
| `backend/api/transactions.py` | 初期化、状態、取引の一覧・取得・追加・削除、サンプル削除の HTTP ルート |
| `backend/api/trajectory.py` | 日付指定軌跡の HTTP ルートと日付形式の検査 |
| `backend/services/validation.py` | 取引の検証・正規化と `ValidationError` |
| `backend/services/trajectory_validation.py` | 軌跡 JSON の読込、厳密な形・参照検証 |
| `backend/services/sample_replacement.py` | 旧・新サンプル JSON の検証、重複・同日参照の検査、置換作業の調停 |
| `backend/db/schema.py` | SQLite スキーマと既存スキーマ移行 |
| `backend/db/store.py` | 接続・トランザクション、取引と軌跡の保存・取得を提供する `Store` |
| `backend/db/trajectory_store.py` | 軌跡テーブルの一括同期と日付別の読取 |
| `backend/db/sample_replacement.py` | 既存 DB の照合、SQLite バックアップ、サンプル取引と軌跡の原子的置換 |
| `backend/cli/replace_samples.py` | 置換コマンドの引数、終了コード、結果出力 |
| `backend/config/runtime.py` | 起動時の Python バージョン検査 |
| `backend/config/paths.py` | 既定 DB、フロントの配信先、サンプル JSON の絶対パス |

各実装ディレクトリには `__init__.py` を置く。`backend/` 自体には `__init__.py` を追加しない。現行のファイル指定による FastAPI CLI と Python の直接実行は `backend/` を import 探索パスに置くため、内部 import は `api.*`、`services.*`、`db.*`、`cli.*`、`config.*` に統一する。旧内部モジュールのルート直下ファイルは削除し、互換用ファイルは上記の2つの入口だけに限定する。既存の `backend/tests/` は新しい所有モジュールを直接検証するよう import を更新し、入口の互換性も別途検証する。

## 処理の流れと依存関係

`server.py` は `config.runtime` の検査と `config.paths` の既定パスを使って `api.app.create_app` を呼ぶ。アプリ生成時は軌跡 JSON を `services.trajectory_validation` で読み、`db.store.Store` を通して SQLite に同期する。各 HTTP ルートは `Store` を使い、既存と同じ JSON、ステータス、エラーコードを返す。共通の本文検査とエラー応答は `api.http` に集める。未定義 API の 404/405 判定と静的配信の登録順も維持する。

取引と軌跡の検証モジュールは DB に依存しない純粋な処理に保つ。`Store` はこれらの検証関数を利用するが、検証モジュールから `db/` を import しない。ルートの置換入口は `cli.replace_samples` に引数処理を委ねる。サンプル置換サービスは入力を完全に検証してから `db.sample_replacement` を呼ぶ。DB 側は既存 DB とサンプルの一致を確認し、バックアップを作り、現在の単一トランザクションによる更新・ロールバックを維持する。`api/` を `services/` または `db/` から import しない。

`front/src/data`、`front/dist`、既定の `backend/data/kakei.sqlite3` を指すパスは `config.paths` に集め、作業ディレクトリに依存させない。実 DB に対して置換 CLI を再実行しない。

## 互換性と失敗時の扱い

- API の全パス、HTTP メソッド、本文制限、同一オリジン制限、初期化前の扱い、404/405 とエラー本文を維持する。
- `create_app(db_path, front_dir, *, port=8765, timeline_path=...)` と2つのルート直下入口を維持する。
- 既存 DB のスキーマ、移行、初期化状態、取引、品目、軌跡同期の意味を変えない。
- 起動時の無効な軌跡 JSON は従来どおり起動を止め、同期をロールバックする。サンプル置換の入力・バックアップ・DB 失敗も現行の停止とロールバックを維持する。
- アーカイブ済みの旧設計・計画文書は履歴として残し、現在の実行手順を記す `backend/README.md` の構成説明だけを更新する。

## 検証

1. 新しい所有モジュールを直接対象にする既存のバックエンドテストを、一時 `KAKEI_DB_PATH` で全件実行する。実 `backend/data/kakei.sqlite3` には触れない。
2. 一時 DB と一時バックアップで `backend/replace_samples.py` を実行し、旧サンプルから新サンプルへの件数、再実行、ロールバック、利用者取引の保存を検証する。
3. `backend/server.py` の `app` と `create_app` をテストし、静的配信、API 契約、起動時同期、無効入力の応答を確認する。文書どおりの FastAPI CLI 起動も一時 DB でスモーク確認する。
4. import 循環がなく、README のコマンドと参照先が実ファイルに一致することを確認する。フロントの未コミット UI 変更には触れない。
