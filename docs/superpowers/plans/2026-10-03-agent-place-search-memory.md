# Agent Place Search and Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 店舗名の検索失敗から地域を根拠に再検索し、次の会話で実際の検索履歴を説明できるようにする。

**Architecture:** Geoapify 接続、検索条件・候補の照合、段階的検索、SQLite の検索記録を分離する。単一 agent が検索処理と履歴読み取りを呼び、候補は既存の変更案・選択・承認へ渡す。検索記録はモデルの最終応答や変更案の作成に依存せず保存する。

**Tech Stack:** Python、FastAPI、LangChain、OpenAI、httpx、SQLite、unittest。既存の仮想環境と依存を使う。

**Spec:** `docs/superpowers/specs/2026-10-03-agent-place-search-memory-design.md`（2026-10-03 承認済み）

## Global Constraints

- 応答は日本語とし、地域は東京や日本に固定しない。取引・軌跡への反映は既存の確認・承認を経る。
- 公開 HTTP API の既存必須フィールドは変更しない。検索履歴の専用画面・専用 HTTP エンドポイントは今回追加しない。新しい依存パッケージを前提にしない。
- 店舗名・地域名などは各200文字以内。国コードは ISO 3166-1 alpha-2 として検証する。
- Geocoding の各応答は最大5件、Places は最大20件を取得し、提示候補は重複排除・照合後に最大5件とする。
- 外部リクエストは検索1回につき最大4回、利用者の発言1回につき合計8回。最初の地点検索開始から25秒と、既存の発言全体60秒の期限の5秒前のうち早い方を検索期限にする。個々の通信は最大5秒か残り時間の短い方。期限後の新規リクエストは発行しない。モデルのツール呼び出し上限8回は継続する。
- 各応答の読み取り上限は64 KiB。生レスポンスやキー付きURLをログに残さない。
- 候補1件の正規化データは最大2 KiB、検索1件のJSON総量は最大256 KiB。省略件数と `truncated` を記録する。
- 直近20件の会話文に加えて、同じ会話の直近3検索の要約を最大8 KiBでモデルへ渡す。履歴ツールは既定5検索、最大10検索、32 KiB。
- 地域の曖昧さ、別支店、通信失敗を「対象店舗が存在しない」と説明しない。モデルが店舗座標を作らない。
- 実DBの取引・会話をテストで変更しない。履歴は会話削除まで保持し、保存済み取引・軌跡は会話削除で消さない。

## Review Focus

- 検索中に会話を削除した場合、遅延応答が履歴や会話を復活させない（Task 1、5）。
- 同じ検索を異なる仮地点IDで同時に要求した場合、通信を共有しても選択候補が別の仮地点へ混ざらない（Task 4）。
- 同時刻の検索記録とサイズの大きい日本語候補でも、ページングが停止せず、UTF-8のバイト上限を守る（Task 1、5）。
- 高い confidence を持つ同名別支店や、名称変更・住所欠落の候補を自動確定しない（Task 3）。
- 古い発言の東京指定と今回の福岡指定が混在する場合、過去の推測で現在の地域を上書きせず、矛盾を確認できる（Task 3、5）。

---

## 実行方法・依存関係

以前の利用者指定 **native** を引き継ぐ。計画レビュー承認後に `superpowers:executing-plans` を用い、必要な作業用worktreeの作成は実行段階で行う。実装者が Task 1 → 2 → 3 → 4 → 5 → 6 を順に実行する。各タスクの最後で関連テストと差分を確認し、コミットする。

コマンドは作業リポジトリのルートで実行する。`backend/.venv/bin/python` は既存の依存入り環境を指す。worktree内に環境がない場合は `/Users/spco/Kakei/backend/.venv/bin/python` を使い、テスト対象は必ず作業worktreeの `backend/tests` とする。

## ファイル構成と共有データ契約

| ファイル | 役割 |
| --- | --- |
| 新規 `backend/agent/place_contracts.py` | 入出力の TypedDict、検索状態、地域・試行・ページの型 |
| 変更 `backend/db/schema.py`、新規 `backend/db/agent_search_store.py` | テーブル追加、処理トークン検証、試行保存、履歴・要約 |
| 変更 `backend/agent/places.py` | 非同期の Geocoding / Places 接続と応答正規化 |
| 新規 `backend/agent/place_matching.py` | 入力根拠の検証、地域・名称の照合、順位・重複排除 |
| 新規 `backend/agent/place_search.py` | 手順の実行、共通予算、同一リクエスト共有、履歴再利用 |
| 変更 `backend/agent/runtime.py`、`backend/api/agent.py`、`backend/db/agent_store.py` | ツール登録、履歴文脈、処理権限・終了処理、変更案への接続 |
| 新規 `backend/tests/agent_search_fixtures.py` | 一時DBの会話・有効な発言処理と固定の店舗・駅の検証データ |
| 新規テスト4本、既存agentテスト | 各層と実際の提案・承認までの検証。詳細は各タスク |

共有辞書は `place_contracts.py` で定義し、内部はsnake_case、既存の候補・応答はcamelCaseを維持する。

- `TurnContext = {thread_id, client_message_id, run_token}`。APIが作る内部値。モデル・履歴応答に公開しない。
- `SearchInput = {query, place_id, brand?, branch?, locality?, landmark?, country_code?, evidence?: list[Evidence], reuse_search_id?}`。
- `Evidence = {field, source, source_id, value}`。`source` は `user_message / transaction / saved_place / search`。引用値と対象フィールドはサーバーが実データで検証する。
- `Candidate` は仕様書§5の既存候補属性と任意の `matchReasons, searchId`。`ProviderPlace` はそれに構造化住所、カテゴリ、結果種別、境界ID、confidenceを加えた内部値。不正な行は `validationErrors` を持ち、座標をnullにできる。Task 3が理由付きで除外し、提示用 `Candidate` には有効な座標のみを許す。表示名・住所の欠落を検索語で埋めない。
- `Region = {kind: point|boundary, coordinates?, provider_id?, country_code?, city?, district?, source_id}`。`point` は駅・住所・保存済み地点、`boundary` は行政区域。市の中心点を店舗位置にしない。
- `Attempt = {id, stage, params, startedAt, finishedAt, status, candidates, excluded, errorCode, truncated}`。`params` にキー・ヘッダーは含めない。候補除外の要素は `{candidate, reasons}`。
- `SearchResult = {searchId, placeId, query, candidates, status, error, unresolved, truncated, reusedFrom?}`。`error` は既存カードに渡せる文字列またはnull。`status` は仕様書§6の7終了状態。
- `HistoryRecord = {searchId, createdAt, finishedAt, input, attempts, result, status, source}`。旧提案は `searchId=null, source=legacy_proposal` とし、`proposalId, legacyCursor` を追加する。
- `HistoryPage = {records, nextBeforeId, hasMore, truncated}`。新形式のカーソルは検索UUID、旧提案は `legacy:<proposal UUID>:<group index>`。型・所属を検証し、文字列をSQLへ埋め込まない。

## Task 1: 有効な発言処理に紐づく永続検索履歴

**Files:** Create `backend/agent/place_contracts.py`, `backend/db/agent_search_store.py`, `backend/tests/agent_search_fixtures.py`, `backend/tests/test_agent_search_store.py`; Modify `backend/db/schema.py`, `backend/db/agent_store.py`.

**Interfaces:**

- `AgentSearchStore(db_path: Path)`。
- `start(context: TurnContext, request: SearchInput) -> str` は処理トークンを検証し、DBトランザクション内でsequenceを割り当てて検索IDを返す。
- `record_attempt(context: TurnContext, search_id: str, attempt: Attempt) -> None` は試行IDで開始・終了を更新する。`finish(context, search_id, result: SearchResult) -> None` は終了結果を保存する。
- `get(thread_id: str, search_id: str) -> HistoryRecord`、`history(thread_id: str, *, search_id: str | None = None, before_id: str | None = None, limit: int = 5) -> HistoryPage`。
- `summary(thread_id: str) -> dict` は3件・8 KiBの要約と省略情報を返す。
- `cancel_searches(connection, context: TurnContext, *, now: float) -> None`、`recover_stale_turns(connection, *, now: float) -> None` は呼出側のトランザクションで動く。
- テスト補助 `active_turn(path: Path, text: str = '軌跡を作成') -> tuple[Store, AgentStore, TurnContext]` を提供する。

- [ ] **Step 1: 失敗する履歴テストを書く。** `test_search_survives_no_proposal_and_model_failure`、`test_old_token_cannot_overwrite_retry`、`test_history_pagination_and_utf8_bounds`、`test_delete_during_search_does_not_resurrect` を追加する。主要な期待値:

```python
self.assertEqual(reopened.get(thread_id, search_id)['result']['status'], 'empty')
self.assertEqual(old_attempt['status'], 'cancelled')
with self.assertRaises(TrajectoryConflict):
    searches.finish(old_context, search_id, result)
self.assertLessEqual(len(json.dumps(page, ensure_ascii=False).encode()), 32768)
self.assertEqual(len(ids_from_all_pages), len(set(ids_from_all_pages)))
```

 追加ケース: 同時刻の記録、候補2 KiB・全体256 KiB、会話外のID/カーソル拒否、旧テーブルからの移行、旧提案の最終候補のみ参照、正常応答再送時の履歴重複なし、業務 `sourceVersion` 不変。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_search_store.py' -v`。新モジュール未実装による失敗を確認する。
- [ ] **Step 3: 契約・テーブル・リポジトリを実装する。** 仕様書§7の列・制約・インデックスを追加し、SQLはパラメータ化する。発言への外部キーは置かず会話だけを参照し、既存 `INSERT OR REPLACE agent_turns` による履歴消失を防ぐ。`start/record_attempt/finish` はDB上の有効トークンを同一トランザクションで検証する。
  履歴は `(created_at DESC, id DESC)` で取得する。32 KiBを超える単独記録は候補を切り詰め、少なくともID・状態・条件を返し、次の記録へ進める。`truncated` と `hasMore` を区別する。新形式がない会話のみ旧提案を読み、DBへの擬似履歴挿入はしない。
- [ ] **Step 4: 発言の終了・回収を接続する。** `AgentStore.fail_turn` と `begin_turn` に同一トークンの中断処理を入れる。`AgentStore.__init__` と `begin_turn` で70秒以上古い処理を回収する。終了済み検索はそのまま残す。DB接続を入れ子にせず、前記connection関数を使う。
- [ ] **Step 5: GREEN を確認する。** Step 2 と `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_store.py' -v` を実行し、全件成功を確認する。
- [ ] **Step 6: コミットする。** 上記Filesのみを追加し、`git commit -m "feat: persist agent place search history"`。

## Task 2: キャンセル可能な Geoapify 接続

**Files:** Modify `backend/agent/places.py`, `backend/tests/test_agent_places.py`; Create `backend/tests/test_agent_place_provider.py`.

**Interfaces:**

- `GeoapifyProvider(client: httpx.AsyncClient | None = None)` は非同期context managerで、内部生成したクライアントだけをcloseする。
- `async geocode(self, query: str, *, country_code: str | None = None, region: Region | None = None, timeout: float) -> list[ProviderPlace]`。
- `async nearby(self, name: str, *, category: str, region: Region, timeout: float) -> list[ProviderPlace]`。
- `PlaceProviderError(code: str, *, stop_turn: bool = False)`。code は `unavailable/auth/rate_limited/timeout/network/invalid_response`。APIキーを含む元例外を応答に連結しない。
- 既存の同期 `search_places(query, *, bias=None, client=None)` は互換性のため残し、共通の応答正規化を使う。新検索経路では非同期の2メソッドを使う。

- [ ] **Step 1: 失敗するプロバイダーテストを書く。** `httpx.MockTransport` で `test_japanese_geocoding_and_scoped_places`、`test_partial_stream_timeout_and_cancellation`、`test_malformed_and_oversized_payload` を追加する。

```python
self.assertEqual(request.url.params['lang'], 'ja')
self.assertEqual(request.url.params['limit'], '20')  # nearby
self.assertEqual(request.url.params['filter'], 'circle:130.4,33.59,1000')
self.assertNotIn('secret', json.dumps(normalized, ensure_ascii=False))
self.assertEqual(error.code, 'rate_limited')
self.assertTrue(error.stop_turn)
```

 ケース: Geocoding limit=5、Placesの境界ID、country未指定で日本固定なし、期限、64 KiB境界、HTTP200でJSON形状不正、NaN/無効座標、空結果、401/403/429/5xx、URLのqueryとuserinfo除去。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_place_provider.py' -v`。
- [ ] **Step 3: アダプターを実装する。** 固定のGeoapify URL、`follow_redirects=False`、非同期streamと全体を包む `asyncio.timeout(timeout)` を使う。Geocodingの `results` とPlacesのGeoJSON `features[].properties` を `ProviderPlace` へ変換する。座標欠落などの不正レコードも理由付きで観測できるようにし、正常な空結果にすり替えない。認証・429は追加呼出を止めるエラーとして返す。
- [ ] **Step 4: GREEN と互換性を確認する。** Step 2 と `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_places.py' -v` を実行する。
- [ ] **Step 5: コミットする。** `git commit -m "feat: add bounded async Geoapify place queries"`。

## Task 3: 根拠を検証した地域解決と候補照合

**Files:** Create `backend/agent/place_matching.py`, `backend/tests/test_agent_place_matching.py`; Modify `backend/agent/place_contracts.py`, `backend/tests/agent_search_fixtures.py`.

**Interfaces:**

- `EvidenceResolver(store: Store, searches: AgentSearchStore, thread_id: str, messages: list[dict])` と `resolve(request: SearchInput) -> dict`。戻り値は `{request, saved_places, region, clarification, category}`。`clarification` は状態・質問内容またはnull。
- `normalize_text(value: str) -> str`、`resolve_region(places: list[ProviderPlace], request: SearchInput) -> dict` は `{region, clarification}` を返す。
- `match_candidates(places: list[ProviderPlace], request: SearchInput, region: Region | None) -> dict` は `{candidates, excluded, exact_match}`。理由は安定したcodeと日本語説明。
- `short_query(request: SearchInput, region: Region) -> str`。都市・地区はプロバイダー由来の値で補う。

- [ ] **Step 1: 失敗する照合テストを書く。** `test_fukuoka_evidence_and_short_query`、`test_distinct_branches_never_collapse`、`test_current_region_conflict_is_explicit`、`test_missing_address_does_not_become_exact` を追加する。

```python
self.assertEqual(short_query(request, fukuoka_region), 'ドトール 福岡市 天神')
self.assertFalse(match['exact_match'])  # 名称がチェーン名だけ
self.assertIn('branch_unconfirmed', match['candidates'][0]['matchReasons'])
self.assertEqual(conflict['clarification']['status'], 'needs_clarification')
self.assertEqual(len(match['candidates']), 2)  # 同名・別ID・別支店
```

 ケース: 根拠IDと引用値の不一致、他会話の履歴、ブランドの正規化、空・201文字、不正国コード、東京候補の除外、海外店舗、曖昧な駅、高confidenceの別支店、異なる表記で同じproviderId、支店名が欠けた名称変更候補。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_place_matching.py' -v`。
- [ ] **Step 3: 根拠・照合を実装する。** 元の店舗名の部分文字列として抽出したブランド・支店・駅名を認め、地域の新情報はプロバイダー結果からのみ補う。NFKC・空白整理・casefoldを使い、支店名を消す一般的な置換は行わない。新しい地域指定と過去の根拠が矛盾すれば確認を返す。
  国・市・範囲の不一致と別支店は除外し、名称だけなら支店未確認として順位を下げる。駅・住所の中心と候補の距離は標準ライブラリの球面距離で計算する。境界検索結果の住所が不足する場合は「未確認」を残す。カテゴリは根拠ある業種語（例: コーヒーショップ/cafe/coffee）から許可済みGeoapifyカテゴリへ対応し、判断できなければnullとする。
- [ ] **Step 4: GREEN を確認する。** Step 2 を実行する。
- [ ] **Step 5: コミットする。** `git commit -m "feat: match place candidates against location evidence"`。

## Task 4: 段階的検索・共通予算・履歴再利用

**Files:** Create `backend/agent/place_search.py`, `backend/tests/test_agent_place_search.py`; Modify `backend/tests/agent_search_fixtures.py`.

**Interfaces:**

- `SearchBudget(turn_deadline: float, *, clock=time.monotonic)`。発言の全検索で一つだけ共有する。
- `PlaceSearchService(provider: GeoapifyProvider, searches: AgentSearchStore, resolver: EvidenceResolver, context: TurnContext, budget: SearchBudget)`。
- `async search(self, request: SearchInput) -> SearchResult`。各試行はTask 1のメソッドで開始・完了を保存する。
- 共有リクエストのキーはプロバイダー操作と正規化済み検索条件。`place_id` は含めない。ネットワーク結果を共有し、履歴・候補ID・提案先は検索呼出ごとに分ける。

- [ ] **Step 1: 失敗する検索テストを書く。** 正式語0件→駅解決→短い名称→周辺施設の固定応答を使い、`test_fukuoka_fallback_records_all_attempts` を追加する。さらに `test_parallel_budget_and_duplicate_requests`、`test_reuse_is_scoped_and_preserves_origin`、`test_cancel_preserves_finished_attempts` を追加する。

```python
self.assertEqual(stages, ['formal', 'region', 'short', 'nearby'])
self.assertLessEqual(calls_for_one_search, 4)
self.assertLessEqual(calls_for_turn, 8)
self.assertLessEqual(timeout_for_request, 5)
self.assertNotEqual(first['candidates'][0]['id'], second['candidates'][0]['id'])
self.assertEqual(first['placeId'], 'first-placeholder')
self.assertEqual(second['placeId'], 'second-placeholder')
```

 ケース: 完全一致で早期終了、地域不明・曖昧、カテゴリ不明でnearby省略、部分成功後429、25秒予算と発言55秒地点期限、同時リクエスト共有、再試行で新履歴、再利用の条件違い拒否、旧履歴再利用不可、サイズ省略。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_place_search.py' -v`。
- [ ] **Step 3: 検索状態機械を実装する。** Task 3で入力を検証し、Task 1で開始を保存してからTask 2を呼ぶ。仕様書§5の順序で、曖昧な地域なら止め、弱い候補を残して後段へ進む。候補の最終状態・除外理由を記録する。`empty` は全実行が正常、`partial` は省略・失敗を含む場合とする。
  リクエスト共有と予算はasync lockで保護する。通信の全体時間制限、HTTP認証/429による発言内停止を共有する。外側のキャンセルで実行中タスクを終了させてから中断保存し、遅延した子タスクを残さない。
- [ ] **Step 4: 履歴再利用を実装する。** `reuse_search_id` は同じ会話の終了結果だけを受け付ける。正規化した検索条件を比較し、仮地点ID・再利用ID・根拠の参照表現のみ比較から除く。地域・ブランド・支店などが変われば拒否する。元ID・日時を `reusedFrom` に入れ、新しい候補IDで保存する。外部呼出0回を保証する。
- [ ] **Step 5: GREEN を確認する。** Step 2 とTask 1〜3の関連テストを実行する。
- [ ] **Step 6: コミットする。** `git commit -m "feat: add staged place search with durable attempts"`。

## Task 5: Agent の検索ツール・会話記憶・API処理権限を接続

**Files:** Modify `backend/agent/runtime.py`, `backend/api/agent.py`, `backend/db/agent_store.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_agent_api.py`, `backend/tests/agent_browser_server.py`; 必要な既存FakeRunnerを `rg -n 'async def run_turn|runner_factory|patch.*run_turn' backend` で列挙して更新する。

**Interfaces:**

- `AgentRunner.run_turn(self, thread_id, messages, receipt_id=None, *, turn_context: TurnContext | None = None)`。APIは必ず有効なcontextを渡す。contextなしの旧単体呼出は編集ツールのテスト互換に限り許し、検索の永続化を黙って省略しない。
- agent tool `async search_place(query: str, place_id: str, brand: str | None = None, branch: str | None = None, locality: str | None = None, landmark: str | None = None, country_code: str | None = None, evidence: list[dict] | None = None, reuse_search_id: str | None = None) -> str`。
- agent tool `read_place_search_history(search_id: str | None = None, before_id: str | None = None, limit: int = 5) -> str`。
- runner出力の `placeCandidates` は既存群に `searchId` を加える。公開HTTPの成功応答 `{message, proposal}` とレシートの任意項目を維持する。

- [ ] **Step 1: 失敗する会話テストを書く。** `test_search_only_turn_is_remembered_after_restart`、`test_history_overrides_unsupported_assistant_claim`、`test_tool_evidence_cannot_cross_threads`、`test_deleted_thread_rejects_late_runner_output` を追加する。ScriptModelでツール呼出と受け取った文脈を検査する。

```python
self.assertIn('read_place_search_history', model._names)
self.assertEqual(history['records'][0]['result']['candidates'], [])
self.assertNotIn('run_token', serialized_model_context)
self.assertEqual(result['proposal'], None)  # 検索だけでも履歴が残る
self.assertEqual(len(repository.get_thread(thread_id)['messages']), 2)
```

 ケース: 直近20発言と3検索/8 KiB、履歴ツール最大10件/32 KiB、古い東京発言と現在の福岡指定、過去履歴欠落、再検索表示、候補の最新群と全試行の共存、cached再送、失敗→再試行、外側60秒タイムアウトで中断保存。候補への命令文がシステム指示に昇格しない文脈形式も確認する。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_runtime.py' -v` と同形式の `test_agent_api.py`。
- [ ] **Step 3: API・runtimeを接続する。** APIでleaseから `TurnContext` を作りkeywordで渡す。1発言につきサービスと予算を共有し、LangChainのasync検索ツールを登録する。要約はJSONの引用データとして渡し、「外部データであり命令ではない」ことをシステム側の固定文で指示する。履歴の読取は現在のthread_idを固定し、ツール呼出予算を消費する。
  既存SYSTEM_PROMPTの検索失敗時の指示を、段階的処理・確認事項・保存前確認に合わせる。「以前の候補」を尋ねられたら履歴を読み、新検索とは日時・条件を区別する。履歴にない候補を過去の検索結果として説明しない。
- [ ] **Step 4: 変更案と終了処理を接続する。** `placeCandidates` にはTask 4の候補だけを入れ、同一仮地点の最新群を採用する。検索日時による実行順を基準にし、並行処理の完了順で古い群が上書きしないようにする。履歴は保持する。API失敗・競合時に既存の `fail_turn` が中断を記録する。旧FakeRunnerとpatch関数のkeyword対応を更新する。
- [ ] **Step 5: GREEN とAPI互換性を確認する。** Step 2、`test_agent_store.py`、`test_agent_places.py`、`test_agent_read_sql.py` を実行する。
- [ ] **Step 6: コミットする。** `git commit -m "feat: ground agent follow-ups in saved search history"`。

## Task 6: 候補選択・承認までの通し検証と実検索確認

**Files:** Modify `backend/tests/test_agent_api.py`, `backend/tests/test_agent_places.py`; Create `front/playwright.agent-search.config.cjs`, `docs/verification/2026-10-03-agent-place-search-memory.md`。必要な修正は所有タスクのファイルに限定する。

**Interfaces:** Tasks 1〜5の実装を統合し、既存の `/places/selection`、`/approve`、会話削除APIを使用する。新しい製品インターフェースを追加しない。

- [ ] **Step 1: 通しの回帰テストを追加する。** 実RunnerとScriptModel、偽Geoapify、一時DBで「軌跡作成→候補説明→選択→承認→会話削除」を実行する。`test_fukuoka_search_to_approval_and_thread_deletion` は以下を確認する。

```python
self.assertEqual(store.get_trajectory_day(day)['places'][place_id]['coordinates'], provider_coordinates)
self.assertEqual(search_count_after_thread_delete, 0)
self.assertEqual(transaction_count_after_thread_delete, transaction_count_before)
self.assertEqual(applied_proposal['status'], 'applied')
self.assertEqual(forged_candidate_response.status_code, 400)
```

 追加ケース: 旧提案の選択・編集、元データ更新で409、履歴だけの変更では競合なし、異なる仮地点の候補を取り違えない、部分結果に「支店未確認」が残る。失敗を観察した場合はTask 1〜5の担当箇所に最小の修正を加える。
- [ ] **Step 2: バックエンド全体を検証する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -v`。全件成功を確認し、実行件数を検証記録へ残す。
- [ ] **Step 3: 隔離したブラウザ検証設定を追加する。** `front/playwright.agent-search.config.cjs` で既存設定を読み、`use.baseURL='http://127.0.0.1:8767'`、`webServer.url`も同じURL、`reuseExistingServer=false`、`cwd=__dirname` とする。webServerコマンドは環境変数 `KAKEI_TEST_PYTHON`（未指定なら `../backend/.venv/bin/python`）で `../backend/tests/agent_browser_server.py` を起動する。このfixtureは既に一時SQLiteを作る。既存の8765を使う設定で書き込みテストを実行しない。
- [ ] **Step 4: 既存画面との契約を検証する。** `npm --prefix front test`、`npm --prefix front run build`、`npm --prefix front run test:e2e -- --config=playwright.agent-search.config.cjs tests/e2e/app.spec.cjs`。worktreeでは `KAKEI_TEST_PYTHON` に既存仮想環境の絶対パスを設定する。buildの生成物は実装コミットに混ぜない。既存カード・会話読込・保存の回帰を確認する。ポート8767が使用中なら利用者のプロセスを勝手に終了せず、テスト専用環境を調整する。
- [ ] **Step 5: 実APIを読み取り確認する。** 追跡しない `.superpowers/` 配下の検証スクリプトから、ルート`.env`の既存Geoapifyキーを読み、正式店名・短い名称・駅周辺を合計8外部呼出以内で確認する。新サービスと一時DBを使い、キー付きURLや個人の取引全体を出力しない。ネットワーク承認が必要なら所定のエスカレーションを使う。
  取得した日時・条件・件数・地域・支店同定の限界を記録する。ライブで4件や特定支店の収録は要求しない。未実施・外部障害は明記し、偽応答によるテストをライブ成功と書かない。
- [ ] **Step 6: 検証結果と差分を確認してコミットする。** `git diff --check`、意図したファイルだけの変更、秘密情報なしを確認する。`git commit -m "test: verify agent search memory and approval flow"`。
- [ ] **Step 7: 全変更のレビューを行う。** nativeの実行スキルに従い、実装完了後に独立したレビューを一度行う。特にReview Focusの5項目、asyncキャンセル、トークン検証、候補選択境界を確認し、指摘を修正・該当テスト再実行する。mainへのマージや稼働アプリの再起動は、この新しい変更に対する利用者の指示に合わせる。

## 自己レビュー結果

- 仕様§4〜6: Task 2〜4、保存§7: Task 1、記憶§8: Task 1・5、互換性§9: Task 1・4〜6、完成条件§10: 全タスクとTask 6に対応。
- 型・関数の責務は上記契約を共有し、試行履歴の保存と提案への候補コピーを分離した。
- 検索範囲・予算・失敗記録・旧履歴・会話削除・再送と再試行のテストを計画に含めた。
- 外部APIの挙動やモデル文章を完全保証するテストは設けず、構造化入力・根拠・確定操作の境界を検証する。
- 本計画はレビュー待ち。製品コードの実装は開始していない。
