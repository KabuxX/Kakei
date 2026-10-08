# Receipt Merchant Location Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** レシート登録時に店舗住所を補足し、店舗を特定できない場合は利用者の店舗・地域確認が完了するまで登録を止める。

**Architecture:** 印字住所の抽出とGoogleによる店舗照合を分離し、レシートごとの確認状態を版付きで保存する。変更案は確認結果を固定し、承認時に取引・原本・Google地点参照を原子的に保存する。Google住所はPlace IDから一時表示し、本人由来住所と区別する。

**Tech Stack:** 既存のPython、FastAPI、SQLite、httpx、LangChain、React、Vite、unittest、Vitest、Playwright。Python依存はbackendのuv.lockを使い、新しいプロバイダーや依存パッケージは追加しない。

**Spec:** [承認済み仕様書](../specs/2026-10-08-receipt-merchant-location-design.md)。実装担当とレビュー担当は本計画と仕様書の両方を読む。

## Global Constraints

- レシートや利用者入力の住所は住所欄に保存する。Google検索で得た住所は取引に関連づけたPlace IDから表示時に取得する。
- 複数候補または候補なしでは、店舗・地域を利用者に確認してから登録する。住所を空欄にしたまま続行する操作は設けない。
- 入力の制限は店舗名・支店名・地域各200文字、住所500文字以内とする。
- 1回の検索処理は合計20秒以内、外部検索最大2要求、各通信最大8秒とする。
- レシート読取と初回検索は既存の180秒ターン期限を共有する。確認の期限は24時間、候補は最大10件。
- 検索結果の本文をLLMに渡さず、状態と参照IDだけを渡す。
- 外部通信中はDBトランザクションを保持しない。
- 金額修正では確認を維持し、店舗・住所変更では以前の確認を無効にする。
- Google取得の名前・住所・座標・生レスポンスは新しい確認テーブル、会話、変更案、ログへ保存しない。
- テストは固定Google応答、スクリプト化したモデル、一時DBを使い、普段使いのDBには取引を追加しない。
- ダッシュボードの情報階層やレイアウトは変更しない。アプリ内画面としてDESIGN.md、MASTER.md、ui-ux-pro-maxに従う。

## Review Focus

- 完了前に会話を削除した検索が、会話や確認行を復活させないこと。Task 3の削除競合テストで検証する。
- 金額だけの編集フォームが空の住所欄を送っても、Google地点関連を失わないこと。Task 5の未変更nullテストで検証する。
- 同名支店が同じ建物・番地にある場合でも、住所一致だけで別支店を自動採用しないこと。Task 2で検証する。
- 変更案の地点関連だけが別操作で変わった場合も、古い変更案で上書きしないこと。Task 4で検証する。
- 別のレシートや会話へ移った後に返った検索・Details応答が、画面の候補や保存ボタンを更新しないこと。Task 6で検証する。

---

## ファイルと共通契約

新規ファイルは責務ごとに限定する。

| ファイル | 責務 |
| --- | --- |
| `backend/services/receipt_location_contracts.py` | 入力・確認結果の型、正規化、入力指紋 |
| `backend/db/receipt_location_store.py` | 確認状態のCAS更新と期限回収 |
| `backend/db/merchant_place_store.py` | 取引のGoogle参照を読む・保存する・解除する |
| `backend/services/receipt_location_matching.py` | 候補の純粋な同一性判定 |
| `backend/services/receipt_location.py` | 検索、候補選択、本人住所確認の調停 |
| `backend/services/receipt_location_proposals.py` | 変更案と確認の結びつき、承認条件 |
| `backend/api/receipt_locations.py` | 会話とレシート配下の確認API |
| `front/src/components/receipts/ReceiptLocation.jsx` | 地域入力、再検索、候補選択、状態説明 |
| `front/src/components/receipts/useReceiptLocation.js` | 入力変更・通信・現在版の管理 |

既存のruntime、AgentStore、Storeは呼び出しを接続するだけに留め、検索や照合の実装を増やさない。

`ReceiptLocationInput`はTypedDictで`merchant: str`、`branch: str | None`、`locality: str | None`、`merchantAddress: str | None`を持つ。branch・locality・merchantAddressの空文字はnullへ正規化する。merchantはtrimした文字列とし、空文字は読取直後のneeds_inputに限って許可し、検索・住所確認では非空を要求する。検索用正規化を保存表示値に適用しない。

`ReceiptLocationResolution`はTypedDictで`id, receiptId, revision, input, inputFingerprint, status, placeIds, selectedPlaceId, method, reason, confirmedAt, expiresAt, sourceTransactionId`を持つ。`sourceTransactionId`は既存取引由来の確認だけに設定する。statusは仕様書の6種類、methodは`receipt_address/user_address/google_unique/google_selected/existing_address/existing_google`またはnullとする。confirmedAtは解決時刻またはnull、expiresAtは24時間の期限とする。Google内容を型に含めない。

入力指紋は本人由来の4入力をcanonical JSON化してSHA-256で作る。保存先依存性は`sourceTransactionId`を別途照合する。新規検索結果の利用は保存先に依存させない。

API応答は`{locationResolution: ReceiptLocationResolution}`。新規APIの期待版キーは`revision`、確認参照は`resolutionId`とする。`receipt-proposals`と再確認リクエストは`location: {resolutionId, revision, input}`を受け取る。inputを添えることで、フォームだけで変更した支店・地域でも古い確認を使用できない。

`merchantPlace`の読取形は`{provider: 'google', placeId: str, method: str}`。Google住所は含めない。地点関連なしではこのプロパティを省略し、旧指紋のcanonical表現を維持する。

## Task 1: 確認と取引地点参照の保存

**Files:** Create `backend/services/receipt_location_contracts.py`, `backend/db/receipt_location_store.py`, `backend/db/merchant_place_store.py`; Modify `backend/db/schema.py`; Test `backend/tests/test_receipt_location_store.py`, `backend/tests/test_schema.py`.

**Interfaces:**
- Produces `normalize_location_input(value: object) -> ReceiptLocationInput`、`location_fingerprint(value: ReceiptLocationInput) -> str`。
- Produces `ReceiptLocationStore(db_path)` with `get(thread_id, receipt_id, *, now) -> ReceiptLocationResolution | None`, `seed(thread_id, receipt_id, input, *, status, method, now) -> ReceiptLocationResolution`, `begin_search(thread_id, receipt_id, input, revision, *, now, processing_until, source_transaction_id=None) -> ReceiptLocationResolution`, `finish_search(thread_id, receipt_id, resolution_id, revision, result, *, now, turn_context=None) -> ReceiptLocationResolution`。turn_contextがある場合は同じDBトランザクションでprocessing中のagent_turnsのtokenも確認する。
- Produces `set_selection(thread_id, receipt_id, resolution_id, revision, place_id, *, now) -> ReceiptLocationResolution`と`set_address(thread_id, receipt_id, input, revision, *, method, source_transaction_id=None, now) -> ReceiptLocationResolution`。seedは初回のneeds_inputまたは印字住所を保存し、既存の確認を上書きしない。set_selectionはneeds_selectionの版と候補所属を検証して更新する。
- Produces connection-level `read_merchant_place(connection, transaction_id) -> dict | None`, `write_merchant_place(connection, transaction_id, binding: dict) -> None`, `clear_merchant_place(connection, transaction_id) -> None`。read/writeのbindingは`provider, placeId, method, input, confirmedAt`を持ち、APIのmerchantPlaceは先頭3キーだけへ投影する。

- [ ] **Step 1: 一時DB用のテストを作る。** `test_cas_rejects_old_result`, `test_recover_search_at_deadline`, `test_limits_and_blank_normalization`, `test_delete_cascades_without_changing_transactions`, `test_legacy_schema_migrates_without_backfill`で次の値を検証する。

```python
self.assertEqual(normalize_location_input({'merchant': ' 店 ', 'merchantAddress': ' \r\n '})['merchantAddress'], None)
self.assertEqual(location['expiresAt'], started_at + 86400)
self.assertEqual(recovered['status'], 'unavailable')  # now == processing_until
with self.assertRaises(TrajectoryConflict):
    locations.finish_search(thread, receipt, old_id, old_revision, result, now=now)
```

- [ ] **Step 2: 失敗を確認する。** rootで`uv run --project backend --locked python -m unittest discover -s backend/tests -p test_receipt_location_store.py -v`。新規モジュールまたは期待動作の不足でFAILすること。
- [ ] **Step 3: 保存層を実装する。** スキーマ追加は既存transactions移行とagent/receiptテーブル作成の後に同じ移行トランザクションで行う。確認表は`UNIQUE(thread_id, receipt_id)`、会話・原本へのCASCADE外部キー、版、入力JSON、候補ID JSON、処理期限、24時間期限を持つ。取引地点表はtransaction_id主キーとCASCADE外部キーを持つ。beginで版を進め、finishはid/版/状態/入力/処理期限を条件に更新する。候補・結果は許可キーだけを保存し、Google本文を渡されても保存しない。期限切れ確認はresolvedとして返さない。
- [ ] **Step 4: PASSを確認する。** Step 2のコマンドと`uv run --project backend --locked python -m unittest discover -s backend/tests -p test_schema.py -v`がPASS。
- [ ] **Step 5: 当該ファイルだけをコミットする。** `feat: persist receipt location confirmations and merchant references`。

## Task 2: レシート向けの店舗照合

**Files:** Create `backend/services/receipt_location_matching.py`; Modify `backend/services/google_place_resolution.py`は既存の純粋関数を共有する必要がある場合だけ; Test `backend/tests/test_receipt_location_matching.py`, `backend/tests/test_google_place_resolution.py`; Reuse `backend/tests/google_places_fixtures.py`.

**Interfaces:**
- Consumes Task 1の`ReceiptLocationInput`と既存`GoogleCandidate`。
- Produces `receipt_query_variants(input: ReceiptLocationInput) -> list[str]`、`match_receipt_places(input, candidates: list[GoogleCandidate]) -> dict`。結果は`{status, placeIds, selectedPlaceId, method, reason}`で、Google本文を含めない。

- [ ] **Step 1: 判定のテストを作る。** `test_exact_branch_unique`, `test_brand_only_never_auto_resolves`, `test_same_building_different_branch`, `test_missing_address_or_political_place_excluded`, `test_without_coordinates_can_resolve`, `test_duplicate_ids_and_normalized_query`。

```python
self.assertEqual(match_receipt_places(branch_input, [exact])['status'], 'resolved')
self.assertEqual(match_receipt_places(brand_input, [exact])['status'], 'needs_selection')
self.assertNotIn(other_branch.place_id, match_receipt_places(branch_input, [other_branch])['placeIds'])
self.assertLessEqual(len(receipt_query_variants(input)), 2)
```

- [ ] **Step 2: FAILを確認する。** `uv run --project backend --locked python -m unittest discover -s backend/tests -p test_receipt_location_matching.py -v`。
- [ ] **Step 3: 純粋関数を実装する。** 店舗・支店の正規化、住所・地域の矛盾、物理店舗type、非空住所を確認する。ブランドのみを具体的な支店一致と扱わない。正規化した検索2種から重複を除く。候補は10件以内でPlace IDごとにまとめる。hard mismatchは選択対象からも除く。軌跡の座標必須条件と既存の照合結果を維持する。
- [ ] **Step 4: PASSを確認する。** Step 2と`uv run --project backend --locked python -m unittest discover -s backend/tests -p test_google_place_resolution.py -v`がPASS。
- [ ] **Step 5: コミットする。** `feat: match receipt merchants without guessing branches`。

## Task 3: 住所確認サービスとAPI

**Files:** Create `backend/services/receipt_location.py`, `backend/api/receipt_locations.py`; Modify `backend/api/app.py`; Test `backend/tests/test_receipt_location_service.py`, `backend/tests/test_receipt_location_api.py`.

**Interfaces:**
- Consumes Tasks 1–2と`GooglePlacesClient.search_text(query, region_code=None)`、`details(place_id)`。
- Produces `ReceiptLocationService(store, *, client_factory=GooglePlacesClient, monotonic=time.monotonic, wall_clock=time.time)` with `async initialize(thread_id, receipt_id, candidate: ReceiptCandidate, *, deadline, turn_context) -> ReceiptLocationResolution`, `async search(thread_id, receipt_id, input, revision, *, source_transaction_id=None, deadline=None) -> ReceiptLocationResolution`, `async select(thread_id, receipt_id, resolution_id, revision, place_id) -> ReceiptLocationResolution`, `confirm_address(thread_id, receipt_id, input, revision, *, source_transaction_id=None) -> ReceiptLocationResolution`。
- Produces `register_receipt_locations(app, store, *, service_factory=ReceiptLocationService)`と仕様書のGET/search/selection/address routes。create_appへ任意の`receipt_location_service_factory`を追加し、テスト時だけ注入する。

- [ ] **Step 1: 固定clientと制御可能なclockでテストを作る。** `test_printed_address_skips_google`, `test_search_20_seconds_two_requests`, `test_select_checks_current_candidates_and_details`, `test_configuration_not_found_timeout_distinct`, `test_changed_input_discards_old_search`, `test_deleted_thread_does_not_resurrect`, `test_existing_target_requires_same_merchant`, `test_wrong_thread_and_expired_receipt_rejected`。

```python
self.assertEqual(printed['method'], 'receipt_address'); self.assertEqual(client.queries, [])
self.assertLessEqual(len(client.queries), 2)
self.assertEqual(config_failure['reason'], 'provider_configuration')
self.assertEqual(missing['status'], 'not_found')
self.assertEqual(forged_selection.status_code, 400)
self.assertEqual(stale_selection.status_code, 409)
```

- [ ] **Step 2: FAILを確認する。** `uv run --project backend --locked python -m unittest discover -s backend/tests -p 'test_receipt_location_*py' -v`。
- [ ] **Step 3: サービスとroutesを実装する。** 操作ごとに原本の会話所属と有効性を確認する。印字住所は検索なしで初期化する。Google検索は2要求/20秒/各8秒/10候補、初回だけturn deadlineとtokenを共有し、キャンセル後のfinishを拒否する。検索0件、設定、通信、時間切れを別reasonにする。選択は今回のIDとDetailsを再照合する。本人住所確認はmerchantと非空住所を要求する。sourceTransactionId指定時は実DBの同一店舗・住所またはGoogle参照を照合し、別保存先への流用を禁止する。ネットワーク前後だけ短いDB書込みを行い、長いロックを保持しない。
- [ ] **Step 4: PASSを確認する。** Step 2がPASS。削除競合テストは途中で会話を削除してawaitを解放し、確認行数0・取引行数不変を実際に読む。
- [ ] **Step 5: コミットする。** `feat: resolve receipt addresses with scoped confirmation APIs`。

## Task 4: Agentと変更案と原子的承認への接続

**Files:** Create `backend/services/receipt_location_proposals.py`; Modify `backend/agent/runtime.py`, `backend/db/agent_store.py`, `backend/services/agent_changes.py`, `backend/api/receipts.py`, `backend/api/agent.py`, `backend/api/app.py`; Test `backend/tests/test_receipt_location_proposals.py`, `backend/tests/test_receipt_location_runtime.py`, `backend/tests/test_agent_changes.py`, `backend/tests/test_agent_api.py`, `backend/tests/test_receipt_upload.py`.

**Interfaces:**
- Consumes Task 3のinitialize、Task 1の保存と入力指紋。
- Extends `AgentRunner(..., receipt_location_service_factory=ReceiptLocationService)`。create_appとregister_agentはTask 3で指定したfactoryを通常runnerへ渡し、既存のrunner_factory(store)注入を維持する。
- Produces `bind_receipt_location(connection, thread_id, receipt_id, target, draft, location: dict, *, now) -> dict`、`validate_receipt_location(metadata: dict, command: dict, *, now) -> None`、`apply_receipt_location(connection, transaction_id, binding: dict) -> None`。
- Extends `AgentStore.create_receipt_proposal(..., location=None)`と`revise_receipt_proposal_location(proposal_id, expected_revision, draft, location) -> dict`。再確認routeは`POST /api/agent/proposals/{proposal_id}/receipt-location`、bodyは`{revision, draft, location}`。

- [ ] **Step 1: 承認とモデル入力のテストを作る。** `test_unresolved_create_rejected`, `test_resolved_reference_saved_atomically`, `test_place_only_conflict_blocks_approval`, `test_reconfirmation_updates_same_pending_proposal`, `test_amount_edit_keeps_binding_but_merchant_edit_rejected`, `test_old_proposal_remains_approvable`, `test_google_content_not_in_model_or_json`, `test_initial_search_shares_turn_deadline`。

```python
self.assertEqual(unresolved_response.status_code, 400)
self.assertEqual(reconfirmed['id'], pending['id'])
self.assertEqual(reconfirmed['revision'], pending['revision'] + 1)
self.assertEqual(first_approval, repeated_approval)
self.assertNotIn('Google専用の住所文字列', serialized_model_and_database)
```

- [ ] **Step 2: FAILを確認する。** `uv run --project backend --locked python -m unittest discover -s backend/tests -p test_receipt_location_proposals.py -v`と同じコマンドの`-p test_receipt_location_runtime.py`。
- [ ] **Step 3: 既存フローへ接続する。** runtimeは抽出直後にinitializeし、read_receiptとreceiptReviewへ参照だけを添える。get_threadは最新確認状態を合成する。新規レシート変更案はlocation必須、Googleの場合はmerchantAddressをnullとし、既存住所の削除も差分に出す。metadataはGoogle本文を持たない固定bindingとする。read_stateに`merchantPlaces`の保存済みbinding一覧を加え、baseline_valueに`merchant-place:<transaction_id>`を追加する。新しい取引更新案ではこのbaselineも保存し、関連だけの変更を検出する。旧proposalのbaselineキーは増やさず互換性を維持する。再確認では同じpending変更案の版・baselines・before/afterを更新する。普通のreviseで店舗入力が変わったら保存可能にせず、再確認を要求する。承認でbinding・期限・店舗入力・sourceTransactionId・地点関連の元データを検証し、取引保存とattachと地点参照保存を同じトランザクションで行う。旧proposalはmetadataがない場合だけ従来ルールを適用し、新規作成APIのlocation省略で旧扱いにしない。
- [ ] **Step 4: PASSと回帰を確認する。** `uv run --project backend --locked python -m unittest discover -s backend/tests -p 'test_receipt_location_*py' -v`および`-p 'test_agent_*py'`、`-p 'test_receipt_*py'`がPASS。地点保存を故意に失敗させ、取引・添付・proposal状態が全てロールバックされることを検証する。
- [ ] **Step 5: コミットする。** `feat: require resolved receipt locations before transaction approval`。

## Task 5: 保存後の住所表示と通常編集の整合性

**Files:** Modify `backend/db/store.py`, `backend/db/merchant_place_store.py`, `backend/services/agent_changes.py`, `backend/services/transaction_addresses.py`, `front/src/components/transactions/TransactionAddress.jsx`; Reuse `front/src/components/places/GooglePlaceResults.jsx`, `front/src/components/places/DemoPlaceResults.jsx`; Test `backend/tests/test_merchant_place_transactions.py`, `backend/tests/test_transaction_addresses.py`, `front/src/tests/TransactionAddress.test.jsx`, `front/src/tests/App.edit.test.jsx`, `front/src/lib/merchant-address-csv.test.js`.

**Interfaces:**
- Consumes Task 1のread/write/clearとTask 4のbinding。
- Produces 任意の`merchantPlace`を含むStore.list_transactions/get_transactionの読取結果。Task 4のread_stateの保存済み関連と一致するAPI投影を返す。
- Produces `should_clear_merchant_place(old: dict, draft: dict, *, address_only=False) -> bool` in `backend/db/merchant_place_store.py`。住所PATCHは明示操作としてaddress_only=True、通常PUTは正規化後の店舗名・住所の実際の変更またはincomeへの変更だけで解除する。

- [ ] **Step 1: 編集と表示のテストを作る。** `test_amount_only_full_draft_preserves_null_address_reference`, `test_patch_null_explicitly_clears_reference`, `test_merchant_address_or_income_change_clears`, `test_delete_cascades`, `test_address_precedes_google`, `test_details_failure_keeps_transaction_and_offers_retry`。

```python
self.assertFalse(should_clear_merchant_place(old, {**draft, 'merchantAddress': None}))  # old addressもnull、店舗不変
self.assertTrue(should_clear_merchant_place(old, {'merchantAddress': None}, address_only=True))
self.assertEqual(updated['merchantPlace']['placeId'], 'fixture-one')  # 金額のみ変更
```

フロントではGoogle住所が編集フォームの初期値に入らず、金額のみの保存でも関連を維持し、CSVにGoogle表示住所が入らないことをassertする。
- [ ] **Step 2: FAILを確認する。** rootで`uv run --project backend --locked python -m unittest discover -s backend/tests -p test_merchant_place_transactions.py -v`、frontで`npm test -- src/tests/TransactionAddress.test.jsx src/tests/App.edit.test.jsx src/lib/merchant-address-csv.test.js`。
- [ ] **Step 3: 読取と編集と表示を実装する。** 一覧読取は関連を一括取得してN+1を避ける。通常編集とAgentの通常取引編集で同じ解除判定を使う。previewのafterと保存結果に関連を反映し、旧canonicalは関連なしを省略する。Google関連のない旧住所表示を維持しつつ、本人住所なし・merchantPlaceありではGoogle一時表示を使う。demoはDemoPlaceResultsだけを使う。地点取得失敗は関連を削除せず再読み込みを提供する。Google文字列をCSVや編集値に転記しない。
- [ ] **Step 4: PASSを確認する。** Step 2と`uv run --project backend --locked python -m unittest discover -s backend/tests -p test_transaction_addresses.py -v`がPASS。
- [ ] **Step 5: コミットする。** `feat: display receipt merchant references and preserve edit semantics`。

## Task 6: レシートの店舗確認と再確認画面

**Files:** Create `front/src/components/receipts/ReceiptLocation.jsx`, `front/src/components/receipts/useReceiptLocation.js`; Modify `front/src/components/receipts/ReceiptReview.jsx`, `front/src/components/agent/AgentProposal.jsx`, `front/src/pages/AgentChat.jsx`, `front/src/lib/agent-api.js`, `front/src/components/places/GooglePlaceResults.jsx`, `front/styles.css`; Test `front/src/tests/ReceiptLocation.test.jsx`, `front/src/tests/ReceiptReview.test.jsx`, `front/src/tests/AgentChat.test.jsx`, `front/src/tests/GooglePlaceResults.test.jsx`.

**Interfaces:**
- Consumes Task 3のroutesとTask 4の再確認route。
- Produces client methods `getReceiptLocation(thread, receipt)`, `searchReceiptLocation(thread, receipt, {revision, input, sourceTransactionId})`, `selectReceiptLocation(thread, receipt, {resolutionId, revision, placeId})`, `confirmReceiptAddress(thread, receipt, {revision, input, sourceTransactionId})`, `reconfirmReceiptProposal(proposal, {revision, draft, location})`。いずれも対応するresolutionまたはproposalを返す。
- Produces `useReceiptLocation({threadId, receiptId, initialResolution, input, target, readOnly})` returning `{resolution, pending, error, resolved, search, select, confirmAddress, reload}`。`ReceiptLocation`はこの戻り値と`input/onInputChange`を受け取る。
- Extends `GooglePlaceResults` with optional `selectedPlaceId`, `onSelect(placeId)`, `disabled`, `onRetry`。既存の表示専用呼出しを維持する。

- [ ] **Step 1: フォーム操作のテストを作る。** `blocks_proposal_until_location_resolved`, `preserves_amount_items_while_searching`, `invalidates_on_branch_locality_or_merchant_change`, `does_not_invalidate_on_amount_change`, `ignores_late_response_after_receipt_switch`, `keeps_target_specific_confirmations_separate`, `reconfirms_same_pending_proposal`, `focuses_error_summary_and_announces_status`。

```js
expect(screen.getByRole('button', {name: '変更案を確認'}).disabled).toBe(true);
expect(screen.getByLabelText('金額 1').value).toBe('1139');
expect(api.proposeReceipt.mock.lastCall[1].location.resolutionId).toBe('current-resolution');
expect(screen.getByRole('button', {name: '変更案を確認'}).disabled).toBe(true); // 支店変更直後
```

- [ ] **Step 2: FAILを確認する。** frontで`npm test -- src/tests/ReceiptLocation.test.jsx src/tests/ReceiptReview.test.jsx src/tests/GooglePlaceResults.test.jsx`。
- [ ] **Step 3: 確認画面を実装する。** hookは入力指紋と対象IDを比較し、変更直後にresolvedをfalseにする。通信はAbortControllerと対象・版のguardで古い応答を無視する。再検索/選択/本人住所確認は同時送信を抑止する。「店舗・住所」「支店名」「地域」をlabelで示し、候補に店舗名・住所・地図リンクと選択操作を提供する。本人住所欄へGoogle文字列をコピーしない。保存先変更で継承確認を解除する。再確認が必要なpending変更案からReceiptReviewを開き、既存draftを保持して再確認routeで同じproposalを更新する。readOnlyは検索・編集をせず固定表示だけにする。disabledの理由、欄ごとのエラー、focusableエラー要約、status領域を追加する。
- [ ] **Step 4: PASSを確認する。** Step 2と`npm test -- src/tests/AgentChat.test.jsx src/tests/AgentChat.demo.test.jsx`がPASS。既存の税不一致・品目編集・保存先のテストには確認済みfixtureを追加し、住所gateを迂回しない。
- [ ] **Step 5: コミットする。** `feat: confirm receipt merchants before preparing transactions`。

## Task 7: 一時サーバーで全体検証とビルド

**Files:** Create `backend/tests/receipt_location_browser_server.py`, `front/playwright.receipt-location.config.cjs`, `front/tests/e2e/receipt-location.spec.cjs`, `front/dev/mock-merchant-place-fixtures.mjs`, `front/src/lib/mock-merchant-place.test.js`; Modify `backend/tests/agent_browser_server.py`, `front/dev/mock-api.mjs`, `front/src/lib/demo-api.test.js`, `front/src/lib/demo-validation.test.js`, `backend/API.md`, `backend/README.md`; Generate `front/dist/` through build; Save verification note at `docs/verification/2026-10-08-receipt-merchant-location/README.md`.

**Interfaces:**
- Consumes Tasks 1–6の実APIを一時DBと固定clientで通す。
- Browser fixtureはcreate_appへのTask 3のservice factoryと既存runner_factoryを使う。Google表示APIのclientもプロセス内の固定clientへ差し替える。外部OpenAI/Google要求を発行しない。
- 新しいPlaywright configは127.0.0.1:8768、一時DB、reuseExistingServer=false。mockモードは固定merchantPlaceとDetails応答だけを提供し、Agent全体の新しいmockサブシステムは作らない。

- [ ] **Step 1: 実際のユーザーフローをテストする。** `ambiguous_receipt_requires_region_before_save`, `unique_receipt_saves_reference_and_displays_address`, `changed_merchant_requires_reconfirmation`, `details_retry_and_duplicate_approval`, `phone_keyboard_and_no_horizontal_overflow`。1440x900と375x812で、住所なしレシート添付→未解決→地域入力→選択→変更案→保存→取引詳細を通す。保存前のDB取引件数が増えないこと、Google住所ではmerchantAddress=nullで関連行1件になることをHTTP結果とDBでassertする。demoテストはreadOnly表示時の外部fetchが0、mockテストは固定Detailsの住所表示と関連解除をassertする。
- [ ] **Step 2: FAILを確認する。** frontで`npx playwright test --config playwright.receipt-location.config.cjs tests/e2e/receipt-location.spec.cjs`と`npm test -- src/lib/mock-merchant-place.test.js src/lib/demo-api.test.js src/lib/demo-validation.test.js`。不足するfixturesや挙動のFAILを確認する。
- [ ] **Step 3: 必要なfixtureと説明を接続する。** 既存browser serverのレシートfixtureも確認状態を生成して旧E2Eを維持する。mockは架空の固定Place ID・住所と編集時の解除条件を実装する。demoは既存の独立した出典データを使用し、Google lookupへ接続しない。API.mdに新routes、location参照、再確認、merchantPlace、エラーを記載する。READMEに確認手順、表示時の再取得、CSVの住所範囲を説明する。
- [ ] **Step 4: 必須チェックを完了する。** バックエンド全体は`KAKEI_DB_PATH="$(mktemp -d)/kakei.sqlite3" uv run --project backend --locked python -m unittest discover -s backend/tests -v`がPASS。frontで`npm test`、`npm run build`、`npm run build:demo`が成功。demo build出力は既存vite設定の専用出力先を使い通常distを上書きしないことを確認する。新E2Eと`npx playwright test --config playwright.agent.config.cjs tests/e2e/receipt-tax.spec.cjs tests/e2e/iphone-receipts.spec.cjs tests/e2e/agent-delete.spec.cjs`がPASS。旧税・iPhone・削除検証に新しい住所必須条件を正しく組み込む。
- [ ] **Step 5: デスクトップと電話幅の結果を目視確認して記録する。** 未解決理由、入力値保持、候補名と住所、保存操作、保存後の住所と帰属、再試行、キーボード操作を確認し、一時サーバーのスクリーンショットと検証結果をverification noteに残す。ブラウザを利用できない場合は構造確認と未検証範囲を明記し、目視成功と主張しない。`git diff --check`が成功したら変更した当該ファイルと生成distだけをコミットする。commit messageは`test: verify receipt merchant location registration end to end`。

## 計画のレビューと実行

Tasks 1–7は上記の順序で実施する。各タスクの完成条件は記載したテストのPASSであり、実装前に期待動作のFAILを確認する。必須の全体検証はTask 7にまとめ、途中で無関係な全件検証を繰り返さない。

実行前に計画のレビューと実行方法の選択が必要。サブエージェント方式ではタスクごとに実装とレビューを行う。このセッションでの方式では同じ担当が順に実装し、最後に独立レビューを行う。いずれも実行時にusing-git-worktreesで作業場所を決め、通常DBではテストしない。

推奨はサブエージェント方式。7タスクが確認状態・版・保存の契約を共有し、誤った支店や古い確認での登録を防ぐため、各段階の独立レビューが役立つ。
