# 取引日時の分単位精度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 取引の日時をフロント、API、SQLiteで分単位に揃え、日付だけだった既存値は識別可能な仮時刻へ移行する。

**Architecture:** 取引日時はタイムゾーンなしのローカル文字列 `YYYY-MM-DDTHH:mm` とし、サーバー管理の `timeEstimated` で補完値を示す。バックエンドの共通日時ヘルパーが日付だけの一括取込とDB移行で決定的な仮時刻を割り当てる。フロントはその契約を入力・表示・CSVで使い、集計と軌跡照合は日時のカレンダー日付を使う。

**Tech Stack:** Python 3, FastAPI, SQLite, React 19, Vitest, `unittest`, Playwright。新しい依存パッケージは追加しない。

**Spec:** `docs/superpowers/specs/2026-10-03-transaction-minute-precision-design.md`

## Global Constraints

- `date` はローカル日時 `YYYY-MM-DDTHH:mm` とし、秒、UTC オフセット、タイムゾーン変換を含めない。
- API の取引レコードには boolean の `timeEstimated` を含め、SQLite では `time_estimated` に保存する。作成リクエストでクライアントはこの値を指定しない。
- 新規作成 API は分単位日時を必須とし、初期取込のみ `YYYY-MM-DD` を受け付けて仮時刻を割り当てる。
- 1件の日付のみレコードは12:00にする。同日の複数件は ID 昇順で、840件以下なら08:00〜21:59、841〜1,440件なら00:00〜23:59へ均等に割り当てる。同日1,440件超はエラーとする。
- 仮時刻の取引には「時刻は仮設定」を表示し、CSVの「時刻の精度」列を「仮設定」にする。
- 見た目は `DESIGN.md`、アプリ内UXは `design-system/household-budget-app/MASTER.md` に従う。日時欄は可視ラベル付きの適切な入力型とし、スマートフォンで横スクロールを起こさない。

## Review Focus

- 不正な年月日、`24:00`、秒やオフセット付き日時は日時フィールドエラーになる（Task 1: `test_rejects_invalid_local_datetime_values`）。
- 取込内の日付だけレコードは同日で異なる安定した時刻になり、1件は12:00、1,440件超は拒否される（Task 1: `test_assigns_deterministic_distinct_estimated_minutes`, `test_rejects_more_than_1440_same_day_records`）。
- 既存スキーマと `items_json` 旧スキーマのどちらでも移行し、失敗時は元の取引・品目・初期化状態を残す（Task 2: `test_current_schema_backfills_date_only_rows`, `test_legacy_migration_backfills_datetime_and_preserves_items`, `test_migration_failure_rolls_back`）。
- ブラウザーのローカル日時が UTC 変換で別の日・時刻へずれず、推定値だけが仮設定と表示される（Task 3: `test_round_trips_local_datetime_without_timezone_shift`, `shows estimated and entered times distinctly`）。
- 分単位日時を含む取引でも月・週集計と軌跡参照はカレンダー日付で一致し、CSVは推定状態を保持する（Task 3: `exports minute date and precision`, Task 4: `groups minute transactions by calendar day`, `joins timestamped transactions to same-date events`）。

---

### Task 1: バックエンド日時の検証と仮時刻割当

**Files:**
- Create: `backend/transaction_datetime.py`
- Modify: `backend/services/validation.py`
- Create: `backend/tests/test_transaction_datetime.py`
- Modify: `backend/tests/test_validation.py`

**Interfaces:**
- Produces: `parse_transaction_datetime(value: object, *, allow_date_only: bool = False) -> tuple[str, bool]`. 返り値は `(date, time_estimated)`。分単位日時はそのまま返し、日付だけは `allow_date_only=True` の場合に限り `(date, True)` を返す。形式・実在日・時刻が不正なら `ValueError` を送出する。
- Produces: `assign_estimated_datetimes(records: list[dict]) -> list[dict]`. 入力を変更せず複製を返す。日付だけのレコードを日付ごとに ID 昇順で割り当て、`date` を分単位へ変換して `timeEstimated: true` を設定する。日時付きレコードは維持する。
- Consumes: `services.validation.normalize_transaction` は `parse_transaction_datetime` を使い、新規取引では `allow_date_only=False`、初期取込では `True` とする。初期取込レコードには `timeEstimated` を含める。

- [ ] **手順1: 日時ヘルパーと検証の失敗テストを書く。** `backend/tests/test_transaction_datetime.py` に `test_single_estimated_record_uses_noon`, `test_assigns_deterministic_distinct_estimated_minutes`, `test_rejects_more_than_1440_same_day_records` を追加する。`backend/tests/test_validation.py` には `test_accepts_minute_local_datetime_and_date_only_import` と `test_rejects_invalid_local_datetime_values` を追加し、秒・UTC オフセット・`24:00`・`2026-02-30` を拒否する。
- [ ] **手順2: 日時ヘルパーテストを実行して失敗を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_transaction_datetime.py' -v` を実行し、新規関数が未実装のため失敗することを確認する。
- [ ] **手順3: `backend/transaction_datetime.py` に2関数を実装する。** 日付文字列は固定桁の正規表現と Python の日時パーサーの両方で検証する。仮時刻は複数件の場合、各 ID 順位置 `i`（0始まり）に対して、840件以下なら `480 + floor((i + 1) * 840 / (n + 1))` 分、841〜1,440件なら `floor((i + 1) * 1440 / (n + 1))` 分を割り当てる。1件は12:00、1,440件超はエラーにする。
- [ ] **手順4: `normalize_transaction` を日時契約へ更新する。** 新規作成では分単位日時のみ受け付け、初期取込では日付だけを受け付ける。`timeEstimated` は入力値を信頼せず、検証した `date` 形式からサーバー側で設定する。
- [ ] **手順5: 日時ヘルパーと検証テストを実行する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_transaction_datetime.py' -v` と `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_validation.py' -v` を実行し、すべて成功することを確認する。
- [ ] **手順6: タスク1の変更をコミットする。** `backend/transaction_datetime.py`、検証コード、テストを `feat: add minute transaction datetime validation` でコミットする。

### Task 2: SQLite移行、取込、API契約

**Files:**
- Modify: `backend/db/schema.py`
- Modify: `backend/db/store.py`
- Modify: `backend/db/sample_replacement.py`
- Modify: `backend/services/sample_replacement.py`
- Modify: `backend/API.md`
- Modify: `backend/tests/test_schema.py`
- Modify: `backend/tests/test_store.py`
- Modify: `backend/tests/test_replace_samples.py`
- Modify: `backend/tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 の `assign_estimated_datetimes(records: list[dict]) -> list[dict]` と `normalize_transaction(...)`。
- Produces: `Store.list_transactions()`, `Store.get_transaction()` と作成レスポンスは各レコードに `date: str` と `timeEstimated: bool` を返す。SQLite 行は `date` と `time_estimated` を保存する。

- [ ] **手順1: SQLite・Store・API の失敗テストを書く。** `test_schema.py` に `test_current_schema_backfills_date_only_rows` と `test_legacy_migration_backfills_datetime_and_preserves_items` を追加し、既存 `test_migration_failure_rolls_back` に新列と補完日時の rollback 検証を足す。`test_store.py` に日付のみ初期取込と create/list/get の往復を追加する。`test_replace_samples.py` と `test_server.py` にサンプル置換、API応答の推定フラグ、`test_create_rejects_date_only_and_returns_time_estimated` を追加する。新規作成 fixture は分単位日時へ更新し、日付のみ fixture は初期取込・移行テストに限る。
- [ ] **手順2: 変更対象のバックエンドテストを実行し、未実装のため失敗することを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_schema.py' -v` を実行する。
- [ ] **手順3: `backend/db/schema.py` の新規・既存スキーマを更新する。** 新規 `transactions` に `time_estimated INTEGER NOT NULL DEFAULT 0 CHECK (time_estimated IN (0, 1))` を作る。既存の現行スキーマでは列を追加してから、同じ SQLite トランザクション内で日付のみ行を補完する。`items_json` 旧スキーマの再作成経路でも、取引日時・推定フラグ・品目を同一トランザクションで移す。
- [ ] **手順4: `backend/db/store.py` とサンプル保存を更新する。** `_insert` と `_record` に推定フラグを通す。`Store.initialize` は全行を正規化してから一括割当を行い、`create_transaction` は新規日時と `false` を保存する。`db/sample_replacement.py` の期待値・実値比較に `time_estimated` を含める。
- [ ] **手順5: API ドキュメントとサンプル取込を更新する。** `services/sample_replacement.py` は日付だけの旧 fixture を同じ規則で正規化する。`backend/API.md` と `test_server.py` で作成日時の形式、初期取込の互換、応答中の `timeEstimated` を明記・確認する。
- [ ] **手順6: バックエンド全テストを実行する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -v` が成功することを確認する。
- [ ] **手順7: タスク2の変更をコミットする。** バックエンド実装・API文書・テストを `feat: persist estimated transaction datetimes` でコミットする。

### Task 3: フロントの日時入力・詳細・CSV

**Files:**
- Create: `front/src/lib/transaction-datetime.js`
- Create: `front/src/lib/transaction-datetime.test.js`
- Modify: `front/src/TransactionDialog.jsx`
- Modify: `front/src/TransactionDialog.test.jsx`
- Modify: `front/src/TransactionDetail.jsx`
- Modify: `front/src/TransactionDetail.test.jsx`
- Modify: `front/src/App.jsx`
- Modify: `front/src/App.mutations.test.jsx`
- Modify: `front/src/dev-environments.test.js`
- Modify: `front/src/lib/transaction-data.js`
- Modify: `front/src/lib/contracts.test.js`

**Interfaces:**
- Produces: `dateTimeLocalValue(date: Date = new Date()) -> string` はローカル時刻の `YYYY-MM-DDTHH:mm` を返す。
- Produces: `transactionCalendarDate(value: string) -> string`、`transactionMonthKey(value: string) -> string`、`formatTransactionDate(value: string) -> string` はそれぞれ先頭10文字、先頭7文字、日本語の年月日と分単位時刻を返す。日付だけの旧 UI fixture は従来の日付だけで表示する。
- Consumes: バックエンドの `date` と `timeEstimated`。作成フォームは `date` のみ送信し、推定状態はサーバーに決めさせる。

- [ ] **手順1: フロント日時ヘルパーとコンポーネントの失敗テストを書く。** `transaction-datetime.test.js` に `test_round_trips_local_datetime_without_timezone_shift` を追加する。`TransactionDialog.test.jsx` に `sends minute-level datetime with a visible label` を追加し、`App.mutations.test.jsx` と `dev-environments.test.js` の新規作成 fixture を分単位へ更新する。`TransactionDetail.test.jsx` に `shows estimated and entered times distinctly` を追加する。`contracts.test.js` では API 作成 fixture を分単位にし、`exports minute date and precision` を追加する。
- [ ] **手順2: 日時ヘルパーテストを実行して失敗を確認する。** `cd front && npm test -- src/lib/transaction-datetime.test.js` を実行する。
- [ ] **手順3: `transaction-datetime.js` と追加フォームを実装する。** ローカル `Date` getter で初期値を作り、UTC変換を使わない。フォーム欄を可視ラベル「日付と時刻」、`type="datetime-local"`、分単位の `step` にし、厳密な日時検証後に `date` を送る。
- [ ] **手順4: `TransactionDetail.jsx` と `App.jsx` を実装する。** 詳細は日本語年月日と24時間表記の時刻を表示し、`timeEstimated` のときだけ「時刻は仮設定」を表示する。追加後の表示月は datetime-local 値の先頭7文字から選ぶ。
- [ ] **手順5: CSV出力を更新する。** `transaction-data.js` の `date` 列に分単位日時を出力し、「時刻の精度」列に「仮設定」または「入力時刻」を出力する。既存の CSV 引用・数式対策を保つ。
- [ ] **手順6: フロントの関連単体テストを実行する。** `cd front && npm test -- src/lib/transaction-datetime.test.js src/TransactionDialog.test.jsx src/TransactionDetail.test.jsx src/lib/contracts.test.js` が成功することを確認する。
- [ ] **手順7: タスク3の変更をコミットする。** フロント helper、入力、詳細、CSV、テストを `feat: show minute precision in transaction details` でコミットする。

### Task 4: 集計・軌跡の日付互換

**Files:**
- Create: `front/src/lib/dashboard.test.js`
- Modify: `front/src/lib/dashboard.js`
- Modify: `front/src/lib/trajectory-model.js`
- Modify: `front/src/lib/trajectory-model.test.js`
- Modify: `backend/services/sample_replacement.py`
- Modify: `backend/tests/test_replace_samples.py`

**Interfaces:**
- Consumes: Task 3 の `transactionCalendarDate(value: string) -> string` と `transactionMonthKey(value: string) -> string`。
- Produces: 月次・週別計算、軌跡の取引検索、サンプル取引参照検証は分単位日時を受け取り、カレンダー日付単位で判定する。

- [ ] **手順1: カレンダー日付ベースの失敗テストを書く。** `dashboard.test.js` に `groups minute transactions by calendar day` を追加し、同日の複数時刻の月合計、週分類、降順を検証する。`trajectory-model.test.js` に `joins timestamped transactions to same-date events` を追加し、`date: "2026-09-02T09:17"` を `2026-09-02` のイベント・交通費に結び、別日を拒否する。`test_replace_samples.py` に分単位日時の取引と日単位の軌跡日の照合を追加する。
- [ ] **手順2: 新しいフロントテストを実行し失敗を確認する。** `cd front && npm test -- src/lib/dashboard.test.js src/lib/trajectory-model.test.js` を実行する。
- [ ] **手順3: 月・週集計とフロント軌跡の取引照合を更新する。** 月は先頭7文字、日付表示と週分類・軌跡参照は先頭10文字を使用する。取引の並び順は分単位日時文字列の降順を保つ。
- [ ] **手順4: バックエンドのサンプル軌跡検証を日付部分へ更新する。** `services/sample_replacement.py` は日付付き取引の先頭10文字を `timeline.days[].date` と比較する。
- [ ] **手順5: フロントとサンプル置換テストを実行する。** `cd front && npm test -- src/lib/dashboard.test.js src/lib/trajectory-model.test.js` と `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_replace_samples.py' -v` が成功することを確認する。
- [ ] **手順6: タスク4の変更をコミットする。** 集計・軌跡実装とテストを `fix: compare transaction datetimes by calendar day` でコミットする。

### Task 5: 全体検証と画面確認

**Files:**
- Modify only if verification finds a defect: files owned by Tasks 1–4.

**Interfaces:**
- Consumes: Tasks 1–4 のバックエンド日時契約、フロント表示、集計、軌跡の変更。
- Produces: 全層の検証結果。未実施の確認を成功として記録しない。

- [ ] **手順1: 全バックエンド単体テストを実行する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -v` が成功することを確認する。
- [ ] **手順2: 全フロント単体テストと本番ビルドを実行する。** `cd front && npm test` と `npm run build` が成功することを確認する。
- [ ] **手順3: ブラウザで取引詳細と追加フォームを確認する。** デスクトップ幅と375px幅で、日時入力・詳細・推定表示・フォーカス・横スクロールを確認する。API応答で日付だけの取込が仮時刻とフラグを持ち、新規作成が入力日時と `false` を持つことも確認する。
- [ ] **手順4: 不具合が見つかった場合だけ修正し、所有タスクの確認を再実行する。** 変更を所有するタスクのテストと最終確認を通してから、結果をユーザーへ報告する。
