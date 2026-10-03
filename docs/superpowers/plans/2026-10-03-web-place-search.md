# Web Place Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Geoapify を廃止し、出典付き Web 店舗検索と保存可能な Mapbox 座標を用いて軌跡を作成できるようにする。

**Architecture:** 単一 LangChain agent の検索ツールの内側を、権限のない Web 調査、構造化抽出、住所ジオコーディングに分ける。検索履歴と候補選択の境界を維持し、出典をメッセージと地点に保存する。選択できない住所候補も失わず画面へ返す。

**Tech Stack:** 既存 Python / FastAPI / LangChain / httpx / SQLite / React / Vite / Vitest / Playwright。OpenAI Responses API と Mapbox Geocoding v6。新しい製品依存は追加しない。

**Spec:** `docs/superpowers/specs/2026-10-03-web-place-search-design.md`（2026-10-03 承認済み）

## Global Constraints

- Geoapify への新しい通信と設定依存を廃止する。既存 `.env` のキーを勝手に削除・書換えしない。
- 検索モデル: `KAKEI_AGENT_SEARCH_MODEL`、未設定時 `KAKEI_AGENT_MODEL`。既存指定 `gpt-6-luna` を無断変更しない。
- OpenAI: `web_search`、検索必須、`store=false`、各最大6,000出力トークン、SDK自動再試行なし。引用と検索の実記録だけを保存する。
- Mapbox: 専用 `MAPBOX_GEOCODING_ACCESS_TOKEN`、`permanent=true`、`autocomplete=false`、`language=ja`、応答最大5件。国の根拠がある場合だけcountryを指定する。
- 期限: agent120秒、リース130秒、検索開始から85秒かつturn終了10秒前まで。Web最大3要求×35秒、抽出最大3要求×15秒、Mapbox最大10住所×5秒・同時2。Web1要求内 `max_tool_calls=2`。
- 1店舗検索: Web1回、抽出1回、住所最大5件。提示最大5件。外部HTTP本文各512 KiB、候補各8 KiB、結果40 KiB、検索全体256 KiB、履歴32 KiB、会話要約8 KiB。
- 名前・住所・URL・IDを途中で切らない。副次出典または候補単位で省略し理由を残す。
- 地域を東京・日本に固定しない。座標はMapbox応答・保存済み地点・利用者の手動指定だけから取得する。
- 旧地点・旧検索・未承認提案の読込と承認を維持する。新検索で旧方式の検索履歴をコピーしない。
- UIはアプリ内画面。実装前に `ui-ux-pro-max` と `DESIGN.md`、MASTERを読む。現在agent-chat/trajectory専用のページ指針はないため、既存画面の情報階層を継続する。外観はDESIGNを優先。
- 実行方式は従来の利用者指定 **native** を継続。計画レビュー後に隔離worktreeを作り、実装者が全タスクを実施、最後に独立レビュー1回。
- 実DBでテストしない。キーやキー付きURLをログ・差分へ出さない。mainへのマージ・稼働アプリ再起動は別の指示による。

## Review Focus

1. 別支店の住所を含む引用文、または住所を支えない引用リンクから候補が確定されないこと（Task 2）。
2. 全角番地・漢数字・丁目と、似た別番地の区別。精度情報のない海外住所を確定しないこと（Task 3）。
3. 同じ建物内の別店舗、同一店舗の異なる出典を取り違えず、地域訂正・refresh・履歴再利用が矛盾しないこと（Task 4）。
4. モデルの失敗や応答紛失・再送・再読込でも、引用が別メッセージへ付いたり期限前に処理権限が失効したりしないこと（Tasks 1・5）。
5. 長い日本語出典や未確認候補が選択肢から無言で消えず、キーボード・スマートフォンで出典と選択状態を読めること（Tasks 4・6）。

## ファイル構造と共有契約

新規の単位:

- `backend/services/place_evidence.py`: 出典URL、出典・座標根拠属性の共通検証。DB/HTTP/UIへ渡す前の形を統一。
- `backend/agent/place_http.py`: 固定プロバイダーホストへの非同期JSON通信、512 KiB制限、エラー分類。任意URL取得には使わない。
- `backend/agent/web_places.py`: Responses検索→引用つきレポート、ツールなし抽出→Web店舗候補。
- `backend/agent/geocoding.py`: Mapbox応答の住所要素・精度照合。
- `backend/agent/limits.py`: 120/130/85秒とプロバイダー別上限の定数。
- `front/src/PlaceSources.jsx`: 引用ID解決、店舗出典・座標帰属表示。

既存の `place_contracts.py` に TypedDict を置く。`Source={id,title,url,kind,retrievedAt}`、`WebPlace={id,name,branch,address,country_code,locality,sources,evidenceText,unresolved}`、`ResearchReport={text,sources,actions,usage,retrievedAt}`、`GeocodeResult={candidates,unresolved}`。WebPlaceには座標を許可しない。各 geocode candidate は `{coordinates,geocoding}` を持つ。`geocoding` のキーは仕様§6と同一。

検索結果は既存 `SearchResult` に `pipelineVersion='web-mapbox-v1'`、`unlocatedCandidates`、`sources` を追加する。未確認候補は `{id,name,address,sources,unresolved}` で `candidates` と分離。`sources` のIDはサーバー発行で検索IDにより名前空間を分け、モデルが自作したURLと交換しない。

テストは既存 `unittest`、`httpx.MockTransport`、一時SQLiteを利用する。新規 `backend/tests/web_place_fixtures.py` に合成の公式ページ、住所、Mapbox応答を置く。店名は対象支店を使えるが、合成住所・座標を実店舗の確認結果と記載しない。

---

### Task 1: 出典属性とメッセージの後方互換な保存

**Files:** Create `backend/services/place_evidence.py`, `backend/tests/web_place_fixtures.py`, `backend/tests/test_place_evidence.py`; Modify `backend/agent/place_contracts.py`, `backend/db/schema.py`, `backend/db/trajectory_store.py`, `backend/db/agent_store.py`, `backend/services/trajectory_validation.py`, `backend/services/trajectory_mutation.py`, `backend/services/agent_places.py`, `backend/tests/test_schema.py`, `backend/tests/test_agent_store.py`, `backend/tests/test_trajectory_store.py`。

**Interfaces:** `safe_source_url(value: str) -> str` は検証済みURLまたはValidationError。`validate_place_evidence(place: dict) -> None` は仕様§6の任意属性を検証。`AgentStore.complete_turn(...)` は内部resultの `sources` と `searchIds` をassistantメタデータへ保存し、送信応答・`get_thread`のmessageに `sources` を返す。旧messageは `sources=[]`。

共通属性の上限はtitle200文字、URL2048文字、id100文字、name200文字、address500文字、evidenceText500文字、retrievedAtは有限のUNIX秒。sources最大3件、kindは仕様の4値。文字列超過は切らず拒否する。geocodingは固定キーのみ、provider=mapbox、permanent=true、matchCodeはMapboxの住所一致情報だけを正規化して保持する。

- [ ] **Step 1: 保存契約の失敗テストを追加する。** `test_evidence_round_trip_and_old_schema`, `test_message_sources_survive_cached_response`, `test_source_urls_preserve_identity` で以下を固定する。
  ```python
  self.assertEqual(reloaded_place['sources'], place['sources'])
  self.assertEqual(reloaded_place['geocoding'], place['geocoding'])
  self.assertEqual(reloaded_message['sources'], response['message']['sources'])
  self.assertEqual(old_message['sources'], [])
  self.assertEqual(safe_source_url('https://store.example/detail?id=12'), 'https://store.example/detail?id=12')
  ```
  URLのuserinfo、localhost、IPv4/IPv6の非公開直指定、javascript、キー付きAPI URLを拒否する。schema移行を2回適用し、旧提案・旧日時・取引が変わらないことを確認する。
- [ ] **Step 2: REDを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_place_evidence.py'`。新関数未定義または新属性未対応でFAIL。
- [ ] **Step 3: 保存・検証を実装する。** 軌跡テーブルに `sources_json TEXT NOT NULL DEFAULT '[]'`、`geocoding_json TEXT`、メッセージに `metadata_json TEXT NOT NULL DEFAULT '{}'` を追加する冪等migration。旧地点には任意キーを増やさず旧ハッシュを保つ。地点全体の置換・日別読込・全件読込・更新・エクスポートに属性を通す。messageの全INSERTを列指定へ変更し、引用は完了トランザクション内で本文と保存する。手動地点はproviderメタデータを引き継がない。
- [ ] **Step 4: GREENと関連回帰を確認する。** `test_place_evidence.py`、`test_schema.py`、`test_agent_store.py`、`test_trajectory*.py` を各 `unittest discover -s backend/tests -p '<pattern>'` で実行し全件成功。
- [ ] **Step 5: コミットする。** `git commit -m "feat: persist place and message source evidence"`。

### Task 2: 引用に結び付いた Web 店舗検索

**Files:** Create `backend/agent/place_http.py`, `backend/agent/web_places.py`, `backend/tests/test_agent_web_places.py`; Modify `backend/agent/place_contracts.py`, `backend/agent/places.py`, `backend/tests/web_place_fixtures.py`。

**Interfaces:** `PlaceProviderError(code: str, *, stop_turn=False)` を `place_http.py` に定義し既存placesから再exportして移行期間の互換性を保つ。`request_json(client, provider: str, path: str, *, params=None, body=None, timeout: float) -> dict` はproviderをopenai/mapboxだけに限定。`WebPlaceProvider(client=None, *, model=None)` はasync context manager、`research(request: SearchInput, *, timeout: float) -> ResearchReport`、`extract(report: ResearchReport, *, timeout: float) -> list[WebPlace]` を提供。

- [ ] **Step 1: 失敗テストを追加する。** `test_research_requires_search_and_returns_real_sources`, `test_extraction_rejects_unbound_address_and_url`, `test_report_instructions_cannot_grant_tools`, `test_bounded_provider_transport`。
  ```python
  self.assertEqual(sent['tools'], [{'type': 'web_search'}])
  self.assertEqual(sent['tool_choice'], 'required')
  self.assertEqual(sent['max_tool_calls'], 2)
  self.assertFalse(sent['store'])
  self.assertEqual(sent['max_output_tokens'], 6000)
  self.assertNotIn('coordinates', extracted[0])
  self.assertEqual(unbound_result, [])
  ```
  名前の違う2支店を一段落に混ぜた応答、引用なしの住所、sources一覧だけにあるURL、架空引用ID、検索未実行、incomplete/refusal、512 KiB超過、非JSON、401/403/429、timeout、取消をfixture化する。支店との結び付きを確認できない行は未確認理由付きまたは除外とし確定候補にしない。
- [ ] **Step 2: REDを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_web_places.py`。新provider未定義でFAIL。
- [ ] **Step 3: 検索と抽出を実装する。** httpxのstreamで固定 `/v1/responses` に送信し、HTTP本文の上限を読込中に検査。researchは店舗・地域だけを入力、引用annotationsのoffsetとURLを検証しIDを割り当てる。extractはtoolsなし・strict JSON schemaのtext.formatを用い、名称/住所/引用ID/短い根拠文/不明点を抽出。全候補をサーバーで再検証し、レポートにない根拠文や引用を拒否する。公式と断定できないサイトはkind=unknownに落とす。エラーにはキー/本文/URLを載せず、利用量・実actionsをResearchReportに返す。
- [ ] **Step 4: GREENを確認する。** Step 2のコマンドと `test_place_evidence.py` が全件成功。通信回数1回で自動再試行がないこともassert。
- [ ] **Step 5: コミットする。** `git commit -m "feat: discover cited store addresses with web search"`。

### Task 3: 永久保存できる住所座標の取得

**Files:** Create `backend/agent/geocoding.py`, `backend/tests/test_agent_geocoding.py`; Modify `backend/tests/web_place_fixtures.py`, `backend/agent/place_contracts.py`。

**Interfaces:** Task 2の `request_json` / `PlaceProviderError`、Task 1のWebPlace/GeocodeResultを使用。`MapboxGeocoder(client=None)` はasync context manager、`geocode(place: WebPlace, *, timeout: float) -> GeocodeResult`。`match_address(place: WebPlace, feature: dict) -> list[str]` は不一致・不足のreasonコードを返し、空配列の場合のみcandidateを返せる。

- [ ] **Step 1: 失敗テストを追加する。** `test_permanent_geocoding_for_japan_and_overseas`, `test_address_number_and_precision_gate`, `test_mapbox_failure_never_uses_temporary_mode`。
  ```python
  self.assertEqual(params['permanent'], 'true')
  self.assertEqual(params['autocomplete'], 'false')
  self.assertEqual(params['language'], 'ja')
  self.assertEqual(japan_params['country'], 'jp')
  self.assertEqual(overseas_params['country'], 'gb')
  self.assertEqual(block_result['candidates'], [])
  self.assertIn('interpolated', interpolated['candidates'][0]['geocoding']['accuracy'])
  ```
  `１丁目２－３`と`1丁目2-3`を同一視し、`1丁目2-30`と区別。丁目部分だけの漢数字→数字変換は許可するが地名の漢字は変更しない。番地不明・match_code欠落・不一致・複数対応・別国・市中心・NaN/bool座標を選択不能にする。
- [ ] **Step 2: REDを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_geocoding.py`。新geocoder未定義でFAIL。
- [ ] **Step 3: Mapboxと照合を実装する。** `/search/geocode/v6/forward`へ専用キーで送信。文字幅・住所の区切りを正規化し、候補のcontext・match_code・feature_typeと比較。番地要素の推定/不一致、検証不能な住所はunresolvedにする。英語住所も同じ安全側の基準。Mapbox query上限256文字/20語を超える入力は切らず未確認理由を返す。最大5featuresから一意に一致するaddress/secondary_addressを採用し、建物名省略を記録。保存用geocodingにはキー付きURLを含めない。
- [ ] **Step 4: GREENを確認する。** Step 2と `test_agent_web_places.py` が全件成功。401/403/429・5秒timeout・512 KiB・取消の通信境界を固定応答で確認。
- [ ] **Step 5: コミットする。** `git commit -m "feat: geocode verified addresses with permanent Mapbox results"`。

### Task 4: 検索手順・予算・履歴の置換

**Files:** Create `backend/agent/limits.py`; Modify `backend/agent/place_search.py`, `backend/agent/place_matching.py`, `backend/db/agent_search_store.py`, `backend/agent/place_contracts.py`, `backend/tests/test_agent_place_search.py`, `backend/tests/test_agent_place_matching.py`, `backend/tests/test_agent_search_store.py`。

**Interfaces:** `SearchBudget(turn_deadline, *, clock=time.monotonic)` と `run(stage: str, key: str, call) -> object`、`close()`。stage=web/extract/geocodeで上限を共有。`PlaceSearchService(web, geocoder, searches, resolver, context, budget)`、`search(request: SearchInput) -> SearchResult`。`SearchInput.refresh: bool=False`。既存EvidenceResolverを継続し任意モデル座標は受け付けない。

- [ ] **Step 1: RED用の統合テストを更新・追加する。** 旧Geoapifyの段階テストを新手順に置換し、権限・履歴のassertを維持。`test_web_to_mapbox_persists_partial_search`, `test_shared_stage_budgets_and_deadlines`, `test_refresh_reuse_and_latest_region`, `test_dedup_preserves_cotenant_stores`, `test_bounds_preserve_source_identity`。
  ```python
  self.assertEqual(result['pipelineVersion'], 'web-mapbox-v1')
  self.assertEqual([a['stage'] for a in history['attempts']], ['web','extract','geocode'])
  self.assertEqual(result['status'], 'partial')  # 一部の座標取得が失敗
  self.assertLessEqual(web_count, 3); self.assertLessEqual(extract_count, 3)
  self.assertLessEqual(geocode_count, 10); self.assertLessEqual(max_geocode_concurrency, 2)
  self.assertEqual(legacy_reuse['status'], 'needs_clarification')
  ```
  異なる出典IDの同店舗は1候補・sources統合、同住所の別店舗は2候補。大きい日本語出典を省略した事実が残り、残ったURL/名称は元値のまま。refresh時は保存済み一致でもWebへ進み、refresh+reuseはValidationError。
- [ ] **Step 2: REDを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_place_search.py` と `test_agent_search_store.py`。旧コンストラクタ/手順/サイズ制限でFAIL。
- [ ] **Step 3: サービスと保存を実装する。** Web→抽出→住所変換を呼び、Mapboxの失敗でもunlocatedCandidatesを保存する。countryは根拠付き住所からのみ得る。地域不明と候補競合を区別。shared tasksをdeepcopyしtoken検証で履歴を更新。geocodeの住所子記録は個々の完了ごとに保存し、取消時に未完了だけ終了させる。新旧pipelineVersion・有効地域・正規化した条件を再利用前に検証し新しい候補/引用IDへ付け替える。旧結果のreadだけは維持する。
- [ ] **Step 4: 期限・サイズを実装する。** `limits.py`にGlobal Constraintsの値を集約。budgetsは開始時予約、geocode同時2、stage別キー、同条件共有、最短残時間timeout。storeは候補8 KiB/結果40 KiB/検索256 KiB以内に原子的に縮小。sources・unlocatedCandidatesにも識別情報を切らない規則を適用し、要約/履歴でも引用IDとURLの対応を維持。
- [ ] **Step 5: GREENを確認する。** `test_agent_place_search.py`、`test_agent_place_matching.py`、`test_agent_search_store.py` 全件成功。fake clockで85秒/turn終了10秒前、並列上限、取消後の遅延書込拒否・会話削除を検証。
- [ ] **Step 6: コミットする。** `git commit -m "feat: orchestrate web place discovery with durable search budgets"`。

### Task 5: Agent/API 接続と Geoapify 依存の除去

**Files:** Modify `backend/agent/runtime.py`, `backend/api/agent.py`, `backend/db/agent_store.py`, `backend/db/agent_search_store.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_agent_api.py`, `backend/tests/test_agent_trajectory.py`, `backend/tests/test_environment.py`, `backend/tests/test_map_config.py`, `backend/README.md`, `backend/API.md`; Remove `backend/agent/places.py`, `backend/tests/test_agent_place_provider.py`, `backend/tests/test_agent_places.py`（Task 2/3へ必要ケースを移行後）。

**Interfaces:** 既存ツール名を維持、search_placeにrefresh追加。Runner resultは `sources: list[Source]` と `searchIds: list[str]` を返す。引用は実検索/同会話履歴ツールの結果からサーバーで集約し、本文の `[source:<id>]` 形式に対応。`configuration()`の `placesAvailable` はOpenAI・モデル・専用Mapbox設定を判定し、`placesMissing`と`placesMessage`を追加。通常のavailable判定とは独立。

- [ ] **Step 1: 失敗テストを追加する。** `test_search_sources_without_proposal_survive_reload`, `test_web_search_to_approval_and_thread_deletion`, `test_search_configuration_is_independent`, `test_long_turn_keeps_lease_and_stale_retries_are_fenced`。
  ```python
  self.assertEqual(sent['message']['sources'], loaded['messages'][-1]['sources'])
  self.assertEqual(saved_place['geocoding']['provider'], 'mapbox')
  self.assertEqual(status['placesMissing'], ['MAPBOX_GEOCODING_ACCESS_TOKEN'])
  self.assertEqual(TURN_SECONDS, 120); self.assertEqual(TURN_LEASE_SECONDS, 130)
  self.assertEqual(geoapify_requests, [])
  ```
  80秒経過でも有効、130秒超で失効、古いtokenの完了拒否をfake clockで確認。候補IDにunlocatedのIDを指定したら400、旧提案は従来どおり承認できることも確認。
- [ ] **Step 2: REDを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_runtime.py` と `test_agent_api.py`。未接続/メタデータ欠落/旧期限でFAIL。
- [ ] **Step 3: 接続を実装する。** runtimeのprovider構築・cleanup・検索説明を置換。モデル側ネットワークtimeoutにもturn残時間を適用、外側API120秒とリース130秒を定数参照に統一。検索は地域矛盾を質問し、partial/unlocatedを説明する。モデル出力の任意リンクをsourcesへ昇格させない。全クライアントはfinallyで終了する。
- [ ] **Step 4: Geoapify依存を除去し説明を更新する。** provider例外importをTask 2へ移す。古い同期関数の参照ゼロを確認してファイルを削除。旧provider単体テストの通信・日本語・timeout・サイズ・エラーassertを新providerテストへ移行してから削除する。環境テストは新変数、秘密非公開のテストは両方の新キーを対象にする。README/APIへ専用トークン・永久保存資格・検索モデル・引用属性・期限を記載。過去の仕様/検証資料は書換えない。
- [ ] **Step 5: GREENと全バックエンドを確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests`。製品コードを `rg 'GEOAPIFY_API_KEY|api\.geoapify|GeoapifyProvider' backend --glob '!tests/**'` で調べ、実行時依存がないことを確認する。旧データ説明などの残存と通信コードを区別。
- [ ] **Step 6: コミットする。** `git commit -m "feat: switch agent place tools from Geoapify to web and Mapbox"`。

### Task 6: 出典・未確認地点を会話と軌跡に表示

**Files:** Create `front/src/PlaceSources.jsx`, `front/src/PlaceSources.test.jsx`; Modify `front/src/AgentChat.jsx`, `front/src/AgentPlaces.jsx`, `front/src/Trajectory.jsx`, `front/src/useAgentChat.js`（任意属性が失われる場合のみ）, `front/src/AgentPlaces.test.jsx`, `front/src/AgentChat.test.jsx`, `front/src/Trajectory.test.jsx`, `front/styles.css`（出典の折返しとフォーカス表示）。

**Interfaces:** `<PlaceSources sources={Source[]} geocoding={object|undefined} sourceUrl={legacyURL} attribution={legacyText}/>` と `renderCitedText(text: string, sources: Source[]) -> ReactNode` を同ファイルで提供。既存sourcesなし表示はsourceUrlへfallback。新形式はメッセージ/候補に属する出典だけを解決。

- [ ] **Step 1: UI指針を読む。** 対象はin-product。`ui-ux-pro-max`、`DESIGN.md`、`design-system/household-budget-app/MASTER.md`を読み、既存の会話レイアウト・文字サイズ・カード外観を維持する。ダッシュボード専用の階層はこの画面へ流用しない。
- [ ] **Step 2: 失敗テストを追加する。** `unknown_citation_stays_plain_text`、`unlocated_store_cannot_be_selected`、`sources_survive_message_reload`、`trajectory_shows_store_and_coordinate_evidence`。
  ```javascript
  expect(screen.getByRole('link', {name: /店舗情報/})).toHaveAttribute('href', source.url);
  expect(screen.getByText('位置未確認')).toBeVisible();
  expect(within(unlocatedCard).queryByRole('radio')).toBeNull();
  expect(screen.queryByRole('link', {name: 'source:unknown'})).toBeNull();
  expect(screen.getByText(/補間/)).toBeVisible();
  ```
  長い日本語出典、javascriptリンク、ユーザー発言内の引用風文字、保存済みの旧出典、失敗→再送→再読込を含める。
- [ ] **Step 3: REDを確認する。** `npm --prefix front test -- src/PlaceSources.test.jsx src/AgentPlaces.test.jsx src/AgentChat.test.jsx src/Trajectory.test.jsx`。新表示未実装でFAIL。
- [ ] **Step 4: 表示を実装する。** Reactのtext/anchorだけで引用を描画し、未知IDをリンクにしない。店舗出典と座標の帰属を別ラベルにする。未確認候補は理由と手動入力案内を表示し、radioを付けない。設定不足はplacesMessageを表示する。キーボードfocus、外部リンクの新タブ案内、折返し、選択中/処理中のdisabledを維持。
- [ ] **Step 5: GREENを確認する。** Step 3、`npm --prefix front test`、`npm --prefix front run build`。生成済みdistをコミット対象へ混ぜない。
- [ ] **Step 6: コミットする。** `git commit -m "feat: show cited store evidence and unresolved locations"`。

### Task 7: 移行の通し検証・実API・最終レビュー

**Files:** Modify `backend/tests/agent_browser_server.py`, `front/tests/e2e/app.spec.cjs`; Create `docs/verification/2026-10-03-web-place-search.md`。一時スクリプトはこの計画専用 `.superpowers/sdd/2026-10-03-web-place-search/` のみ。

**Interfaces:** 既存 `front/playwright.agent-search.config.cjs` を利用しport8767、一時DB、`KAKEI_TEST_PYTHON`でmainのPython環境を指定。稼働アプリの8765と実DBへ書き込まない。

- [ ] **Step 1: ブラウザの通し回帰を追加する。** fixtureに出典付き候補と未確認住所を追加し、Web候補→選択→保存→軌跡の出典、変更案なし応答→再読込の引用、旧候補の承認をテストする。`expect(link).toHaveAttribute('href', fixtureSource.url)`、未確認候補の選択不可、偽ID400をassertする。
- [ ] **Step 2: 新規ブラウザテストを実行する。** `KAKEI_TEST_PYTHON=/Users/spco/Kakei/backend/.venv/bin/python KAKEI_E2E_ARTIFACT_DIR=../.superpowers/sdd/2026-10-03-web-place-search/screenshots npm --prefix front run test:e2e -- --config=playwright.agent-search.config.cjs tests/e2e/app.spec.cjs`。新しいfixtureで未実装が判明した場合だけ失敗を再現し、担当Taskの範囲で修正する。
- [ ] **Step 3: 画面を確認する。** desktop1440px・phone375pxで候補/引用/未確認/手動入力を撮影して読む。横スクロール、入力欄に隠れる情報、リンクとradioの操作競合がない。UI未変更のダッシュボードを再設計しない。ブラウザが使えなければ構造確認と未確認事項を明示する。
- [ ] **Step 4: 実APIを限定検証する。** `.env`を表示せず必要キーの存在だけ確認。OpenAI＋Mapboxが利用可能なら新サービスと一時DBで対象店舗を調査し、Web調査最大3回・Mapbox最大5住所を厳守。Web内蔵call/usage、モデル、取得時刻、住所一致、座標精度を記録。設定不足・権限不足・住所未確定を成功と記さない。追加課金設定を勝手に変更しない。
- [ ] **Step 5: 全体を検証する。** `backend/.venv/bin/python -m unittest discover -s backend/tests`、`npm --prefix front test`、`npm --prefix front run build`、Step 2のブラウザテスト、`git diff --check`。件数・実検索と固定テストの区別・残る制限を検証文書へ保存する。
- [ ] **Step 6: 検証記録をコミットする。** `git commit -m "test: verify web place search migration and approval flow"`。
- [ ] **Step 7: 独立レビューを1回行う。** native実行スキルに従い全変更とReview Focusをレビューし、重要指摘をRED→GREENで修正して関連テストと全体を再実行。軽微な保留を記録し、mainへの統合方法を利用者の指示に合わせる。

## 計画の自己レビュー

- 仕様§1〜4 → Tasks 2・4・5、§5 → Task 3、§6 → Tasks 1・4、§7 → Tasks 4・5、§8 → Tasks 1・5・6、§9 → Task 7に対応。
- 120/130秒はRunner/API/DBを同一定数で揃える。storeサイズ更新とunlocatedの扱いをTask 4へ集約し、引用の保存と再読込はTask 1からTask 5/6へ同じ属性を渡す。
- WebPlaceには座標なし、GeocodeResultに座標、選択候補だけが地点作成を認可できる。旧履歴の閲覧と新検索での再利用禁止を分けた。
- Review Focusの5件を担当タスクの回帰へ追加済み。計画レビュー前の製品コード変更なし。
