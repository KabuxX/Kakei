# Google Places Automatic Trajectory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 指定日の取引からGoogle Places API (New)で特定できた訪問だけを確認なしで保存し、除外した取引と理由を結果に表示する。

**Architecture:** 外部通信、店舗の特定、保存予定内容の準備、原子的な保存を分離する。Agentの軌跡作成経路は保留中の変更案を使わず、実行トークンを検証した完了処理で軌跡と応答を同時保存する。Google地点は永続的なPlace IDと期限付き座標キャッシュに分け、表示時に解決する。

**Tech Stack:** Python 3.14以上、既存のFastAPI・SQLite・httpx・LangChain、React 19・Vite・Vitest・Playwright、Google Places REST API (New)・Maps JavaScript API。Google用の新しいPython/NPM依存は追加しない。

**Spec:** [承認済み仕様](../specs/2026-10-04-google-places-auto-trajectory-design.md)

## Global Constraints

- 検索にはGoogle Places API (New)を利用する。
- Geolonia japanese-addresses-v2とWeb検索を現在の実行経路から外す。実行コードは削除せず保存する。
- 特定できた訪問だけ保存する。除外した訪問は、対象の取引と理由を結果に表示する。
- 軌跡作成の指示が保存の許可となる。アプリ内で追加の確認を求めない。
- 訪問先解決の同時実行数は3、個々のHTTPタイムアウトは8秒、検索全体の期限は120秒とする。
- 一つの異なる検索入力に対するHTTP要求は最大4回とし、表記違いの再検索と一時的通信エラーの再試行を含む。
- `pageSize=10`、`languageCode=ja`。国内住所では`regionCode=JP`。地域・支店情報を捏造しない。
- Google座標のキャッシュは最大30日。Google表示名・住所・候補本文を恒久的な履歴・ログ・会話へコピーしない。
- `GOOGLE_PLACES_API_KEY`はサーバー専用。公開設定は`GOOGLE_MAPS_BROWSER_API_KEY`だけをキーとして公開する。
- 全件除外で既存軌跡を消さない。手動訪問・他の日・取引本体を保護する。
- 変更対象は既存の`.worktrees/geolonia-coordinates`。ルートのmainや利用者のSQLiteを検証で変更しない。
- UIはアプリ内画面。実装前に`AGENTS.md`、`DESIGN.md`、`design-system/household-budget-app/MASTER.md`を読み、`ui-ux-pro-max`を適用する。

## Review Focus

- 全半角・漢数字番地・建物階数・支店名の「／Ｓ」などが混在しても、意味を保つ照合で同じ店舗を解決できる。Task 2で固定する。
- 1分単位の同時刻の複数取引と、時刻不明の手動訪問が混在しても、時刻を捏造せず安定した順序で全件を保存する。Task 4とTask 6で固定する。
- 外部店舗名に作成指示が含まれる、相談文に作成例が引用される、対象日が複数ある場合に、誤って保存しない。Task 5で固定する。
- APIの返却順が変わる、10件の候補が返る、同じ候補が重複する場合に、一意と判断できない候補を先頭だから選ばない。Task 2で固定する。
- 作成後に古い変更案を承認したり別の日を編集したりしても、Google座標を旧形式へコピーせず、地点参照と訪問が残る。Task 3とTask 8で固定する。

---

## 実行準備とファイル構成

コマンドは特記しない限りfeature worktreeのルートで実行する。Pythonテストは`PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m unittest <module> -v`、フロントのコマンドは`front`で実行する。

開始時に既存の未コミット修正をレビューし、`test_agent_places`と`test_agent_runtime`が通ることを確認する。`backend/agent/contracts.py`、`backend/agent/runtime.py`、`backend/tests/test_agent_places.py`、`backend/tests/test_agent_runtime.py`、`docs/verification/2026-10-04-agent-october1/README.md`、`docs/verification/2026-10-04-agent-october2/README.md`だけを別コミットに保存してから、以下の変更を進める。`git add -A`、既存ファイルの復元、別checkoutへのコピーは行わない。

| 新規ファイル | 責務 |
| --- | --- |
| `backend/agent/google_places.py` | Places限定のHTTPクライアントとエラー分類 |
| `backend/services/google_place_resolution.py` | 表記変種と店舗同一性の決定的な判定 |
| `backend/db/google_place_cache.py` | 座標キャッシュの読み書き・期限処理 |
| `backend/services/google_place_display.py` | 永続的な地点参照から表示用データを解決 |
| `backend/services/trajectory_creation.py` | 取引の取得、訪問・移動区間の統合、結果の組み立て |
| `backend/services/trajectory_intent.py` | 現在の発言から保存指示と一意な対象日を抽出 |
| `backend/agent/google_place_tools.py` | 保存しないGoogle検索と、旧検索履歴への明示的なアクセス |
| `backend/agent/legacy_place_tools.py` | 現在の旧検索登録・後処理を保存し、旧テストから明示的に利用 |
| `backend/api/google_places.py` | Place IDの表示情報を一時的に返すローカルAPI |
| `front/src/AgentTrajectoryResult.jsx` | 保存結果・登録済み・除外の表示 |
| `front/src/GooglePlaceResults.jsx` | 検索結果の一時的な表示と帰属 |
| `front/src/GoogleTrajectoryMap.jsx` | Google Mapsによる訪問・区間表示 |
| `front/src/lib/google-maps.js` | Maps JavaScript APIの単一ロードと再試行 |

各TaskのFilesに追加のテストと変更対象を示す。旧検索モジュール・旧Mapboxコンポーネントとその依存は残す。

## Task 1: Google Placesクライアント

**Files:** Create `backend/agent/google_places.py`, `backend/tests/google_places_fixtures.py`, `backend/tests/test_google_places.py`。Modify `backend/README.md`。

**Interfaces:** `GooglePlacesClient(*, client: httpx.AsyncClient | None = None, api_key: str | None = None)`は非同期context manager。`search_text(query: str, *, region_code: str | None = None) -> list[GoogleCandidate]`、`details(place_id: str) -> GoogleCandidate`。`GoogleCandidate`は`place_id, display_name, formatted_address, address_components, coordinates, types, maps_uri, attributions`を持つ一時的なdataclass。座標は`tuple[float, float] | None`。`GooglePlacesError`は`code, retry_after`を持ち、キーや応答本文を含めない。codeは`configuration/rate_limited/unavailable/invalid_response/not_found`で、401・403はconfiguration、429はrate_limited、5xx・通信・期限はunavailable、Detailsの404はnot_foundに分類する。

- [ ] **Step 1: 失敗するテストを書く。** `test_text_search_contract`は要求先・ヘッダー・基本FieldMask・`pageSize=10`・`languageCode=ja`を確認。`test_details_and_errors`はGET Details、401/403/429/5xx、8秒期限、不正JSON・NaN・座標範囲外・大きすぎる応答を確認。例のアサーション:
  ```python
  self.assertEqual(request.url.host, 'places.googleapis.com')
  self.assertEqual(body['pageSize'], 10)
  self.assertEqual(body['languageCode'], 'ja')
  self.assertNotIn('server-secret', str(error))
  ```
- [ ] **Step 2: REDを確認。** `PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m unittest test_google_places -v`。新規モジュール未実装でFAIL。
- [ ] **Step 3: クライアントを実装。** 固定Googleホストのみ、リダイレクト無効、最大512KiB。検索FieldMaskは仕様の8フィールド、Detailsは`id,location,displayName,formattedAddress,googleMapsUri,attributions`。クライアント自体は再試行しない。公式の[Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search)・[Details](https://developers.google.com/maps/documentation/places/web-service/place-details)を参照。
- [ ] **Step 4: GREENを確認。** Step 2のコマンドでPASS。`httpx.MockTransport`を使い、実ネットワークに接続しない。
- [ ] **Step 5: コミット。** Filesの4ファイルだけを追加し、`feat: add Google Places New client`。

## Task 2: 表記差を許容する店舗の特定

**Files:** Create `backend/services/google_place_resolution.py`, `backend/tests/test_google_place_resolution.py`。Modify `backend/tests/google_places_fixtures.py`。

**Interfaces:** Task 1のクライアントを使用。`VisitInput(transaction_id: str, label: str, address: str | None)`、`VisitResolution(transaction_id: str, provider_place_id: str | None, coordinates: tuple[float,float] | None, obtained_at: float | None, reason: str | None)`。`VisitResolver(client, *, deadline: float, clock=time.monotonic)`の`resolve(visit: VisitInput) -> VisitResolution`、`resolve_many(visits: list[VisitInput]) -> list[VisitResolution]`は非同期。同一入力の通信を共有しても取引ごとの結果を返す。

- [ ] **Step 1: 失敗するテストを書く。** `test_variants_preserve_branch_and_address`でセブン-イレブン千代田店と二番町8-8、ファミリーマート八重洲／Ｓ店の建物・地下階差を合成候補で検証。`test_ambiguous_and_address_only_are_excluded`、`test_reordered_full_page_and_duplicate_ids`、`test_four_requests_three_workers_and_deadline`で判定と制限を固定する。
  ```python
  self.assertEqual(resolved.provider_place_id, 'fixture-chiyoda')
  self.assertEqual(ambiguous.reason, 'ambiguous')
  self.assertLessEqual(len(requests_for_one_input), 4)
  self.assertLessEqual(max_in_flight, 3)
  self.assertEqual(unprocessed.reason, 'budget_exceeded')
  ```
- [ ] **Step 2: REDを確認。** `PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m unittest test_google_place_resolution -v`。
- [ ] **Step 3: Resolverを実装。** 正規化にはUnicode NFKC、空白・ハイフン・既知ブランド表記、丁目番地表記を使用。候補はブランド・支店または具体的住所の一致で絞り、異なるPlace IDの適合候補が複数なら除外。記録の支店・番地を保持し、住所点や駅中心点は採用しない。Task 1の分類済みエラーを仕様の除外コードへ変換する。全体120秒、HTTP最大4回、一時障害の再試行最大1回を実装。
- [ ] **Step 4: GREENを確認。** Step 2でPASS。時計・待機・通信は注入して120秒の実待機を避ける。
- [ ] **Step 5: コミット。** Filesの3ファイルだけを追加し、`feat: resolve visits with bounded Google Places search`。

## Task 3: 地点参照の移行と期限付き座標表示

**Files:** Create `backend/db/google_place_cache.py`, `backend/services/google_place_display.py`, `backend/tests/test_google_place_storage.py`。Modify `backend/db/schema.py`, `backend/db/trajectory_store.py`, `backend/db/store.py`, `backend/services/trajectory_validation.py`, `backend/services/trajectory_mutation.py`, `backend/services/agent_changes.py`, `backend/tests/test_trajectory_validation.py`。

**Interfaces:** 永続Google地点は`{name, address, sourceUrl: None, placeEvidence: 'google_places', provider: 'google', providerPlaceId}`。`name/address`は取引由来。Google地点の永続形に`coordinates`は含めない。既存`read_trajectory_day/timeline`は永続形を返す。`write_cached_coordinates(connection, place_id, coordinates, obtained_at)`、`read_cached_coordinates(connection, place_id, now) -> tuple | None`、`purge_expired_coordinates(connection, now) -> int`。`GooglePlaceDisplay(store, client).hydrate(timeline: dict, *, now: float) -> dict`は非同期で表示形だけに`coordinates`と`locationResolution: resolved/unavailable`を付ける。

- [ ] **Step 1: 失敗するテストを書く。** `test_legacy_migration_and_google_without_coordinates`、`test_expiry_and_failed_rehydration_keep_visit`、`test_cache_does_not_change_source_version`、`test_other_day_edit_and_old_proposal_keep_google_reference`。旧SQL fixtureからの移行、共有地点・孤立地点も対象にする。
  ```python
  self.assertIsNone(read_cached_coordinates(connection, 'fixture-place', obtained_at + 30*86400))
  self.assertNotIn('coordinates', durable_google_place)
  self.assertEqual(version_before_refresh, version_after_refresh)
  self.assertEqual(legacy_before, legacy_after)
  ```
- [ ] **Step 2: REDを確認。** `PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m unittest test_google_place_storage test_trajectory_validation -v`。
- [ ] **Step 3: 永続化と検証を実装。** `trajectory_places`にprovider・provider_place_idを追加し、Googleでは緯度経度をNULLにする。既存スキーマ移行は全軌跡テーブルを退避、子から削除、親から復元する既存方式で、同じSQLiteトランザクション内に収める。旧地点のJSON形と根拠は変えない。新規キャッシュ表の主キーはGoogle Place ID、地点全体の置換でキャッシュを消さない独立表とする。検証は両形式を区別し、キャッシュを`read_state`や変更案へ混入させない。
- [ ] **Step 4: 表示解決を実装。** キャッシュの期限を取得日時+30日で判定し、期限切れを削除してDetailsで再取得。失敗時は地点参照と訪問を返し、座標をnullにする。起動時の削除をStore初期化へ組み込む。アプリ生成の履歴・書き出しにキャッシュをコピーしない。
- [ ] **Step 5: GREENを確認。** Step 2に`test_trajectory_store test_trajectory_mutation test_agent_changes`を加えてPASS。Google地点を含む全体置換の往復と外部キーの整合も確認。期限切れの旧提案は既存どおり拒否し、Google地点を消さないことを確認する。
- [ ] **Step 6: コミット。** Filesだけを追加し、`feat: persist Google place references and expiring coordinates`。

## Task 4: 訪問の統合と原子的な自動保存

**Files:** Create `backend/services/trajectory_creation.py`, `backend/tests/test_trajectory_creation.py`。Modify `backend/db/agent_store.py`, `backend/services/trajectory_validation.py`, `backend/tests/test_agent_store.py`。

**Interfaces:** `PreparedCreation(date: str, source_version: str, timeline: dict, resolutions: list[VisitResolution], result: dict)`はサーバー内部専用dataclass。`TrajectoryCreationService(store, resolver).prepare(date: str) -> PreparedCreation`は非同期で書き込まない。`apply_creation(connection, prepared: PreparedCreation, *, now: float) -> dict`は呼び出し元のトランザクションに参加し外部通信しない。`AgentStore.complete_turn`が`result['preparedCreation']`を受け取り、確定した`trajectoryCreation`だけを保存・返信する。

`trajectoryCreation={date,status,counts:{saved,existing,excluded},saved:[],existing:[],excluded:[]}`。各リスト要素は`transactionId,label,time,timeEstimated`、saved/existingには`eventId`、excludedには`reason,message`を含む。状態は仕様の`created/partial/unchanged/failed`。外部由来の表示名・住所・座標をこの結果に入れない。

- [ ] **Step 1: 失敗するテストを書く。** `test_resolved_only_saved_without_proposal`、`test_all_excluded_preserves_day`、`test_retry_existing_and_manual_visits`、`test_same_minute_and_unknown_manual_order`、`test_atomic_reply_rollback_and_stale_token`。101件以上の取引が既存のcontext制限で落ちないことも確認。
  ```python
  self.assertIsNone(response['proposal'])
  self.assertEqual(response['trajectoryCreation']['counts'], {'saved': 2, 'existing': 0, 'excluded': 1})
  self.assertEqual(manual_event_before, manual_event_after)
  self.assertEqual(database_before_failed_commit, database_after_failed_commit)
  ```
- [ ] **Step 2: REDを確認。** `PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m unittest test_trajectory_creation test_agent_store -v`。
- [ ] **Step 3: 保存予定内容を実装。** 全取引を既存`read_state`の永続形から取得し、`trajectory_context`の100件制限を経由しない。収入・明示オンライン取引・情報不足を理由付きで除外する。IDは`uuid.uuid5(uuid.NAMESPACE_URL, 'kakei:visit:'+date+':'+transaction_id)`、地点IDは`google:`+Place ID。既存の同日・同取引の訪問は登録済みとし、再検索しない。同一Google地点の永続ラベルは最初の取引由来情報を保ち、個別の表示名は関連取引から得る。
- [ ] **Step 4: 時刻と接続を統合。** 新規訪問は取引時刻と推定フラグを引き継ぐ。同時刻では既存訪問の相対順を保ち、新規を取引ID順に続ける。時刻不明の既存訪問は相対順を保って既知時刻の後に置く。減少する時刻は不正、同時刻は許可する。隣接が変わらない脚を保持し、新規接続は`modeEvidence=inferred`、`modeHint`なし、実際の経路・手段は不明という説明を付ける。
- [ ] **Step 5: 完了処理へ原子的に接続。** 現行の`BEGIN IMMEDIATE`内で実行トークン・版・入力を検証し、キャッシュ、永続的軌跡、assistantメッセージ、ターン完了を保存する。新規ゼロなら軌跡を置換しない。確定結果はメッセージmetadataとターンresultへ置き、`get_thread`でも同じ結果を返す。再送には既存のcached完了結果を使用する。
- [ ] **Step 6: GREENを確認。** Step 2でPASS。失敗を軌跡書き込み後と会話挿入前に注入して、全変更が戻ることを確認。
- [ ] **Step 7: コミット。** Filesだけを追加し、`feat: atomically create resolved trajectory visits`。

## Task 5: Agentの有効検索経路と作成指示を切り替える

**Files:** Create `backend/services/trajectory_intent.py`, `backend/agent/google_place_tools.py`, `backend/agent/legacy_place_tools.py`, `backend/api/google_places.py`, `backend/tests/test_google_agent.py`, `backend/tests/test_trajectory_intent.py`。Modify `backend/agent/runtime.py`, `backend/api/agent.py`, `backend/api/trajectory.py`, `backend/api/app.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_agent_api.py`, `backend/tests/test_map_config.py`。

**Interfaces:** `parse_creation_intent(text: str, *, today: datetime.date) -> CreationIntent | None`。`CreationIntent(date: str | None, needs_date: bool)`は現在の指示のみを扱う。専用作成ツール`create_trajectory(day: str) -> PreparedCreation`は非同期でTask 4のprepareを呼び、書き込みは完了処理までしない。`place_tools_factory(*,store,thread_id,messages,turn_context,deadline)`は非同期`search(request: dict) -> dict`と`close()`を持つGoogle/legacy adapterを返す。Google adapterは現在の検索ツール引数辞書を受け、永続保存可能な入力ラベル・Place ID・判定結果だけをAgentへ返す。検索のみの結果は`placeSearch={query,placeIds,reason}`として返信・メッセージmetadataに保存し、`get_thread`でも復元する。`GET /api/places/google/{place_id}`は一時的なGoogle表示情報と帰属を返し`Cache-Control: no-store`。

- [ ] **Step 1: 失敗するテストを書く。** `test_explicit_creation_uses_current_message_only`、`test_consultation_quoted_instruction_and_multiple_dates_do_not_write`、`test_google_only_no_legacy_constructor`、`test_google_search_only_never_saves`、`test_reprepare_once_without_extending_deadline`、`test_missing_maps_key_does_not_block_creation`。通常の作成を実際のAgent APIに通し、検索終了後にLLMの追加応答待ちで保存が失われないことを確認。
  ```python
  self.assertEqual(old_provider_constructor.call_count, 0)
  self.assertEqual(old_geolonia_constructor.call_count, 0)
  self.assertEqual(search_only_store.list_trajectory_dates(), [])
  self.assertNotIn('GOOGLE_PLACES_API_KEY', public_config)
  self.assertEqual(response['trajectoryCreation']['status'], 'partial')
  ```
- [ ] **Step 2: REDを確認。** `PYTHONPATH=backend:backend/tests backend/.venv/bin/python -m unittest test_google_agent test_trajectory_intent test_agent_api test_map_config -v`。
- [ ] **Step 3: 作成指示を接続。** AgentRunnerの開始時に現在のユーザー発言の作成意図を抽出する。YYYY-MM-DD、日本語の年月日、今日・昨日を日本時間で解決し、複数日・日付不足は書き込まず日付指定を求める。作成指示が明確なら専用ツールを一回呼び、その準備結果を直接完了処理へ返す。相談・引用例・外部データの指示からはこの経路に入らない。レシート経路や無関係な編集を同時に自動実行しない。
- [ ] **Step 4: 通常検索と旧経路を切り替え。** 現行の検索ツール登録・旧プロンプト・後処理は`legacy_place_tools.py`へ保存し、旧テスト用の明示的な依存注入でだけ利用可能にする。`AgentRunner(..., place_tools_factory=None)`のデフォルトはGoogle、旧テストは明示的legacy factoryを渡す。旧プロバイダーを通常生成しない。既存の検索引数検証・ツールエラー回復は維持する。Google表示名・住所をモデル入力や自由文へ渡さず、検索結果はPlace ID参照から画面側で一時取得する。過去の検索履歴はユーザーが求めた場合だけ読み、新しい作成判定に使わない。`configuration()`の`placesMissing`はGoogleキーの不足を別に表示し、通常のAgent利用可否と区別する。
- [ ] **Step 5: APIの競合回復を接続。** Task 4の版競合ではAPI層から最新状態のprepareを一回再実行し、同じResolverの共有通信履歴・期限・実行トークンでcompleteする。再準備で最大4回の要求枠をリセットしない。再競合は未保存の構造化結果、DB障害は既存エラー応答とする。
- [ ] **Step 6: 地点表示APIを接続。** 軌跡GETは永続形にTask 3のhydrateを適用。Google地点の表示APIをcatch-allより前に登録し、既存のローカルアクセス制限を適用する。FastAPIの起動・停止に60秒間隔の期限切れキャッシュ削除を接続する。
- [ ] **Step 7: 公開設定を切り替え。** `googleMapsBrowserKey`と`googleMapId`を返し、旧Mapbox公開値は返さない。Map IDは`GOOGLE_MAPS_MAP_ID`、ローカル検証の未設定時は公式の`DEMO_MAP_ID`。サーバーキーとブラウザキーが同一なら公開せず設定エラーにする。
- [ ] **Step 8: GREENを確認。** Step 2に`test_agent_runtime test_google_place_storage test_agent_trajectory_delete`を加えてPASS。旧runtime検索テストは明示的legacy注入へ変更し、旧サービス単体テストは保存する。新しいデフォルトの挙動を旧期待に合わせて戻さない。
- [ ] **Step 9: コミット。** Filesだけを追加し、`feat: use Google Places and direct trajectory creation in agent`。

## Task 6: 保存結果・除外表示と座標欠落への対応

**Files:** Create `front/src/AgentTrajectoryResult.jsx`, `front/src/AgentTrajectoryResult.test.jsx`, `front/src/GooglePlaceResults.jsx`, `front/src/GooglePlaceResults.test.jsx`。Modify `front/src/AgentChat.jsx`, `front/src/useAgentChat.js`, `front/src/App.jsx`, `front/src/Trajectory.jsx`, `front/src/lib/trajectory-model.js`, `front/src/lib/trajectory-model.test.js`, `front/src/AgentChat.test.jsx`, `front/src/PlaceSources.jsx`, `front/styles.css`, `front/trajectory.css`。

**Interfaces:** `AgentTrajectoryResult({result, onOpenTrajectory})`はTask 4の`trajectoryCreation`を表示。`GooglePlaceResults({placeIds})`はTask 5のローカル表示APIを読み、コンポーネント状態だけに保持する。`Trajectory`へ任意の`requestedDate`を追加し、結果から開いた日を初期選択する。`buildTrajectoryDays`は永続参照が有効なら未解決座標を許容し、座標なし区間は`distanceKm:null`とする。

- [ ] **Step 1: 失敗するテストを書く。** `shows_saved_and_excluded_without_approval_controls`、`restores_result_after_thread_reload`、`opens_created_date_and_refreshes_trajectory`、`keeps_visits_with_unavailable_coordinates_and_equal_times`、`google_results_are_ephemeral_and_attributed`。
  ```javascript
  expect(screen.queryByRole('button', {name:'確認して保存'})).not.toBeInTheDocument();
  expect(screen.getByText(/1件除外/)).toBeInTheDocument();
  expect(day.events).toHaveLength(2);
  expect(day.segments[0].distanceKm).toBeNull();
  ```
- [ ] **Step 2: REDを確認。** `npm test -- src/AgentTrajectoryResult.test.jsx src/GooglePlaceResults.test.jsx src/AgentChat.test.jsx src/lib/trajectory-model.test.js`をfrontで実行。
- [ ] **Step 3: 結果と移動先を実装。** assistantメッセージの`trajectoryCreation`を専用コンポーネントで表示し、件数と日本語理由を常に見せる。`placeSearch`があればその`placeIds`をGooglePlaceResultsへ渡す。長い除外一覧はdetailsで展開する。保存された日へのリンクとAppの選択日を接続し、確定した新規保存結果で既存`onCommitted`の再読込を行う。既存の取引・削除用承認カードは維持する。返信は成功したまま、追加の一覧取得失敗だけを別表示する。
- [ ] **Step 4: 表示モデルとGoogle情報表示を実装。** 新参照形式・座標null・同時刻を扱い、旧形式の不正座標検証は残す。未解決の位置と距離不明を表示し、0kmが全区間確定の距離と誤読されないようにする。Googleの住所を取引由来住所の恒久表示へ混ぜず、Google表示情報には帰属を付ける。unmountや会話切替で遅い取得結果を破棄する。
- [ ] **Step 5: GREENを確認。** Step 2と`npm test -- src/Trajectory.test.jsx src/Trajectory.failure.test.jsx src/AgentProposal.delete.test.jsx`でPASS。
- [ ] **Step 6: コミット。** Filesだけを追加し、`feat: show automatic trajectory results and excluded visits`。

## Task 7: Google Mapsと利用説明

**Files:** Create `front/src/GoogleTrajectoryMap.jsx`, `front/src/GoogleTrajectoryMap.test.jsx`, `front/src/lib/google-maps.js`, `front/src/lib/google-maps.test.js`, `front/public/google-maps-usage.html`。Modify `front/src/Trajectory.jsx`, `front/trajectory.css`, `backend/README.md`, `front/README.md`。Keep `front/src/TrajectoryMap.jsx` unchanged。

**Interfaces:** `loadGoogleMaps({browserKey, mapId}) -> Promise<{Map, Polyline, AdvancedMarkerElement}>`。`GoogleTrajectoryMap({day, selectedEventId, onSelectEvent})`は旧マップと同じpropsを消費する。Map IDはTask 5の公開設定を使う。

- [ ] **Step 1: 失敗するテストを書く。** `loads_script_once_and_cleans_markers`、`shows_legacy_and_google_visits_on_google_map`、`missing_key_or_load_failure_keeps_timeline`、`stale_date_load_cannot_replace_current_map`、`keyboard_selects_visit`。旧Mapboxコンストラクタを呼んだら失敗するmockを付ける。
  ```javascript
  expect(document.querySelectorAll('script[data-kakei-google-maps]')).toHaveLength(1);
  expect(markerPositions).toContainEqual({lng:139.7, lat:35.6});
  expect(mapboxConstructor).not.toHaveBeenCalled();
  expect(screen.getByRole('button', {name:/再試行/})).toBeEnabled();
  ```
- [ ] **Step 2: REDを確認。** frontで`npm test -- src/GoogleTrajectoryMap.test.jsx src/lib/google-maps.test.js`。
- [ ] **Step 3: Googleマップを実装。** 公式の[ロード方法](https://developers.google.com/maps/documentation/javascript/load-maps-js-api)に従う単一script+callbackで、`loading=async`、`v=quarterly`、`language=ja`、`libraries=maps,marker`。AdvancedMarkerElement、Polyline、boundsで旧マップと同じ選択操作を実装。座標なし地点は描かず一覧に残す。マーカー・線・listenerの後始末を行い、帰属を覆わない。DEMO_MAP_IDはローカル検証用として説明する。
- [ ] **Step 4: 設定説明を実装。** `google-maps-usage.html`に店舗名・住所の送信先、Googleの利用規約・プライバシーポリシーへのリンク、アプリの利用・データ取扱説明を記載し、地図設定案内から常時開けるようにする。READMEにPlacesとMaps JSの有効化、課金、キーの用途別制限、任意Map IDを記載する。クラウド設定やキー作成は自動実行しない。
- [ ] **Step 5: GREENを確認。** Step 2と`npm test -- src/Trajectory.test.jsx src/Trajectory.failure.test.jsx`でPASS。地図キーを設定しない場合も保存・時系列が動くことを確認。
- [ ] **Step 6: コミット。** Filesだけを追加し、`feat: display trajectories with Google Maps`。

## Task 8: 統合確認と実APIの検証

**Files:** Create `front/tests/e2e/google-auto-trajectory.spec.cjs`, `docs/verification/2026-10-04-google-auto-trajectory/README.md`。Modify `backend/tests/agent_browser_server.py`。

**Interfaces:** BrowserRunnerのGoogle作成分岐は実際のTask 4のprepare/apply契約を使い、Googleクライアントだけを合成応答へ置換する。検証DBは従来どおり一時ディレクトリ、ポート8767。地図の外部スクリプトはテスト用Google Maps実装に置換し、キーや有料APIを必要としない。

- [ ] **Step 1: 失敗するブラウザテストを書く。** 2件特定・1件曖昧の作成指示を送り、確認ボタンなしでDBに2訪問が入ること、除外理由が見えることを確認。再送・会話再読み込み・別メッセージによる同日作成・全件除外・地図未設定・既存変更案とGoogle地点の混在を検証する。1440×900と390×844の両方で結果と訪問を読めることを確認。
- [ ] **Step 2: REDを確認。** frontで`npx playwright test --config=playwright.agent.config.cjs tests/e2e/google-auto-trajectory.spec.cjs`。fixture未対応でFAIL。
- [ ] **Step 3: fixtureを接続。** 対象分岐だけ追加し、旧Geolonia・Web・削除のfixtureを維持する。作成結果の件数を直接返す偽実装ではなく、一時SQLiteへの実保存を通す。
- [ ] **Step 4: 全体GREENを確認。** ルートで`backend/.venv/bin/python -m unittest discover -s backend/tests -v`。frontで`npm test`、`npm run build`、`npx playwright test --config=playwright.agent.config.cjs`。失敗の原因が新デフォルトか旧機能の破損かを調べ、期待値の削除だけで通さない。
- [ ] **Step 5: 実APIと画面を検証。** ルート`.env`からキーを秘密として読む一時スクリプトで、セブン-イレブン千代田店・二番町8-8と既存の代表店舗を検索する。保存検証はコピーした一時DBのみで行う。キーの値、利用者の取引ID、Google候補の生応答をリポジトリや恒久ログへ残さない。ブラウザキーがあればGoogle地図も両画面幅で確認し、なければ未設定時の表示を確認して制限を報告する。sandbox通信失敗時は所定のescalationで再試行する。
- [ ] **Step 6: 最終レビューとコミット。** `git diff --check`、全検証の結果、旧コード保存、有効経路のGoogle限定、キー漏出なしを記録。Filesだけを追加し、`test: verify Google automatic trajectory creation`。選択された実行方式のレビューを完了し、結果を報告する。mainへのmerge・push・利用者DBへの試験保存は行わない。

## 計画のセルフレビュー

仕様の検索、直接保存、除外、再実行、版競合、キャッシュ、表示、旧経路保存、設定説明、検証はTask 1〜8に割り当てた。永続形と表示形、準備結果と保存結果を別契約にして、Google取得情報の再保存と保存前の成功表示を防ぐ。Review Focusの5項目は担当Taskの具体的テストに含めた。

実行はTask順とする。特にTask 3の永続形を決めてからTask 4〜7を進める。今回の変更は一つの検索・保存フローとして依存しており、独立した別プロジェクトへ分割しない。

## 実行方式

この計画ではNativeを推奨する。永続形・保存結果・表示APIの契約が連続して変更されるため、このセッションで順に実装してから全体を独立レビューする方法が適する。

- Native: このセッションで実装し、最後に新しいレビュアーがブランチ全体を確認する。
- Subagent-driven: 各Taskを新しい実装担当とレビュアーが担当し、Taskごとの確認と最後の全体確認を行う。

計画のレビューと実行方式の選択を受けてから実装を開始する。
