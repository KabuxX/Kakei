# Kakei Local Backend Implementation Plan

> この計画は最初の標準ライブラリ版を対象とした履歴です。HTTPサーバーは後のFastAPIへのリファクタリングで置き換えました。現行の依存関係と起動手順は `backend/README.md` を参照してください。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PythonのローカルAPIに取引を保存し、既存画面を接続して `http://localhost:8765/` のブラウザ保存データを初回に引き継ぐ。

**Architecture:** Python標準のHTTPサーバーが `front/` と `/api/` を同じオリジンで配信し、SQLiteが取引と初期化状態を保持する。画面はAPIから取引を読み、既存の集計・検索・CSV処理を使う。取引の更新はAPI成功後の再取得で反映する。

**Tech Stack:** Python 3.9 標準ライブラリ（`http.server`、`sqlite3`、`unittest`）、ブラウザJavaScript、Node.js標準の `node:test`。追加パッケージなし。

**Spec:** `docs/superpowers/specs/2026-10-01-local-backend-design.md`

## Global Constraints

- バックエンドの製品コード、DB初期化、バックエンドのテストはすべて `backend/`。起動は `python3 backend/server.py`、既定のDBは `backend/data/kakei.sqlite3`、必要なら `--db PATH`。
- サーバーは既定で `127.0.0.1:8765` にバインドし、利用者が開くURLは既存の保存領域と一致する `http://localhost:8765/`。ログイン、外部公開、追加パッケージなし。
- 新規取引の金額は1〜999,999,999円の整数。支出カテゴリは食費、住まい、日用品、交通、娯楽、その他。収入カテゴリは収入。支払方法は `cash`、`credit_card`、`e_money`、`bank_account`。
- 新規の内容・店名・品目名は空白を除いて1〜60文字。新規取引の本文は64KiB、初回取り込みは8MiBまで。初回取り込みは旧形式の支出と空配列を許容し、一度だけ全件を原子的に保存する。
- `localStorage` のキーは `kakei-transactions-v1`。初回取り込み後も旧データを移行元のスナップショットとして残し、以後の正しい保存先はSQLite。
- 画面はアプリ内画面。`design-system/household-budget-app/pages/dashboard.md` を情報順序、`DESIGN.md` を見た目、`MASTER.md` と ui-ux-pro-max を一般UXに使用する。デスクトップとスマートフォンで最初の表示領域に選択月と収支または読み込み・再試行を見せる。

## File Map

- `backend/validation.py`: 新規取引と初回取り込みの純粋な検証・正規化。HTTPとDBに依存しない。
- `backend/store.py`: SQLiteスキーマ、初期化状態、取引のCRUD、原子的な一括操作。`validation.py` を使う。
- `backend/server.py`: HTTPルーティング、JSON入出力、同一オリジン制約、`front/` の静的配信、CLI起動。`store.py` を使う。
- `backend/.gitignore`、`backend/README.md`: DBのGit除外と起動・移行・復旧手順。
- `backend/tests/test_validation.py`、`test_store.py`、`test_server.py`: Python標準 `unittest` と一時DBによる検証。
- `front/api.js`、`tests/api.test.cjs`: 画面から呼ぶAPIクライアントと初回取り込みの判定を、ブラウザとNodeの両方で使用・検証。
- `front/app.js`、`front/index.html`、`front/styles.css`: 読み込み状態、APIへの接続、保存失敗と再試行。既存の描画・入力計算・詳細URLを保つ。

## Review Focus

- `localStorage` が壊れたJSONまたは配列以外の場合、初期化を止めて旧内容を残し、サンプルで置き換えない（Task 4 のテスト）。
- 取引が0件で初期化済みのDBを再起動してもサンプルが復活しない（Task 2 のテスト）。
- 2つの初期化要求が競合しても一方だけ成功し、取引が混在しない（Task 2 のテスト）。
- 別サイトの `Origin` からの書き込みと `front/` 外へのパス参照を拒否する（Task 3 のテスト）。
- 書き込み成功後の一覧再取得だけが失敗しても、再送信による取引の重複や削除の再実行を促さず、表示の再試行を案内する（Task 5 のブラウザ確認）。

---

### Task 1: 取引データの検証

**Files:** Create `backend/validation.py` and `backend/tests/test_validation.py`.

**Interfaces:** `ValidationError(ValueError)` は `field: Optional[str]`、`message: str` を持つ。`normalize_transaction(payload: object, *, import_mode: bool = False) -> dict[str, object]` は既存画面と同じキー名で正規化した取引を返す。新規ではIDを受け取らず、取り込みでは非空IDを必須とする。HTTPとDBはこの関数を再検証なしで使用する。

- [ ] **Step 1: 失敗するテストを書く。** `test_new_income_and_itemized_expense` で収入と品目合計300円の支出が正規化されること、`test_invalid_new_fields` で空白名・不正日付・0円・小数・未知カテゴリ・未知支払方法・品目合計不一致を拒否すること、`test_legacy_import` で旧支出の欠けた詳細と不正な品目だけを未登録にすることを検証する。
- [ ] **Step 2: 赤を確認する。** `python3 -m unittest discover -s backend/tests -p 'test_validation.py' -v` → `normalize_transaction` がないため FAIL。
- [ ] **Step 3: `backend/validation.py` を実装する。** `datetime.date.fromisoformat` で実在日付を検証し、Pythonの `bool` を整数金額として受け入れない。新規のタイトル・店名・品目名は1〜60文字、金額は1〜999,999,999円。取り込みでは旧形式の任意のカテゴリ文字列を保ち、無効な任意詳細だけ `None` または空配列にする。
- [ ] **Step 4: 緑を確認する。** 同じ `unittest` コマンド → 全件 PASS。
- [ ] **Step 5: コミットする。** `git add backend/validation.py backend/tests/test_validation.py`、`git commit -m "feat: validate backend transactions"`。

### Task 2: SQLiteの保存と初期化

**Files:** Create `backend/store.py` and `backend/tests/test_store.py`; create `backend/.gitignore` containing `data/`.

**Interfaces:** `Store(db_path: pathlib.Path)`。`is_initialized() -> bool`、`initialize(records: list[object]) -> int`、`list_transactions() -> list[dict[str, object]]`、`get_transaction(id: str) -> Optional[dict[str, object]]`、`create_transaction(draft: object) -> dict[str, object]`、`delete_transaction(id: str) -> bool`、`delete_samples() -> int`。`AlreadyInitialized` と `NotInitialized` は別の例外。`create_transaction` は `uuid.uuid4()` でIDを生成する。

- [ ] **Step 1: 失敗するテストを書く。** `test_initialize_empty_survives_reopen`、`test_initialize_is_atomic_for_invalid_or_duplicate_ids`、`test_competing_initialize_only_one_wins`、`test_create_list_get_delete_and_samples` を一時DBで検証する。競合テストでは異なる配列を2スレッドから送り、片方だけ成功した後の一覧が一方の配列と完全一致することを確認する。
- [ ] **Step 2: 赤を確認する。** `python3 -m unittest discover -s backend/tests -p 'test_store.py' -v` → `Store` がないため FAIL。
- [ ] **Step 3: `backend/store.py` を実装する。** `transactions` と `meta` テーブルを作り、各操作に短いSQLite接続を使う。初期化は `BEGIN IMMEDIATE` 内でフラグ確認、全件検証・挿入、フラグ設定を行う。品目はJSON文字列で保存し、公開時に既存画面のキー名へ戻す。追加・削除・サンプル削除もトランザクション化する。
- [ ] **Step 4: 緑を確認する。** 同じ `unittest` コマンド → 全件 PASS。DBファイルがGit対象外であることを `git check-ignore backend/data/kakei.sqlite3` で確認する。
- [ ] **Step 5: コミットする。** `git add backend/store.py backend/tests/test_store.py backend/.gitignore`、`git commit -m "feat: persist local transactions in sqlite"`。

### Task 3: HTTP APIと静的配信

**Files:** Create `backend/server.py`、`backend/tests/test_server.py`、`backend/README.md`.

**Interfaces:** `create_server(db_path: pathlib.Path, front_dir: pathlib.Path, *, port: int = 8765) -> http.server.ThreadingHTTPServer`。`main(argv: Optional[list[str]] = None) -> int` は `--db PATH` を受け、既定で `127.0.0.1:8765` を起動する。`GET /api/status`、`POST /api/initialize`、`GET /api/transactions`、`GET /api/transactions/{id}`、`POST /api/transactions`、`DELETE /api/transactions/{id}`、`DELETE /api/samples` を設計書の応答形式で提供する。

- [ ] **Step 1: 失敗するテストを書く。** 一時DBとポート0のHTTPサーバーで `test_api_lifecycle_and_codes`、`test_invalid_json_and_body_limits`、`test_cross_origin_write_and_static_escape_rejected`、`test_encoded_id_and_missing_delete`、`test_database_error_response` を検証する。成功時は `201/200/204`、重複初期化は `409`、不正入力は `400`、過大本文は `413`、未知IDは `404`、対象外メソッドは `405`、DB障害は `500` とJSONエラー形式を確認する。
- [ ] **Step 2: 赤を確認する。** `python3 -m unittest discover -s backend/tests -p 'test_server.py' -v` → `create_server` がないため FAIL。
- [ ] **Step 3: `backend/server.py` を実装する。** siblingの `store.py` を読み込める直接起動形式にする。`Content-Type: application/json` と本文長を検査し、`Store` の例外をHTTP状態へ変換する。書き込みはリクエストの `Host` と一致する localhost/127.0.0.1 の `Origin` だけを許し、CORSを追加しない。静的配信は `front/` 内のファイルだけに限定し、ディレクトリ一覧とパス脱出を拒否する。`backend/README.md` に起動URL、DBの位置、旧データの取り込み条件、DBを消した場合の旧スナップショット再取り込みを記す。
- [ ] **Step 4: 緑を確認する。** `python3 -m unittest discover -s backend/tests -v` → 全件 PASS。`python3 backend/server.py --help` → `--db` の使い方を表示。
- [ ] **Step 5: コミットする。** `git add backend/server.py backend/tests/test_server.py backend/README.md`、`git commit -m "feat: serve Kakei and local API"`。

### Task 4: 画面の初回読み込みと取り込み

**Files:** Create `front/api.js`、`tests/api.test.cjs`; modify `front/index.html:10-13,55-68,130`、`front/app.js:12-45,112-118,429-431`、必要な範囲の `front/styles.css`.

**Interfaces:** `KakeiApi.loadInitialTransactions({ fetchImpl, storage, sampleFactory }) -> Promise<object[]>` は状態確認、必要なら初期化、一覧取得を行う。`KakeiApi.listTransactions(fetchImpl) -> Promise<object[]>` と `KakeiApi.ApiError` を公開し、ブラウザの `globalThis.KakeiApi` と CommonJS の両方で利用できる。`storage` は `getItem`、`sampleFactory` は既存の `sampleTransactions()`。初期化 `409` は競合とみなして一覧を取得する。

- [ ] **Step 1: 失敗するテストを書く。** `test_loads_existing_server_without_storage_access`、`test_imports_saved_array_including_empty`、`test_seeds_samples_only_when_key_is_absent`、`test_corrupt_storage_stops_without_post`、`test_initialize_conflict_fetches_winner` を `tests/api.test.cjs` に書く。`localStorage` 読み取りが例外を投げる場合もPOSTしないことを確認する。
- [ ] **Step 2: 赤を確認する。** `node --test tests/api.test.cjs` → `loadInitialTransactions` がないため FAIL。
- [ ] **Step 3: APIクライアントと初回ロードを実装する。** `front/index.html` で `api.js` を `app.js` より前に読み込む。`app.js` の同期 `loadTransactions()` と末尾の即時 `render()` を、API取得後に描画する流れへ替える。最初の収支カードに表示月・読み込み文・再試行ボタンを置き、未取得の0円を確定値として見せない。初回失敗はサンプルで代替せず、同じ領域で再試行できるようにする。ui-ux-pro-max の関連指針を確認し、既存の視覚トークンに合わせる。
- [ ] **Step 4: 緑を確認する。** `node --test tests/api.test.cjs tests/transaction-data.test.cjs tests/transaction-detail.test.cjs tests/sample-data.test.cjs` → 全件 PASS。ブラウザで空DBと保存済み `localStorage` の初回表示を確認し、最初の領域に表示月と読み込み・収支・再試行があることを確認する。
- [ ] **Step 5: コミットする。** `git add front/api.js front/app.js front/index.html front/styles.css tests/api.test.cjs`、`git commit -m "feat: load and import transactions from local API"`。

### Task 5: 画面の更新操作と総合確認

**Files:** Modify `front/api.js`、`front/app.js:339-428`、`front/index.html` と `front/styles.css` の保存状態表示、`tests/api.test.cjs`、`backend/README.md`.

**Interfaces:** `KakeiApi.addTransaction(draft, fetchImpl) -> Promise<object>`、`KakeiApi.removeTransaction(id, fetchImpl) -> Promise<void>`、`KakeiApi.removeSamples(fetchImpl) -> Promise<number>`。各成功後に `listTransactions` を呼び、画面内配列を一度だけ置き換えて `render()` と必要な `renderRoute()` を実行する。既存の月・検索語・種別フィルター・詳細URLは保持する。

- [ ] **Step 1: 失敗するテストを書く。** `test_create_delete_samples_use_expected_methods_and_paths` でHTTPメソッド・URL・本文・レスポンスを確認し、`test_failed_write_rejects_without_mutating_input` でAPIエラーを呼び出し元へ伝えることを確認する。
- [ ] **Step 2: 赤を確認する。** `node --test tests/api.test.cjs` → 更新用APIがないため FAIL。
- [ ] **Step 3: 画面の更新操作を実装する。** `app.js` の `persistAddedTransaction`、`removePersistedTransaction`、`removePersistedSamples` 呼び出しをAPIに替える。送信中の二重操作を防ぎ、書き込み要求自体の失敗では入力または詳細を保持する。書き込み成功後に一覧再取得だけが失敗した場合は保存済みと明示して再送信を防ぎ、表示の再試行を案内する。`storage` イベント依存を外し、タブが再び表示されたとき一覧を取得する。CSVは現在取得済みの選択月データから生成する。保存先の表示文をサーバー保存に合わせる。
- [ ] **Step 4: 緑を確認する。** `node --test tests/*.test.cjs` と `python3 -m unittest discover -s backend/tests -v` → 全件 PASS。ブラウザで追加・再読み込み・再起動・削除・サンプル削除・検索・CSV・直接詳細URL・別タブ復帰・通信失敗時の再試行を確認する。書き込み成功後だけ一覧再取得が失敗した場合に再送信されないことも確認する。デスクトップとスマートフォン幅でナビゲーション直後の選択月と収支または再試行を確認し、プレビュー不可なら描画構造とその限界を記録する。`git diff --check` → PASS。
- [ ] **Step 5: コミットする。** `git add front/api.js front/app.js front/index.html front/styles.css tests/api.test.cjs backend/README.md`、`git commit -m "feat: connect transaction actions to local API"`。

## Final Gate

計画の全タスク後に、DBをテスト用の一時パスで起動し、既存ブラウザ保存からの取り込み、保存後の再起動、UIの最初の表示領域を最終確認する。ユーザーの実データを含む `backend/data/kakei.sqlite3` は検証で初期化・削除しない。結果と未確認事項を報告する。
