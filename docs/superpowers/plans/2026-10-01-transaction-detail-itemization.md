# 取引詳細の品目管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支出に店名・支払方法・任意の品目を登録し、詳細と CSV で確認できるようにする。

**Architecture:** 既存の `kakei-transactions-v1` のレコードに任意の詳細項目を足し、旧レコードを維持する。純粋な検証・読取・保存・CSV 化を `transaction-data.js` に置き、`app.js` はフォームと詳細画面の操作を担当する。

**Tech Stack:** HTML、CSS、ブラウザ JavaScript、`localStorage`、Node.js 標準の `node:test`。

**Spec:** `docs/superpowers/specs/2026-10-01-transaction-detail-itemization-design.md`

## Global Constraints

- 保存キーは `kakei-transactions-v1`、金額は1円から999,999,999円までの整数。
- 支払方法は `cash`、`credit_card`、`e_money`、`bank_account` の4値。表示名は「現金」「クレジットカード」「電子マネー」「銀行口座」。
- 新規支出の店名・取引先と支払方法は必須、品目は任意。収入の入力・詳細は現状のまま。
- 品目がある支出の取引金額は品目金額の合計。旧形式の取引は保持し、壊れた追加項目だけ未登録として扱う。
- 詳細は閲覧と削除のみ。画面の視覚スタイルは `DESIGN.md` を優先する。

## Review Focus

- 旧レコードに新項目がない場合も取引が残り、詳細では「未登録」と表示する（Task 1、3）。
- 品目配列が不正、または合計が取引金額と異なる場合は品目だけを未登録にする（Task 1）。
- 空白の品目名、小数・0円、合計の上限超過を登録時に拒否する（Task 1、2）。
- `localStorage` の読み書き失敗時は取引配列と入力内容を失わない（Task 1、2）。
- 数式記号で始まる店名、引用符やカンマを含む品目名を CSV で安全に保持する（Task 4）。

---

### Task 1: 取引詳細データの検証と安全な保存

**Files:** Create `front/transaction-data.js`, `tests/transaction-data.test.cjs`; modify `front/index.html:10-12`（スクリプト読込）。

**Interfaces:** `KakeiTransactionData.readExpenseDetails(record)` → `{ merchant: string|null, paymentMethod: string|null, items: {name:string,amount:number}[] }`。`parseExpenseDraft({merchant,paymentMethod,itemRows,manualAmount})` → `{merchant,paymentMethod,items,amount}`、不正時は `field`（`merchant`、`paymentMethod`、`itemRows`、`amount` のいずれか）と `message` を持つ `ValidationError`。`persistAddedTransaction(items,newRecord,storage,key,isValid)` → 保存後の配列。`PAYMENT_METHOD_LABELS` と各関数をブラウザの `globalThis.KakeiTransactionData` と CommonJS の両方へ公開する。

- [ ] **Step 1: 失敗するテストを書く。** `readExpenseDetails` が旧レコードと不正な追加項目を落とさず、品目合計の不一致だけ無効にすることを検証する。`parseExpenseDraft` が品目なしの手入力、2品目の合算、空白名・小数・0円・上限超過・必須項目欠落を検証する。`persistAddedTransaction` が別タブの追加を保持し、読み書き失敗時に元配列を変えないことを検証する。主な期待値は次の通り。

  ```js
  assert.deepEqual(readExpenseDetails({ type: 'expense', amount: 300 }), { merchant: null, paymentMethod: null, items: [] });
  assert.deepEqual(readExpenseDetails({ type: 'expense', amount: 300, items: [{ name: 'パン', amount: 200 }] }).items, []);
  assert.equal(parseExpenseDraft({ merchant: ' 店 ', paymentMethod: 'cash', itemRows: [{ name: 'パン', amount: '200' }, { name: '牛乳', amount: '100' }], manualAmount: '' }).amount, 300);
  assert.equal(parseExpenseDraft({ merchant: '店', paymentMethod: 'cash', itemRows: [], manualAmount: '500' }).amount, 500);
  assert.throws(() => parseExpenseDraft({ merchant: '店', paymentMethod: 'cash', itemRows: [{ name: ' ', amount: '100' }], manualAmount: '' }), { field: 'itemRows' });
  ```
- [ ] **Step 2: 赤を確認する。** `node --test tests/transaction-data.test.cjs` → 未実装 API により FAIL。
- [ ] **Step 3: 最小実装を書く。** 上記3 API と4種類の支払方法ラベルを `transaction-data.js` に実装する。保存直前に保存済み配列を読み直し、新レコードを追加して書き込む。保存データが不正なら上書きせず例外にする。`index.html` で `app.js` より前に読み込む。
- [ ] **Step 4: 緑を確認する。** `node --test tests/transaction-data.test.cjs tests/transaction-detail.test.cjs` → 全件 PASS。
- [ ] **Step 5: コミットする。** `git add front/transaction-data.js front/index.html tests/transaction-data.test.cjs`、`git commit -m "feat: validate and persist itemized expenses"`。

### Task 2: 支出の追加フォーム

**Files:** Modify `front/index.html:96`, `front/app.js:208-253`, `front/styles.css:15-51`。

**Interfaces:** Task 1 の `parseExpenseDraft` と `persistAddedTransaction` を使用。フォームの要素 ID は `expense-fields`、`merchant-input`、`payment-method-input`、`item-rows`、`add-item`、`amount-input`、`form-error`。欄ごとのエラー表示は `merchant-error`、`payment-method-error`、`items-error`、`amount-error` を使い、入力と `aria-describedby` で結ぶ。品目行は `data-item-name`、`data-item-amount` の入力と削除ボタンを持つ。

- [ ] **Step 1: 赤を確認する。** ブラウザで支出追加を開き、店名・支払方法・品目追加操作がまだないことを確認する。
- [ ] **Step 2: フォームを実装する。** 支出だけに必須の店名と未選択が初期値の支払方法を表示し、品目行を追加・削除できるようにする。収入へ切り替えたら支出専用欄を非表示・無効化する。品目がある間は金額を計算表示し、最後の行を消したら以前の手入力額に戻す。
- [ ] **Step 3: 保存処理を実装する。** 既存の内容・日付・カテゴリ検証を維持し、支出は Task 1 の API で検証する。フィールドエラーは該当欄に示し、保存失敗時はフォームを開いたままにする。保存成功後だけ画面内配列を更新して閉じる。
- [ ] **Step 4: 緑を確認する。** ブラウザで品目あり・なしの支出と収入を登録し、再読み込み後に金額とレコードを確認する。未完成行と上限超過は送信できず、収入への切替では支出専用の必須欄が送信を妨げないことを確認する。`node --test tests/transaction-data.test.cjs tests/transaction-detail.test.cjs` → PASS。
- [ ] **Step 5: コミットする。** `git add front/index.html front/app.js front/styles.css`、`git commit -m "feat: enter itemized expense details"`。

### Task 3: 支出詳細の表示とサンプル

**Files:** Modify `front/index.html:75-90`, `front/app.js:21-37,179-206`, `front/styles.css:34-51`。

**Interfaces:** Task 1 の `readExpenseDetails(record)` と支払方法ラベルを使用する。表示先は `detail-expense-fields`、`detail-merchant`、`detail-payment-method`、`detail-items`。

- [ ] **Step 1: 赤を確認する。** 支出の詳細に店名・支払方法・品目がまだ表示されないことを確認する。
- [ ] **Step 2: 詳細を実装する。** 支出だけにラベル付きの2項目と品目一覧を表示する。古い取引では「未登録」と「品目は登録されていません」を示す。文字列は `textContent` または `escapeHtml` で挿入し、長い品目名と金額が両方読める CSS にする。
- [ ] **Step 3: サンプルを追加する。** `sample-1` と `sample-2` に、既存の取引金額と合計が一致する品目、店名、支払方法を設定する。他のサンプルや収入は変更しない。
- [ ] **Step 4: 緑を確認する。** 品目あり、品目なし、旧レコード、収入の詳細をデスクトップと375px幅で確認する。削除と戻る操作、ダッシュボード先頭の表示月・収支も確認する。
- [ ] **Step 5: コミットする。** `git add front/index.html front/app.js front/styles.css`、`git commit -m "feat: show merchant payment and items in detail"`。

### Task 4: CSV と最終検証

**Files:** Modify `front/transaction-data.js`, `front/app.js:285-295`, `tests/transaction-data.test.cjs`。

**Interfaces:** `KakeiTransactionData.serializeTransactionsCsv(items)` → BOM 付き CSV 文字列。Task 1 の `readExpenseDetails` を使用し、既存の5列の後に「店名・取引先」「支払方法」「品目」を追加する。品目セルは JSON、追加項目のない取引は空欄。

- [ ] **Step 1: 失敗するテストを書く。** 新しいヘッダー、2品目の JSON セル、旧レコードの空欄、`=店名` の数式対策、`"` と `,` を含む品目名の往復を検証する。少なくとも `assert.ok(csv.includes('"店名・取引先","支払方法","品目"'))` と `assert.ok(csv.includes("'=店名"))` を満たし、CSV セルを復元した品目配列が元の配列と一致することを検証する。
- [ ] **Step 2: 赤を確認する。** `node --test tests/transaction-data.test.cjs` → CSV API 未実装により FAIL。
- [ ] **Step 3: CSV API とダウンロードを実装する。** 既存の CSV エスケープと数式対策をモジュールへ移し、`app.js` のダウンロード処理から呼ぶ。
- [ ] **Step 4: 緑を確認する。** `node --test tests/transaction-data.test.cjs tests/transaction-detail.test.cjs` と `git diff --check` → PASS。ブラウザで CSV と詳細 URL、別タブ更新、保存失敗時の入力保持、デスクトップ・スマートフォンの見た目を確認する。プレビュー不可ならレンダリング構造を調べて制限を報告する。
- [ ] **Step 5: コミットする。** `git add front/transaction-data.js front/app.js tests/transaction-data.test.cjs`、`git commit -m "feat: export itemized transaction details"`。
