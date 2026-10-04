# Category Budget Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 概要画面から毎月共通のカテゴリ別予算を保存し、その合計・残額・使用率を表示する。

**Architecture:** SQLiteに6カテゴリの予算を保存し、GET/PUT APIを提供する。フロントの予算用フックが読み込みと保存を管理し、純粋な計算関数と編集ダイアログをAppから接続する。取引の取得と予算の取得は独立させる。

**Tech Stack:** Python / FastAPI / SQLite / unittest、React 19 / Vite / Vitest / Testing Library、既存のCSSとネイティブdialog。新しい依存関係は追加しない。

**Spec:** [カテゴリ別予算の設定](../specs/2026-10-04-category-budget-settings-design.md)

## Global Constraints

- 「予算は毎月共通。」変更は過去の月の表示にも適用する。
- 「各カテゴリの金額は0〜999,999,999円の整数とする。」APIは文字列・booleanを受理しない。
- 初期値：食費60,000円、住まい90,000円、日用品25,000円、交通25,000円、娯楽30,000円、その他20,000円。合計250,000円。
- 「月全体の予算は6カテゴリの合計で、独立した金額として保存しない。」
- 「6カテゴリの更新は単一トランザクション。」既存設定を移行時に上書きしない。
- 「取引や軌跡のテーブル・データは変更しない。」予算APIは取引初期化前にも利用できる。
- 「保存中は二重送信と編集・閉じる操作を無効にし、保存中と表示する。」
- 「取得失敗を固定の初期値で隠さず、予算カードに再試行できるエラーを表示する。」
- 「操作領域は44px以上を確保する。」DESIGN.mdの見た目と既存のカード順序を維持する。
- デスクトップと電話幅の最初の表示で、選択月と収支を確認する。
- 保存操作を含む検証は「隔離した一時DB」を使う。
- 月別予算・カテゴリ管理・Agentによる予算変更・専用設定ページは対象外。

## Review Focus

- 読み込みの古い応答が保存結果を上書きしないこと。Task 3の遅延応答テストで固定する。
- サーバーが200で欠落カテゴリや無効な金額を返した場合、正しい予算として採用しないこと。Task 3のAPI応答テストで固定する。
- 最初のカテゴリのDB更新後に失敗しても全カテゴリが元のままであること。Task 1のSQLite triggerによるロールバックテストで固定する。
- 全カテゴリ0円・支出ありでも表示とARIAにNaN/Infinityが入らないこと。Task 3と4で固定する。
- ダイアログをキャンセルして再度開くと保存済みの値に戻り、通信エラーの再試行では入力が残ること。Task 4で固定する。

## Files and Responsibilities

- `backend/services/budget_validation.py`：初期値、カテゴリ集合、API入力の検証。
- `backend/db/budget_store.py`：予算テーブルの作成・不足分の初期値・接続内の読み書き。
- `backend/db/schema.py` / `backend/db/store.py`：スキーマとStore公開メソッドの接続。
- `backend/api/budget.py` / `backend/api/app.py`：GET/PUT登録と既存アクセス制御との接続。
- `front/src/lib/budget.js`：カテゴリ順序、金額検証、合計、0円を含む進捗計算。
- `front/src/lib/budget-api.js`：既存requestを使った予算APIと応答検証。
- `front/src/useBudget.js`：予算取得・保存・状態管理。
- `front/src/components/budget/BudgetDialog.jsx`：6カテゴリの入力と保存・キャンセル。
- `front/src/lib/dashboard.js` / `front/src/pages/Dashboard.jsx` / `front/src/app/App.jsx`：計算と表示、ダイアログの接続。
- `front/styles.css`：予算設定のボタン・入力・状態の最小限のスタイル。
- `front/dev/mock-api.mjs`：mockモードでも予算を編集できるAPI。
- 下記のテストファイル、`front/README.md`、`front/dist/`：検証と利用方法、本番成果物。

---

### Task 1: 予算の検証とSQLite保存

**Files:** Create `backend/services/budget_validation.py`, `backend/db/budget_store.py`, `backend/tests/test_budget_store.py`; Modify `backend/db/schema.py`, `backend/db/store.py`.

**Interfaces:**
- `DEFAULT_BUDGETS: dict[str, int]` は上記6カテゴリの初期値。
- `normalize_budget(payload: object) -> dict[str, int]` はwire形式 `{"categories": {...}}` を検証し、カテゴリ別金額を返す。失敗は既存 `ValidationError(field, message)`。フィールド名は `categories` または `categories.食費` 等。
- `ensure_budget_schema(connection) -> None`, `read_budget(connection) -> dict[str, int]`, `write_budget(connection, categories: dict[str, int]) -> None`。connectionのcommit/rollbackは呼び出し元が管理する。
- `Store.get_budget() -> dict[str, int]`, `Store.update_budget(payload: object) -> dict[str, int]`。後者は検証して全カテゴリを更新し、同じ接続で保存結果を読む。

- [ ] **1. 検証・永続化の失敗テストを書く。** `test_default_and_persistence` で `sum(Store(db).get_budget().values()) == 250000`、全カテゴリ0を保存後 `Store(db).get_budget() == zeros` をassertする。`test_validation_rejects_invalid_input` は欠落・未知カテゴリ・null・配列と、食費の `True, "100", -1, 0.5, 1000000000` を拒否し、0と999999999を許可する。
- [ ] **2. 対象テストを実行し未実装で失敗することを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_budget_store.py -v`。欠落モジュールまたはStoreメソッドの失敗を確認する。
- [ ] **3. 宣言したインターフェースを実装する。** テーブルは `category_budgets(category TEXT PRIMARY KEY, amount INTEGER NOT NULL CHECK(typeof(amount) = 'integer' AND amount BETWEEN 0 AND 999999999))`。カテゴリは固定6個。`_ensure_domain_schema` の早期returnより前にテーブルを作り、`INSERT OR IGNORE` で初期値を追加する。Storeの既存 `_connection()` で一括更新する。取引の初期化を要求しない。
- [ ] **4. 移行・ロールバックのテストを書く。** `test_schema_preserves_saved_values` は既存DBで食費を12345にして再度スキーマを通し12345を保持する。`test_failed_update_rolls_back_all_categories` は住まいへの更新を `RAISE(ABORT, 'fixture')` するSQLite triggerを追加し、更新例外後に全カテゴリが更新前と一致することをassertする。取引・軌跡データも更新前後で一致させる。
- [ ] **5. 対象テストがすべて通ることを確認する。** Step 2のコマンドを再実行する。
- [ ] **6. コミットする。** 上記5ファイルを追加し `git commit -m "feat: persist shared category budgets"`。

### Task 2: 予算HTTP API

**Files:** Create `backend/api/budget.py`, `backend/tests/test_budget_api.py`; Modify `backend/api/app.py`.

**Interfaces:**
- Consumes Task 1のStoreメソッド。
- `register_budget(app: FastAPI, store: Store) -> None`。
- GET/PUT `/api/budget` のレスポンスは `{"categories": dict[str, int]}`。PUTは同じ形のJSONを受ける。GET/PUT成功は200、検証失敗400、DB失敗500、Origin違反403、その他のメソッド405。

- [ ] **1. 未初期化DBを使ったAPI失敗テストを書く。** 独立したTemporaryDirectory・create_app・TestClientを用い、`test_get_put_before_transaction_initialization` はHost `localhost:8765` でGETが200/初期値、正しいOriginを付けたPUTが200/保存値、その後のGETが一致することをassertする。取引のinitializedはfalseのまま。
- [ ] **2. テストを実行して未登録ルートで失敗することを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_budget_api.py -v`。
- [ ] **3. ルートを実装する。** GETはStoreを読む。PUTは既存 `read_json(request, 16 * 1024)` とStoreの検証を使う。appの初期化制御の例外に `/api/budget` を追加し、unknown_apiの既知パスにも追加する。同一OriginとHostの既存制御を維持する。
- [ ] **4. エラー契約テストを書く。** `test_rejected_put_does_not_change_budget` は食費-1を400・`error.field == "categories.食費"` としGETで未変更をassertする。`test_access_and_database_errors` はOrigin欠落/異なるOrigin/不正Hostが403、Storeのsqlite3.Errorが500。壊れたJSON400、サイズ超過413、POST405も確認する。
- [ ] **5. 対象と既存サーバーテストを実行する。** Step 2と `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_server.py -v`。失敗0を確認する。
- [ ] **6. コミットする。** 上記3ファイルを追加し `git commit -m "feat: expose category budget API"`。

### Task 3: フロントの予算取得と安全な計算

**Files:** Create `front/src/lib/budget.js`, `front/src/lib/budget-api.js`, `front/src/useBudget.js`, `front/src/lib/budget.test.js`, `front/src/lib/budget-api.test.js`, `front/src/tests/useBudget.test.jsx`.

**Interfaces:**
- `CATEGORY_NAMES: string[]` は食費・住まい・日用品・交通・娯楽・その他の順序。
- `parseBudgetFields(fields: Record<string, string>) -> {categories: Record<string, number> | null, errors: Record<string, string>}`。前後の空白は除去し、数字だけの整数文字列を受理する。空欄や上限超過なら対象エラーを返す。
- `isValidBudget(categories: unknown) -> boolean` は6カテゴリ全部と範囲内整数を確認する。
- `sumBudget(categories: Record<string, number>) -> number`。
- `budgetUsage(spent: number, limit: number) -> {percent: number, over: boolean, excess: number}`。percentはバー用の0〜100で有限。0/0は0、支出あり/0は100。overはspent > limit、excessはMath.max(0, spent-limit)。
- `loadBudget(fetchImpl = fetch) -> Promise<Record<string, number>>`, `updateBudget(categories, fetchImpl = fetch) -> Promise<Record<string, number>>`。既存 `request` / `ApiError` を使い、成功レスポンスも検証する。
- `useBudget() -> {categories: Record<string, number> | null, status: 'loading' | 'ready' | 'loadError', error: Error | null, busy: boolean, load: () => Promise<boolean>, save: (categories) => Promise<Record<string, number>>}`。saveは失敗時reject、成功時状態更新。保存済み値を成功前に変更しない。

- [ ] **1. 計算・応答・フックの失敗テストを書く。** `budgetUsage(0,0)` は `{percent:0,over:false,excess:0}`、`budgetUsage(300,0)` は `{percent:100,over:true,excess:300}`。全カテゴリ999999999の合計5999999994を確認する。入力文字列の空欄/負数/小数/上限超過を拒否し、6カテゴリの有効な入力を数値に変換する。APIが欠落カテゴリや文字列を返した場合はrejectする。
- [ ] **2. 対象テストを実行して失敗を確認する。** frontから `npm test -- src/lib/budget.test.js src/lib/budget-api.test.js src/tests/useBudget.test.jsx`。
- [ ] **3. 宣言した計算・API・フックを実装する。** 保存二重実行はrefで防ぎ、loadのリクエスト世代を記録する。保存開始時に以前のloadを無効化し、busy中のloadを開始させない。アンマウント後の更新を抑制する。APIの成功応答だけを保存結果として採用する。
- [ ] **4. 失敗と応答順序のテストを追加する。** `test_retry_load` は取得失敗でcategories null、load再試行でready。`test_save_rejection_preserves_loaded_budget` は失敗で既存値維持・readyに戻る。`test_late_load_does_not_overwrite_save` はready後に遅延loadを開始し、GETが未完了の間に保存を成功させ、古いGETを完了後も保存値とreadyを保持する。二重saveでPUTが1回だけとなることも確認する。
- [ ] **5. 対象テストがすべて通ることを確認する。** Step 2を再実行する。
- [ ] **6. コミットする。** 上記6ファイルを追加し `git commit -m "feat: load budgets and calculate budget usage"`。

### Task 4: 予算編集と概要画面への接続

**Files:** Create `front/src/components/budget/BudgetDialog.jsx`, `front/src/tests/BudgetDialog.test.jsx`, `front/src/tests/App.budget.test.jsx`; Modify `front/src/lib/dashboard.js`, `front/src/lib/dashboard.test.js`, `front/src/pages/Dashboard.jsx`, `front/src/app/App.jsx`, `front/styles.css`, `front/src/tests/Dashboard.test.jsx`, `front/src/tests/App.route.test.jsx`, `front/src/tests/App.edit.test.jsx`, `front/src/tests/App.mutations.test.jsx`。

**Interfaces:**
- Consumes Task 3の予算・計算関数とuseBudget。
- `BudgetDialog({open, categories, busy, onClose, onSubmit})`。onSubmitはカテゴリ別金額を受けPromiseを返す。成功時onClose、失敗時入力維持とエラー表示。フォーム内の入力/送信エラーはダイアログが管理する。
- Dashboardへ `budgetStatus`, `budgetError`, `onRetryBudget`, `onEditBudget`, `budgetBusy` を渡す。予算金額はmodelから読み、固定値を参照しない。
- Appは開閉状態とトリガーを保持し、onSubmitで `budget.save(categories)`、成功時toast「予算を保存しました」を表示する。
- `dashboardForMonth(records, month, budgets = null)`。予算未取得なら `totalBudget` / `remaining` / 各 `categoryTotals[].budget` はnull、支出・収入・週別・カテゴリ別支出は通常どおり計算する。固定 `totalBudget` exportを廃止し、カテゴリ名/色は維持する。

- [ ] **1. ダイアログとモデルの失敗テストを書く。** 6つのラベルから入力を取得し、食費60000→70000で合計260000、保存でonSubmitに6カテゴリ全部を渡すことをassertする。空欄/負数/小数/上限超過は対象欄のエラーとaria-invalidを表示し送信しない。保存エラー→入力70000維持→再送信成功をassertする。dashboard.test.jsで予算300000・支出1200なら残額298800、budgetsなしなら収支維持・remaining nullをassertする。
- [ ] **2. 対象テストを実行して失敗を確認する。** frontから `npm test -- src/tests/BudgetDialog.test.jsx src/tests/App.budget.test.jsx src/tests/Dashboard.test.jsx src/lib/dashboard.test.js`。
- [ ] **3. ダイアログを実装する。** 既存TransactionDialogを参照し、showModal/close、Escape、閉じるボタン、最初の入力へのフォーカスを実装する。初回/openし直しで保存済み値を文字列に変換する。必須ラベル・円の単位・inputMode numeric・関連エラー・合計・保存・キャンセルを用意する。説明は「毎月共通の予算です。変更はすべての月に適用されます。」。保存中は編集/閉じる/キャンセル/Escape/送信を無効にし、追加確認を出さない。
- [ ] **4. Dashboard/Appに接続する。** 月の予算の見出し付近へ文字付き「予算を設定」を置き、budgetStatus readyだけで開ける。取引状態に予算取得を結び付けない。読み込み中は予算金額と割合を未取得として表示し、取得失敗には再試行を用意する。各進捗はbudgetUsageを使い、超過額と有限のARIA値を表示する。既存の概要カード順序を維持し、閉じた際にトリガーへフォーカスを戻す。専用CSSは既存の変数・ダイアログ/フォームスタイルに合わせる。
- [ ] **5. 接続・アクセシビリティのテストを追加する。** `App.budget.test.jsx` で予算だけ取得失敗でも選択月/収支/取引が表示され、再試行で予算が戻ること、食費更新後の合計/残額/カテゴリ進捗が一致することをassertする。`BudgetDialog.test.jsx` はキャンセル後の再openで保存値に戻る、busy中に閉じない、フォーカスが最初の欄へ移ることを確認する。Dashboardは全0・支出ありでNaN/InfinityをDOMに含まないことをassertする。既存AppテストのmockにuseBudgetを追加し、未取得予算が取引のテストを阻害しないようにする。
- [ ] **6. 対象と既存フロントテストを実行する。** frontから `npm test`。全ファイル失敗0を確認する。
- [ ] **7. コミットする。** 上記ファイルの変更を追加し `git commit -m "feat: edit category budgets from overview"`。

### Task 5: 開発環境・本番ビルド・実画面の検証

**Files:** Modify `front/dev/mock-api.mjs`, `front/src/dev-environments.test.js`, `front/README.md`, `front/dist/`; Create `backend/tests/budget_browser_server.py`。

**Interfaces:**
- mock APIのGET/PUT `/api/budget` はTask 2と同じwire形式。mock予算はサーバー実行中に保持し、再起動時は初期値に戻る（既存mockモードと同じ）。
- `budget_browser_server.py` は `create_app(temp_db, front_dist, port=8768)` をuvicornで起動する隔離ブラウザfixture。一時DBにサンプル取引を初期化し、実DB/.envを使用しない。

- [ ] **1. mockモードの失敗テストを書く。** `dev-environments.test.js` にGETの合計250000、PUTで食費70000、GETで70000、負数PUT400と設定未変更、mockサーバー再作成時に60000へ戻るテストを追加する。
- [ ] **2. 失敗を確認する。** frontから `npm test -- src/dev-environments.test.js`。
- [ ] **3. mock/APIとfixture、利用説明を実装する。** mockはTask 3の検証に合わせる。fixtureはTemporaryDirectoryを保持して実データへ接続しない。READMEへ予算設定の入口・毎月共通・本番はSQLite保存/mockは一時保存を記載する。
- [ ] **4. 全体検証とビルドを実行する。** frontで `npm test` と `npm run build`、repo rootで `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py'` と `git diff --check`。すべてexit 0、失敗0を確認する。
- [ ] **5. 一時fixtureを起動する。** `backend/.venv/bin/python backend/tests/budget_browser_server.py`。ブラウザ操作はcua_replを使い、`http://localhost:8768/#overview` を開く。
- [ ] **6. デスクトップと電話幅を確認する。** 1440×900と375×812で、ナビゲーション直後に選択月と収支が見えること、ダイアログに横スクロールがないこと、44px以上の操作、フォーカスとEscape/キャンセルを確認する。食費70000で合計260000に保存し、再読み込み後に値を維持することを確認する。DB再接続後の維持はTask 1のStore再作成テストで検証する。全カテゴリ0円に保存し、残額・超過額・進捗の表示を確認する。
- [ ] **7. 最終変更をレビューし修正を検証する。** spec/planのチェックリストと差分を照合し、選択された実行方法のスキルに従ってレビューする。修正があれば関連テストとビルドを再実行する。レビュー結果と実画面検証の制約があれば報告する。
- [ ] **8. 成果物をコミットする。** 上記ファイルと本番distを追加し `git commit -m "test: verify category budget settings and build frontend"`。作業ツリーとブランチの状態を報告する。統合や実アプリ再起動は、セッションで与えられた指示と実行スキルの完了手順に従う。
