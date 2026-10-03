# Merchant Address Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 取引先住所を手入力・レシート・agentから保存し、詳細・軌跡・CSVで一貫して扱う。

**Architecture:** 支出取引に任意の住所を保存し、共有の住所照合処理から関連地点の確認状態を計算する。住所専用更新は店名と旧住所による競合検知を備える。座標未確認でも住所を記録でき、住所変更時は過去の地点データを保持して地図への誤表示を防ぐ。

**Tech Stack:** Python 3.14、FastAPI、SQLite、LangChain、OpenAI、Mapbox Geocoding v6、React、Vite、Vitest、Playwright。新しい依存ライブラリは追加しない。

**Spec:** `docs/superpowers/specs/2026-10-04-merchant-address-design.md`（利用者承認済み）。実装前に仕様と本計画を両方読む。

## Global Constraints

- 最大500文字、空文字・空白のみ・nullは未登録として扱い、数値・配列・オブジェクトは400で拒否する。上限の数え方はフロントとサーバーでUnicodeコードポイント単位に揃える。
- 既存支出の更新でmerchantAddressを省略した場合は既存住所を維持する。ただし保存住所がある取引のmerchant変更にはmerchantAddressの明示指定が必要。
- 収入には取引先住所を持たせない。収入への変更では支出専用の住所を除去する。
- 住所は郵便番号から番地・建物名までを1つの文字列で扱う。前後空白と改行コードを整え、内部の表記や建物名は保持する。
- agentの変更は既存の変更案・差分・保存承認を通す。取引の住所編集で、他の取引も使う共有地点を直接書き換えない。
- 日別軌跡APIのlocationStatusは読取専用。保存コマンドへこの派生値を保存しない。
- CSVの既存列順を保ち、末尾に「取引先住所」と「関連軌跡住所」を追加する。
- 画面はアプリ内画面。DESIGN.mdを視覚スタイルの基準とし、MASTER.mdとdashboard.mdの適用範囲を守る。
- 実API確認は画像読取1回、agentの会話2回まで。本番の取引・会話へテストデータを書かない。既存.envを変更せず、キーを出力しない。
- 実行方法は既に利用者が選んだ**Native**を維持する。計画レビュー後にexecuting-plansを使用し、実行開始時にusing-git-worktreesに従って隔離する。

## Review Focus

1. 古い未承認提案と旧クライアント: 住所欠落とnullの差だけで偽の競合を起こさず、実際に住所が追加された後の古い提案は拒否する（Task 1）。
2. 500文字境界の補助漢字・改行: UTF-16長で早く拒否せず、CRLF正規化後の同じ値を保存できる（Tasks 1, 3）。
3. レシート保存先をA→B→新規→Aへ変更: Aの入力をBへ流用せず、読取失敗で住所を消去しない（Task 4）。
4. 同じ地点を共有する複数取引: 1取引の住所変更で他の訪問のピンや共有地点を変更せず、未確認訪問を飛ばす線を作らない（Tasks 2, 6）。
5. 店名が同じで住所・番地が異なる検索: 過去候補、同一turnキャッシュ、履歴再利用でも旧住所の座標を返さない（Task 5）。

---

## ファイルの責務と作業順序

| 境界 | 新規ファイル | 既存の連携先 |
| --- | --- | --- |
| 住所値・同値比較 | `backend/services/merchant_address.py` | validation、geocoding、place_matching |
| 関連地点の読取・状態計算 | `backend/services/transaction_addresses.py` | Store、住所API、軌跡API、trajectory_context |
| HTTP契約 | `backend/api/transaction_addresses.py` | api/app.py |
| 共通入力欄 | `front/src/MerchantAddressField.jsx` | TransactionDialog、TransactionAddress、TransactionFields |
| 住所入力・API・表示 | 既存ファイルを拡張 | transaction-data.js、api.js、useTransactions、App、TransactionAddress |
| レシート・agent | 既存ファイルを拡張 | receipt.py、agent_store、runtime、検索処理、ReceiptReview |
| 表示・出力 | 既存ファイルを拡張 | trajectory-model、Trajectory、App、CSV処理、mock-api |

依存順は1→2→3→4→5→6→7。相互に関係する住所機能1件として実装し、汎用取引先マスターや汎用取引編集画面は作らない。

検証コマンドは作業ツリーのルートから実行する。Pythonは`/Users/spco/Kakei/backend/.venv/bin/python`を使い、DBは各テストの一時DB。フロントの既存依存を使う。以下のテスト例のstore/agent/client等は対象ファイルの一時DB fixtureを使う。

### Task 1: 住所の保存と既存更新・提案の互換性

**Files:**
- Create: `backend/services/merchant_address.py`, `backend/tests/test_merchant_address.py`
- Modify: `backend/services/validation.py`, `backend/db/schema.py`, `backend/db/store.py`, `backend/services/agent_changes.py`
- Test/modify: `backend/tests/test_schema.py`, `backend/tests/test_store.py`, `backend/tests/test_agent_changes.py`, `backend/tests/test_agent_store.py`

**Interfaces:**
- `normalize_merchant_address(value: object) -> str | None`: CRLF/CRをLFへ、前後空白除去、最大500コードポイント。違反はValidationError(field='merchantAddress')。
- `resolve_updated_merchant_address(old: dict, draft: dict) -> str | None`: 明示値を正規化、省略は維持。支出→収入はNone。保存住所がありmerchantを変えるのに住所省略ならValidationError。
- Storeの支出レコードは`merchantAddress: str | None`を持つ。既存Storeの公開メソッド名は維持する。

- [ ] **Step 1 — REDテストを追加。** `test_address_value_limits`で以下を検証し、`test_address_migration_preserves_records`で新規/現在/items_json旧DBの移行・再移行と各テーブルの値を比較する。
  ```python
  assert normalize_merchant_address(' \r\n東京都千代田区\r\n二番町8-8 ') == '東京都千代田区\n二番町8-8'
  assert normalize_merchant_address('𠮷' * 500) == '𠮷' * 500
  assert normalize_merchant_address('   ') is None
  # '𠮷'*501, 1, [], {} はfield='merchantAddress'のValidationError。
  ```
  `test_omitted_address_survives_put_and_agent_update`: POST→PUTで住所省略→agent更新の順で同じ住所・時刻精度・品目が残る。null/空文字の明示消去、merchant変更時の必須指定、収入変更も検証。
  `test_legacy_proposal_address_baseline`: 住所属性なしの旧提案を模したbaselineは現在住所Noneなら承認可能、現在住所が文字列なら409。住所変更前の新提案も変更後は409。
- [ ] **Step 2 — 失敗を確認。** `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*address*.py'`を上記Pythonで実行。未実装関数/未保存値が原因の失敗を確認。
- [ ] **Step 3 — 実装。** 移行の全経路でmerchant_addressを追加し、INSERT/UPDATE/_recordを対応。PUTの事前正規化で省略とnullを潰さず、prepare_changesと共通の更新規則へ渡す。旧提案とのfingerprint互換はcanonicalの状態表現でmerchantAddress=Noneを省略扱いとし、非nullは必ず含める。他の項目の競合検知は維持する。
- [ ] **Step 4 — GREEN確認。** `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests`で全件成功。住所を持つ初期取込・サンプル置換経路も往復を確認。初期取込でも非文字列と501コードポイントを拒否するテストを含める。
- [ ] **Step 5 — コミット。** `git add`でこのTaskのファイルだけを指定し、`git commit -m "feat: persist merchant addresses with compatible updates"`。

### Task 2: 住所照合・住所専用API・軌跡の確認状態

**Files:**
- Create: `backend/services/transaction_addresses.py`, `backend/api/transaction_addresses.py`, `backend/tests/test_transaction_addresses.py`
- Modify: `backend/services/merchant_address.py`, `backend/agent/geocoding.py`, `backend/db/store.py`, `backend/api/app.py`, `backend/api/trajectory.py`, `backend/agent/trajectory.py`, `backend/API.md`
- Test/modify: `backend/tests/test_agent_geocoding.py`, `backend/tests/test_agent_trajectory.py`

**Interfaces:**
- 移設: geocodingの`normalize_address(value)`と`japanese_parts(value)`をmerchant_addressへ。既存importはre-exportで維持。
- `addresses_match(expected: str | None, actual: str | None) -> bool`: 非空住所のみ、国・郵便番号・番地の矛盾を許容しない。日本語表記と区切られた建物省略は既存geocoderと同じ規則。
- `location_status(merchant_address, place_address) -> str`: `matched|trajectory_only|needs_review`。
- `read_transaction_addresses(connection, transaction_id: str | None = None) -> list[dict]`: specの住所コンテキスト配列。個別は1要素、存在しない取引はTrajectoryNotFound。
- `annotate_location_status(connection, timeline: dict) -> dict`: コピーへ各eventのlocationStatusを付ける。未紐づけはtrajectory_only。保存用のtimelineは変更しない。
- Store: `get_transaction_addresses(transaction_id=None) -> list[dict]`, `update_merchant_address(transaction_id: str, payload: dict) -> dict`。
- APIはspec §4, §7のGET/PATCH経路・応答をそのまま実装。

- [ ] **Step 1 — REDテストを追加。** `test_address_context_deduplicates_by_id`は同名別支店を混ぜず同じplaceIdを1回返す。`test_patch_is_atomic_and_preserves_other_fields`はexpected一致時だけ更新し、店名または住所不一致409、収入400、IDなし404、未初期化409、未知フィールド400を検証。ID`a/b %日本語`でも同じ取引を読書きする。
  ```python
  assert addresses_match('〒810-0001 福岡市中央区天神2-11-3', '日本, 〒810-0001 福岡市中央区天神２丁目１１番３号')
  assert not addresses_match('福岡市中央区天神2-11-3', '福岡市中央区天神2-11-30')
  assert location_status(None, '福岡市中央区天神2-11-3') == 'trajectory_only'
  assert location_status('住所A', None) == 'needs_review'
  ```
  `test_shared_place_review_is_per_transaction`は共有地点の一方の住所変更だけneeds_review、他方matched、地点DB不変。`test_derived_status_never_enters_saved_state`はAPI/contextに状態あり、read_state/保存データにはなし。
- [ ] **Step 2 — 失敗を確認。** `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p test_transaction_addresses.py`。
- [ ] **Step 3 — 実装。** 住所読取はJOINによる一括処理、同一読取トランザクションを使う。PATCHはBEGIN IMMEDIATE内でexpectedを検査し、住所列だけUPDATEする。正規化・表記比較の重複実装を避け、geocoder固有の精度・matchCode判定はgeocodingに残す。日別APIとtrajectory_contextだけで派生状態を付加し、Storeの保存用読取には混ぜない。
- [ ] **Step 4 — GREEN確認。** 全Backendテスト成功。位置の一致→住所編集→needs_review→地点修正→matchedの往復も確認。
- [ ] **Step 5 — コミット。** `git commit -m "feat: expose address context and guarded address updates"`（該当ファイルを先に明示的にstage）。

### Task 3: 住所の手入力・詳細編集・mock環境

**Files:**
- Create: `front/src/MerchantAddressField.jsx`
- Modify: `front/src/TransactionDialog.jsx`, `front/src/TransactionDetail.jsx`, `front/src/TransactionAddress.jsx`, `front/src/lib/transaction-data.js`, `front/src/lib/api.js`, `front/src/useTransactions.js`, `front/src/App.jsx`, `front/styles.css`, `front/dev/mock-api.mjs`
- Test/modify: `front/src/TransactionAddress.test.jsx`, `front/src/TransactionDialog.test.jsx`, `front/src/useTransactions.test.js`, `front/src/lib/contracts.test.js`, `front/src/dev-environments.test.js`

**Interfaces:**
- transaction-data: `normalizeMerchantAddress(value) -> string|null`（既存ValidationErrorを使用）、`readExpenseDetails`と`parseExpenseDraft`の結果へmerchantAddressを追加。
- `MerchantAddressField({id, value, onChange, error='', disabled=false})`: visible label「住所（任意）」、textarea、エラー関連付け。JSの`[...value].length`で500文字を検証し、UTF-16のmaxLength=500では制限しない。
- api: `getTransactionAddress(id, fetchImpl=fetch) -> AddressContext`, `listTransactionAddresses(fetchImpl=fetch) -> AddressContext[]`, `updateMerchantAddress(id, merchantAddress, expected, fetchImpl=fetch) -> Transaction`。
- useTransactions: `updateMerchantAddress(id, address, expected)`を既存write/refresh経路で提供。
- `TransactionAddress({record, busy=false, onSave})`: 取引住所を表示し、Task 2のGETで関連地点を読む。`onSave(address, expected)`はPromise。TransactionDetail→Appで接続する。

- [ ] **Step 1 — REDテストを追加。** `test_optional_address_create`で未入力も保存可能、500補助漢字成功/501失敗、改行保持。`test_address_edit_cancel_conflict_and_clear`でキャンセルはPATCHなし、明示消去はnull、409/通信失敗で入力維持、二重送信なしを確認。
  ```js
  expect(normalizeMerchantAddress('𠮷'.repeat(500))).toHaveLength(1000); // UTF-16長、500コードポイント
  expect(() => normalizeMerchantAddress('𠮷'.repeat(501))).toThrow();
  // onSave(null, {merchant:'喫茶テスト', merchantAddress:'住所A'}) が明示消去時に1回。
  ```
  `test_trajectory_address_copy_is_explicit`: 参照住所はラベルを区別し、クリック前にPATCHなし、指定した1件だけ保存。`test_stale_response_and_needs_review`: 取引切替の古い応答を無視し、needs_reviewには旧座標リンクなし。旧支出のmerchant/paymentMethod=nullでも住所編集可。
- [ ] **Step 2 — 失敗を確認。** `npm --prefix front test -- src/TransactionAddress.test.jsx src/TransactionDialog.test.jsx src/lib/contracts.test.js`。
- [ ] **Step 3 — 実装。** 詳細画面で住所がなくても追加操作を表示する。再読込失敗を未登録と混同せず、成功後の関連住所と取引のrefreshを行う。mockのGET/PATCH/POST・初期データも同じ住所契約へ揃える。mockでもactual/expectedとstatusを検証するが、外部検索は追加しない。
- [ ] **Step 4 — GREEN確認。** `npm --prefix front test`全件成功。既存の日別APIをmockするTransactionAddressテストは新しい個別住所APIへ更新し、当初の取引ID紐づけ・遅延応答テストを維持。
- [ ] **Step 5 — コミット。** `git commit -m "feat: add merchant address entry and inline editing"`。

### Task 4: レシート住所とagent変更フォーム

**Files:**
- Modify: `backend/agent/receipt.py`, `backend/db/agent_store.py`, `front/src/ReceiptReview.jsx`, `front/src/AgentProposal.jsx`
- Test/modify: `backend/tests/test_receipt_extraction.py`, `backend/tests/test_receipt_upload.py`, `front/src/ReceiptReview.test.jsx`
- Create: `front/src/AgentProposal.address.test.jsx`

**Interfaces:**
- ReceiptCandidate: `merchant_address: str | None = None`、500コードポイント。旧reviewの欠落はNone相当。
- receipt_reviewはcandidate内の住所を保持。missingFieldsへ住所を必須追加しない。
- TransactionFieldsはTask 3のMerchantAddressFieldを使い、`command.data.merchantAddress`の明示値だけ変更する。RecordViewの日本語ラベルは「取引先住所」。
- ReceiptReviewは保存先ごとの住所編集状態を保持。初期値は読取住所、なければ対象取引住所、新規なら空。保存時、未編集かつ読取住所なしならmerchantAddressキーを省略、利用者が空にした場合だけnullを送る。

- [ ] **Step 1 — REDテストを追加。** `test_receipt_address_round_trip`は抽出→確認→提案→承認→再読込で住所と原本の紐づきを確認。`test_unreadable_address_preserves_saved_value`は旧review/Noneと明示消去を区別する。
  ```js
  // 保存先A='住所A', B='住所B', 読取住所なし。
  // Aへ'修正A'を入力→Bでは'住所B'→newでは空→Aでは'修正A'。
  // Bで未編集のsubmitにはmerchantAddressキーなし。Bを空にしたsubmitにはnull。
  ```
  `test_agent_address_diff`は追加・変更・消去が差分に出て、住所未指定の旧コマンドを編集しただけではnull消去へ変換しない。ReceiptCandidateの非文字列・501文字も拒否。
- [ ] **Step 2 — 失敗を確認。** `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_receipt*.py'`、`npm --prefix front test -- src/ReceiptReview.test.jsx src/AgentProposal.address.test.jsx`。
- [ ] **Step 3 — 実装。** 抽出指示に印字住所・本社/電話番号除外・推測禁止を追加。保存先切替の住所状態はtarget ID別に管理し、ターゲットを跨いで転記しない。サーバーのreceipt提案はTask 1の省略維持契約を使う。新住所未読取かつ店名変更なら黙って旧住所を指定せず、住所確認のエラーをフォームに示す。
- [ ] **Step 4 — GREEN確認。** 上記対象テストと全Backend/Frontテスト成功。既存の税・値引・重複・支払額の検証結果が維持される。
- [ ] **Step 5 — コミット。** `git commit -m "feat: preserve receipt addresses through review and approval"`。

### Task 5: 保存住所をagent検索と再利用へ通す

**Files:**
- Modify: `backend/agent/runtime.py`, `backend/agent/place_contracts.py`, `backend/agent/place_matching.py`, `backend/agent/place_search.py`, `backend/agent/web_places.py`, `backend/db/agent_search_store.py`
- Test/modify: `backend/tests/test_agent_runtime.py`, `backend/tests/test_agent_place_matching.py`, `backend/tests/test_agent_place_search.py`, `backend/tests/test_agent_web_places.py`, `backend/tests/test_agent_search_store.py`

**Interfaces:**
- SearchInputとsearch_placeへ`address: str | None = None`を追加。最大500、改行・表記はTask 1の値正規化に準拠。
- Evidence.fieldへaddressを追加。transactionの場合はそのレコードのmerchantAddressを参照し、他のフィールドに偶然同じ文字列があっても根拠としない。他の既存sourceは同会話・同保存先の検証を維持。
- requestのaddressはWeb調査、store_reasons、条件・共有cache key、再利用条件へ通す。既存のaddress_formatだけの変更は引き続きWeb結果を共有。
- 不一致候補のreasonは`address_mismatch`。Task 2のaddresses_matchを使い、住所不明を一致にしない。

- [ ] **Step 1 — REDテストを追加。** `test_address_condition_is_not_dropped`: Providerが受け取るrequest.addressと履歴input.addressが保存値と一致。`test_address_evidence_reads_only_merchant_address`: merchantやtitle中の住所文字列では拒否。`test_same_name_new_address_cannot_reuse_old_coordinates`: saved place、同turn cache、reuse_search_idの3経路で住所A→Bの座標流用を拒否し、表記同値だけを許容。
  ```python
  # Provider rowsは同名の住所A/住所B。request.address='住所B'の候補にAのID/座標はない。
  assert all(c['address'] == '住所B' for c in result['candidates'])
  # coordinates未確認でも、引用付き住所Bをtransaction.updateのmerchantAddressに提案できる。
  assert proposal['after'][0]['merchantAddress'] == '住所B'
  assert store.get_transaction(identifier)['merchantAddress'] != '住所B'  # 承認前
  ```
  `test_runtime_uses_saved_address_without_inventing_country`: scripted modelでtrajectory_context→根拠付き検索→住所を含む変更案を検証。source引用と原文住所が残る。
- [ ] **Step 2 — 失敗を確認。** `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent*.py'`。
- [ ] **Step 3 — 実装。** promptにmerchant_addressビュー列、merchantAddress編集、保存住所の利用、未確認座標と住所だけの保存案を追加。住所は地域用200文字ループへ入れず専用500文字で検証する。現在住所の条件とgroundingを再利用時も再評価する。引用・候補ID・予算・承認の境界を維持。
- [ ] **Step 4 — GREEN確認。** 全Backendテスト成功。旧履歴のaddress欠落はNoneとして読めるが、新たな住所条件付き検索の再利用で条件を無視しない。
- [ ] **Step 5 — コミット。** `git commit -m "feat: ground agent place searches in transaction addresses"`。

### Task 6: 要確認地点の地図表示・再確認導線・CSV

**Files:**
- Modify: `front/src/lib/trajectory-model.js`, `front/src/Trajectory.jsx`, `front/src/TrajectoryMap.jsx`, `front/src/TransactionAddress.jsx`, `front/src/App.jsx`, `front/src/useAgentChat.js`, `front/src/lib/transaction-data.js`, `front/src/Dashboard.jsx`, `front/dev/mock-api.mjs`
- Test/modify: `front/src/lib/trajectory-model.test.js`, `front/src/Trajectory.test.jsx`, `front/src/TrajectoryMap.test.jsx`, `front/src/App.mutations.test.jsx`, `front/src/AgentChat.test.jsx`, `front/src/lib/contracts.test.js`

**Interfaces:**
- buildTrajectoryDays: event.locationStatusを保持し、needs_reviewならevent.coordinates=null。segmentは元の隣接関係を維持。`day.unconfirmedLocationCount: number`と`day.distanceIncomplete: boolean`を追加。
- `Trajectory({..., onReviewAddress})`, `TransactionAddress({..., onReviewAddress})`: `onReviewAddress({transactionId, date})`。
- useAgentChatへ`prefillMessage(text: string)`追加。未送信draftがある場合は消さず改行で追記し、送信・会話作成は行わない。Appで`#agent`へ遷移して入力欄をfocus。
- `serializeTransactionsCsv(records, addressContexts = [])`: 既存9列+「取引先住所」「関連軌跡住所」。AddressContextはTask 2と同じ型。
- AppのexportCsvはTask 3の一括GET成功後だけBlobを作る。取得中はCSV操作をdisabled、失敗は再試行可能な通知。

- [ ] **Step 1 — REDテストを追加。** `test_unconfirmed_middle_visit_does_not_bridge`: A→B→CでBだけneeds_review、eventsは3件、ピンA/Cのみ、両segment.coordinatesはnull、A→C線なし、支出合計・訪問数不変、距離の一部未確認を表示。共有placeでも別transactionのmatched訪問は表示する。
  ```js
  expect(day.events).toHaveLength(3);
  expect(day.events[1].coordinates).toBeNull();
  expect(day.segments.every(segment => segment.coordinates === null)).toBe(true);
  expect(day.unconfirmedLocationCount).toBe(1);
  ```
  `test_review_link_only_prefills_chat`: 既存draft維持、transactionId/日付入りの依頼文、clickでPOST/searchなし。`test_csv_addresses_and_failure`: 最後の2列、複数住所重複排除、改行・カンマ・二重引用符・先頭の=、+、-、@、タブ、CRを検証。GET失敗ではURL.createObjectURLを呼ばず、再試行成功時だけ1回ダウンロード。
- [ ] **Step 2 — 失敗を確認。** `npm --prefix front test -- src/lib/trajectory-model.test.js src/Trajectory.test.jsx src/AgentChat.test.jsx src/lib/contracts.test.js src/App.mutations.test.jsx`。
- [ ] **Step 3 — 実装。** 保存地点のcoordinatesは変更せず、表示用eventだけ無効化する。bbox、距離、番号付きマーカー、選択時のmap移動もnullを扱う。既存のnull除外処理を再利用し、表示対象だけを繋ぎ直さない。詳細には「住所が変わったため、位置の再確認が必要です」、軌跡には「住所と位置の再確認が必要」、旧住所には「軌跡に保存された住所」を表示する。旧API応答でlocationStatusが欠落していても既存の地図表示を維持する。CSVの収入住所は空欄。mockのaddress context/軌跡statusはTask 2の共有ケースを固定fixtureで同値確認する。
- [ ] **Step 4 — GREEN確認。** Front全件成功。修正済み地点の再読込でneeds_reviewと地図除外が解除されるテストも通す。
- [ ] **Step 5 — コミット。** `git commit -m "feat: reconcile trajectory locations and export merchant addresses"`。

### Task 7: 統合検証・レビュー・稼働アプリへの反映

**Files:**
- Create: `front/tests/e2e/merchant-address.spec.cjs`, `docs/verification/2026-10-04-merchant-address.md`
- Modify: `front/tests/e2e/transaction-address.spec.cjs`, `backend/tests/agent_browser_server.py`, `backend/API.md`, `backend/README.md`, `front/README.md`
- Build: `front/dist/`（mainへ統合してから通常配信用に生成・コミット）。

**Interfaces:** Tasks 1–6の契約とspec完成条件を接続する。実行時のPythonパスは`KAKEI_TEST_PYTHON=/Users/spco/Kakei/backend/.venv/bin/python`でPlaywrightに渡す。

- [ ] **Step 1 — 統合テストを追加。** 一時DBに住所なしの支出を作り、住所入力→再読込→編集→消去→関連住所から明示コピー→CSV保存を操作。別シナリオでレシート住所→既存取引への保存→軌跡表示→住所変更→要確認→新地点の承認→地図復帰を確認する。375px/1440pxで長文・入力エラー・確認差分・focus・固定navを撮影。dashboardは初期表示に選択期間と収支があることを検証する。
- [ ] **Step 2 — 全検証を実行。** `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests`、`npm --prefix front test`、`npm --prefix front run build`、`KAKEI_TEST_PYTHON=/Users/spco/Kakei/backend/.venv/bin/python npm --prefix front run test:e2e -- --config playwright.agent-search.config.cjs`、`git diff --check`。全テスト成功、ビルド成功、差分エラーなしを確認。
- [ ] **Step 3 — 実APIを限定検証。** 一時DBとユーザーが既に提供したレシート画像を使い、画像読取1回・agent会話2回以内。住所が読めなければ推測せずnull、読めた場合は候補住所と原本を照合。保存住所を検索条件に渡した事実、住所だけの提案/位置確認の結果を記録。本番DBへ書かない。接続できなければ実施不可の理由を記録し、固定テストの成功と区別する。
- [ ] **Step 4 — 全体レビュー。** requesting-code-reviewに従い、このブランチ全体を1人の新しいレビュアーへ依頼する（Nativeで最後に1回）。仕様・Review Focus・移行・引用・座標再利用を確認。重要指摘は再現テストから修正し、該当する検証を再実行する。
- [ ] **Step 5 — 記録・コミット。** 実行コマンド/結果、PC・phone画像、実APIの制限、移行検証をverificationへ記録。API契約・mock手順も更新し、`git commit -m "test: verify merchant address workflows end to end"`。
- [ ] **Step 6 — 統合と配信確認。** レビュー完了後に既存の作業内容を保ってmainへ統合。取引処理が実行中でないことを確認してDBをバックアップし、配信用distをビルド・コミット。バックエンドをmainから再起動し、8765と5173のAPI・最新assetsを読取で確認。既存の.envと本番データをテスト用途で変更しない。統合/再起動を実施できなければその理由と未反映状態を明記する。

## 計画の自己確認

- Spec §3→Task 1、§4→Tasks 2–3、§5→Task 4、§6→Task 5、§7→Tasks 2/6、§8→Tasks 3/6、§9→Task 7。
- 専用APIの型・経路、住所キー、status値、500文字規則を各Taskで一致させた。
- Review Focusの5項目は指定Taskの具体的なテストへ割り当てた。
- 本計画は実装順と契約を決める文書。実装の関数本体、別の取引先管理機能、新しい依存やAPIキーは含めない。

## 実行への引継ぎ

計画レビューを待つ。利用者が既に選択したNative方式で実装し、実装開始には`superpowers:executing-plans`を使う。
