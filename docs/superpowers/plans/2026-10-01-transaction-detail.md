# 取引詳細ページの実装計画

> **実装を担当するエージェントへ:** 必須の補助スキルは `superpowers:subagent-driven-development`（推奨）または `superpowers:executing-plans`。各タスクの手順はチェックボックス（`- [ ]`）で管理する。

**目標:** ダッシュボードから一件の取引を開き、記録済みの5項目を確認し、確認後に削除できるようにする。

**構成:** 既存の静的アプリと `localStorage` の保存形式を維持する。小さなブラウザ対応の補助ファイルで詳細URLと安全な削除を扱う。`front/app.js` はハッシュに応じて、DOMに残したダッシュボードと詳細画面を切り替え、一覧へ戻るときに表示状態を復元する。

**技術:** HTML、CSS、ブラウザのJavaScript、`localStorage`、Node.js標準の `node:test`。アプリやテスト用のパッケージは追加しない。

**設計書:** `docs/superpowers/specs/2026-10-01-transaction-detail-design.md`

## 共通条件

- 詳細はアプリ内画面とする。見た目は `DESIGN.md`、残りのUX指針は `design-system/household-budget-app/MASTER.md` に従う。
- 表示するのは `title`、`amount`、`date`、`type`、`category` の5項目だけとし、保存項目や移行処理を増やさない。
- 詳細URLは `#transaction/<encodeURIComponent(id)>` とし、既存のダッシュボード内アンカーを維持する。
- ダッシュボードをDOMに残し、表示月・検索語・種別フィルターを保つ。一覧から戻るときはスクロール位置とフォーカスも復元する。
- `localStorage` への書き込みに失敗した場合、取引データと詳細画面を変更しない。
- 見えるフォーカス、キーボード操作、スマートフォンでの読みやすさ、既存のアプリナビゲーションを維持する。

## 重点確認項目

- `/`、`#`、空白、日本語を含むIDがURLを経由して元に戻ること（タスク1のテスト）。
- 不正なパーセントエスケープを含むハッシュでもアプリが止まらず、「取引が見つかりません」を表示すること（タスク1のテスト、タスク2のブラウザ確認）。
- HTMLタグのような文字列を含む取引名を文字として表示し、HTMLとして実行しないこと（タスク2のブラウザ確認）。
- 長い取引名や大きな金額でも、幅375pxの画面に横スクロールを生じさせないこと（タスク2のブラウザ確認）。
- 容量不足やアクセス制限で保存に失敗しても、元の配列が変わらないこと（タスク1のテスト、タスク3のブラウザ確認）。

---

### タスク1: URLと削除処理の補助関数

**ファイル:**
- 新規: `front/transaction-detail.js`
- 新規: `tests/transaction-detail.test.cjs`

**インターフェース:**
- `globalThis` に `KakeiDetail.detailHref(id: string): string` と `KakeiDetail.detailIdFromHash(hash: string): string | null` を公開する。NodeのテストにはCommonJSでも公開する。
- `KakeiDetail.removePersistedTransaction(items: object[], id: string, storage: Storage, key: string): object[]` を公開する。候補配列を保存してから返し、保存に失敗したら例外を投げる。引数の `items` は変更しない。

- [ ] **手順1: 失敗する `node:test` を書く。** 特殊文字を含むIDのURL往復、詳細以外と不正なハッシュ、削除の保存成功、`setItem` が例外を投げても元の配列が変わらないことを検証する。
- [ ] **手順2: `node --test tests/transaction-detail.test.cjs` を実行する。** 補助ファイルが未作成のため失敗することを確認する。
- [ ] **手順3: `front/transaction-detail.js` に3関数を実装する。** 同じオブジェクトをブラウザとCommonJSに公開し、依存パッケージは使わない。
- [ ] **手順4: `node --test tests/transaction-detail.test.cjs` を実行する。** 全件成功することを確認する。
- [ ] **手順5: 補助ファイルとテストだけをコミットする。** メッセージは `feat: add transaction detail URL and storage helpers`。

### タスク2: 詳細表示と画面遷移

**ファイル:**
- 変更: `front/index.html`
- 変更: `front/app.js`
- 変更: `front/styles.css`
- 新規: `docs/verification/2026-10-01-transaction-detail-checks.md`

**インターフェース:**
- タスク1の `KakeiDetail.detailHref` と `KakeiDetail.detailIdFromHash` を使用する。`transaction-detail.js` は `app.js` より先に読み込む。
- `app.js` に `renderRoute(): void` を設ける。`#dashboard-view` と `#detail-view` を切り替え、該当取引または未発見状態を描画する。

- [ ] **手順1: `docs/verification/2026-10-01-transaction-detail-checks.md` にブラウザ確認項目と期待結果を書く。** 一覧のリンク、詳細URLの直接表示と再読み込み、不正なハッシュ、ブラウザの戻る操作、表示月・検索語・種別・スクロール位置の保持、フォーカス復元、HTMLタグのような取引名、幅375pxでの長い文字列を対象とする。
- [ ] **手順2: `front/index.html` に意味の分かる詳細画面のマークアップとスクリプトの読み込み順を追加する。** 名前付きの戻るリンク、フォーカス可能な見出し、符号付き金額と収支種別、取引名、ラベル付きの日付とカテゴリ、サンプル表示、削除操作、未発見状態を含める。ダッシュボードはDOMに残す。
- [ ] **手順3: `front/app.js` に画面遷移を実装する。** 取引名のリンク、`hashchange` と初回表示、ユーザー入力の `textContent` 表示、一覧からのスクロール位置とフォーカスの保存、直接表示時の `#transactions` への戻り先、ページタイトルとナビゲーション状態の更新を行う。詳細以外のハッシュは既存のアンカーとして動かす。
- [ ] **手順4: `front/styles.css` に詳細画面と幅ごとのスタイルを追加する。** 既存トークンを使い、非表示の画面をレイアウトから除外し、操作領域を44px以上にし、長い文字列を折り返し、固定の下部ナビゲーションが内容を隠さないようにする。
- [ ] **手順5: 手順1の項目をデスクトップと幅375pxのブラウザで確認し、結果を同じ確認書へ記録する。** 不具合があれば直し、画面の3ファイルと確認書を `feat: show transaction details with back navigation` でコミットする。

### タスク3: 確認付き削除と別タブの変更

**ファイル:**
- 変更: `front/app.js`
- 変更: `docs/verification/2026-10-01-transaction-detail-checks.md`
- 必要な追加ケースが見つかった場合のみ変更: `tests/transaction-detail.test.cjs`

**インターフェース:**
- タスク1の `KakeiDetail.removePersistedTransaction` とタスク2の `renderRoute` を使用する。
- 既存の `transactions` 配列は保存に成功した後だけ変更する。

- [ ] **手順1: 確認書に削除時の期待結果を追記する。** 削除のキャンセル、削除成功と集計の再計算、保存時に例外を発生させた場合、詳細を開いたまま別タブで削除した場合を対象とする。
- [ ] **手順2: 削除操作を詳細画面へ移す。** `front/app.js` の一覧行から削除ボタンを外し、確認には取引名を示す。保存に成功してから `transactions` を差し替え、一覧へ戻す。
- [ ] **手順3: `kakei-transactions-v1` の `storage` イベントを処理する。** 有効な配列を `isValidTransaction` で絞り、キーが削除されたら空配列とする。現在の画面を再描画し、対象が消えた詳細は未発見状態にする。
- [ ] **手順4: `node --test tests/transaction-detail.test.cjs` と手順1のブラウザ確認を実行し、結果を確認書に記録する。** キャンセルと保存失敗では詳細とデータが保たれることを確認し、`front/app.js`、確認書、変更したテストを `feat: safely delete transaction from detail` でコミットする。

### タスク4: 最終確認

**ファイル:** 追加変更は想定しない。

**インターフェース:** 追加なし。

- [ ] **手順1: `node --test tests/transaction-detail.test.cjs` と `git diff --check` を実行する。** 両方の成功を確認する。
- [ ] **手順2: ダッシュボードでナビゲーション直後に見える内容を確認する。** デスクトップと幅375pxで、選択月と収支状況、または操作がすぐ見えることを `AGENTS.md` に従って確認する。
- [ ] **手順3: 詳細画面をデスクトップと幅375pxで確認する。** キーボードだけの操作と動きを減らす設定でも、情報の順序、フォーカス、戻り方、横スクロールの有無を確認する。
- [ ] **手順4: 確認した結果とブラウザ表示の制約があれば報告する。** 実施していない確認を成功したとは書かない。
