# Geolonia Coordinate Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根拠のある日本の店舗住所から Geolonia を優先して詳細座標を取得し、柔軟に再試行した後、必要なら既存 Web 検索へ進む。

**Architecture:** Python が住所変種、候補採用、検索予算・履歴を管理する。専用 Node 補助プロセスが公式正規化ライブラリを呼び、限定したデータ取得と照合証跡を返す。住所対応座標の v2 証拠を既存の候補確認・保存・表示に接続する。

**Tech Stack:** Python asyncio / unittest、FastAPI、SQLite、Node.js ES modules / node:test、`@geolonia/normalize-japanese-addresses`、React / Vitest / Playwright。

**Spec:** [承認済み設計書](../specs/2026-10-04-geolonia-coordinate-search-design.md)。実行者は両方を読む。

## Global Constraints

- 住所の異なる表記を最大6種類試す。Geolonia に使う時間は検索1回につき合計30秒以内とする。
- `level == 8` かつ `point.level == 8`。番地・枝番・住居番号を落とした変種は作らない。
- 既存の検索期限145秒・発言期限180秒・最終応答の予約時間15秒を延長しない。
- 共通の残り検索時間から Web 用に少なくとも35秒を残す。プロセス数は発言内で最大2個。
- 同じ取得対象・範囲は初回と最大2回の再送。再送を使い切った取得障害は住所変種を替えて再送しない。
- 1応答8 MiB、検索1回の合計32 MiB。ホストは `japanese-addresses-v2.geoloniamaps.com` の HTTPS API に固定する。
- 既存必須ツール引数、Web の v1 証拠、保存済み地点の再利用、候補選択・承認動線を維持する。
- Node や依存がなくてもアプリは起動し、Geolonia の利用不能理由を記録して Web に進む。
- 地図確認・変更案承認前に店舗座標を保存しない。実ユーザーデータを検証で変更しない。

## Review Focus

1. 建物階数・部屋番号と住所の枝番が連続する入力で、別番地へ照合を緩めない（Task 2）。
2. ライブラリのキャッシュで通信が省略された次の照合でも、座標の元レコード・取得出典が残る（Task 3）。
3. 発言中止や異常な標準出力でも Node が終了・回収され、Web の停止状態に影響しない（Tasks 4–5）。
4. Geolonia 失敗後に Web が成功した結果と、位置未確認の粗い結果を混同しない（Task 5）。
5. 候補を切り替えたり保存後に再読込したりしても、確認状態と住所対応座標の種類が失われない（Tasks 1・6）。

---

## File structure and fixed contracts

新規モジュールは次の責務で分ける。既存の検索処理や表示を一括で移し替えない。

| File | Responsibility |
| --- | --- |
| `backend/services/geolonia_evidence.py` | v2 証拠の検証と出典参照の付け替え |
| `backend/agent/geolonia_addresses.py` | 日本住所の適格性・意味を保つ変種・照合結果の採用判定 |
| `backend/agent/geolonia_client.py` | Node の起動・通信・期限・終了と検索内共有セッション |
| `backend/agent/geolonia_candidates.py` | 検証済みの照合結果から店舗候補・補助情報を作る |
| `backend/geolonia/package.json`, `package-lock.json` | 補助モジュール専用の固定依存、test script |
| `backend/geolonia/fetch.mjs` | 固定ホスト、DNS/Range/サイズ/取得証跡の制限 |
| `backend/geolonia/normalize.mjs` | 公式正規化と元レコード・取得証跡の結合 |
| `backend/geolonia/worker.mjs` | JSONL 入出力、リクエスト検証、エラーコード化 |
| `backend/tests/geolonia_fixtures.py` | 合成された v2 候補、元レコード、粗い照合結果 |

v2 は既存共通フィールドと `addressMatch` のみを受理する。`version=2,status=address_matched,method=geolonia_address,precision=address` を固定する。`basis` と legacy `geocoding` は併存不可。

`addressMatch` のフィールドを `provider,libraryVersion,originalAddress,queryAddress,matchedAddress,strategies,level,pointLevel,components,record,fetches` に固定する。`provider='geolonia'`、`components={pref,city,town,addr}`、`record={kind,fields}`（kind は `rsdt` / `chiban`、fields は公式の採用レコード）。`fetches` は必要な取得証跡だけを最大4件、各 `{sourceId,url,retrievedAt,range,sha256,updatedAt}` とする。range は null または `{offset,length}`、updatedAt は null または UNIX 秒。sha256 は64桁の小文字16進。

Node 応答の `match` は `{pref,city,town,addr,other,level,point,record}`、point は null または `{lng,lat,level}`、record は粗い結果なら null。`proof` は `{fetches,observation}`。observation は既存構造 `{sourceId,kind,excerpt,coordinates}` の kind を `geolonia_address` にし、excerpt に components と採用レコードの JSON 抜粋を入れる。Node の一時 sourceId は Python で既存 sources に結合し、全参照を同時に付け替える。

未知フィールド、無効な数字、住所・レコード・観測座標の矛盾を拒否する。住所は500文字、既存 note は500文字、excerpt は2048文字、観測は1〜4件、sources は最大6件、候補単位は既存の8192バイト上限を守る。各取引の根拠住所は候補の originalAddress と結び、観測を欠いた候補は作らない。

公式の[package manifest](https://github.com/geolonia/normalize-japanese-addresses/blob/master/package.json)と[Node export](https://github.com/geolonia/normalize-japanese-addresses/blob/master/src/main-node.ts)を確認済み。実装では `3.1.3` を直接固定し、専用 lock を生成する。Node の実行基準は22以上とし、現在の環境（26系）でも確認する。依存は front に追加しない。公開された [metadata 型](https://github.com/geolonia/normalize-japanese-addresses/blob/master/src/types.ts)の採用レコードを使い、正規化アルゴリズムを Python で複製しない。

### Task 1: 住所対応座標の証拠契約と保存

**Files:** Create `backend/services/geolonia_evidence.py`, `backend/tests/geolonia_fixtures.py`; modify `backend/services/coordinate_evidence.py`; test `backend/tests/test_coordinate_evidence.py`, `backend/tests/test_agent_places.py`, `backend/tests/test_agent_search_store.py`。

**Interfaces:** `validate_geolonia_evidence(place: dict) -> None` と `rebind_geolonia_sources(evidence: dict, mapping: dict[str,str]) -> None` を提供する。既存 `validate_coordinate_evidence(place)` が v2 のみ委譲し、v1 は既存検証を維持する。後者は既存の deep-copy 済み evidence 内の fetches.sourceId を更新する。

fixture は `GEOLONIA_PLACE`（上記契約を満たす合成候補）、`DETAILED_RESULT`（8/8のNode結果）、`COARSE_RESULT`（8/3のNode結果）を提供する。検証テストの中心となる assertion:

```python
validate_coordinate_evidence(copy.deepcopy(GEOLONIA_PLACE))
bad = copy.deepcopy(GEOLONIA_PLACE)
bad['coordinateEvidence']['addressMatch']['pointLevel'] = 3
with self.assertRaises(ValidationError):
    validate_coordinate_evidence(bad)
```

- [ ] **Step 1: 契約と保存の失敗テストを書く。** `test_geolonia_requires_detailed_address_and_point` は level / pointLevel を3にした候補と欠落 record を拒否する。`test_geolonia_coordinates_and_record_are_bound` は観測・候補・レコードの座標違い、番地違い、不正 hash / Range / URL を拒否する。`test_geolonia_selection_roundtrip_preserves_evidence` は確認なしの選択を拒否し、確認・承認・再読込後の status/addressMatch を元と比較する。`test_geolonia_rebind_and_bounding_keep_atomic_evidence` は全 sourceId の更新、元候補不変、サイズ超過時の候補単位省略を確認する。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_coordinate_evidence.py' -v`。期待: 有効な v2 候補を既存検証が拒否する。
- [ ] **Step 3: v2 の検証と参照付け替えを実装する。** 上記契約を使い、rsdt/chiban の番号構成と座標を観測抜粋・components に照合する。metadata の追加情報すべてを保存せず採用 record だけ保持する。既存保存経路がそのまま使える限り、新しい DB 列は作らない。
- [ ] **Step 4: GREEN を確認する。** 上記 command、`-p 'test_agent_places.py'`、`-p 'test_agent_search_store.py'` を各実行。期待: v1・legacy・v2 と保存/再利用/サイズ検証が PASS。
- [ ] **Step 5: このタスクのファイルだけをコミットする。** message: `feat(agent): validate address-matched coordinate evidence`。

### Task 2: 住所の適格性・変種・一致判定

**Files:** Create `backend/agent/geolonia_addresses.py`, `backend/tests/test_geolonia_addresses.py`。

**Interfaces:** `eligible_address(address: str, country_code: str | None) -> bool`; `address_variants(address: str, *, grounded_prefixes: list[str]) -> list[dict]`（各 `{address,strategies}`、最大6件）; `match_reasons(original: str, variant: dict, match: dict) -> list[str]`（空なら採用可能）。入力住所・補完可能な prefix は Task 5 が根拠検証して渡す。

```python
variants = address_variants('東京都文京区本郷1-2-301', grounded_prefixes=[])
self.assertLessEqual(len(variants), 6)
self.assertEqual(len({v['address'] for v in variants}), len(variants))
self.assertTrue(all('301' in v['address'] for v in variants))
self.assertFalse(eligible_address('テスト珈琲店', None))
```

- [ ] **Step 1: 失敗テストを書く。** `test_variants_preserve_numbers_and_deduplicate` は郵便番号、日本、全半角、丁目/番/号、空白付き建物名を検証し、重複なし・最大6・番地不変を assert する。`test_floor_and_room_never_erase_address_suffix` は `1-2-301` と `1-2 建物名301号室` を区別する。`test_prefix_only_uses_grounded_administrative_values` は根拠なしで都道府県を追加しない。`test_detailed_match_checks_both_levels_and_other` は片方3、別番地、未解釈の住所数字、無効座標を拒否する。`test_non_japan_and_name_only_are_ineligible` は海外国コード・店名だけを省略するが、国コード省略の日本住所は扱える。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_geolonia_addresses.py' -v`。期待: 新規モジュールの不足による FAIL。
- [ ] **Step 3: 3関数を実装する。** 既存 `merchant_address.py` の NFKC・郵便番号・保守的な建物分離を再利用し、根拠の数字を削らない。公式正規化結果の components / addr と比較し、other に不明な住所番号が残る場合は採用しない。日本語店名を国の根拠にしない。
- [ ] **Step 4: GREEN を確認する。** 同 command。期待: すべて PASS、合成入力のみでネットワークなし。
- [ ] **Step 5: タスクのファイルをコミットする。** message: `feat(agent): retry grounded Japanese address variants`。

### Task 3: 公式ライブラリを呼ぶ Node 補助モジュール

**Files:** Create 上記 `backend/geolonia/` の5ファイル、`backend/geolonia/test/fetch.test.mjs`, `normalize.test.mjs`, `worker.test.mjs`, `fixtures.mjs`; modify `.gitignore`。

**Interfaces:** `createDatasetFetcher({fetchImpl,lookup,clock,signal}) -> {request,proofFor,close}`、`createNormalizer({fetcher}) -> {normalize(address): Promise<{match,proof}>}`。worker は JSONL `{id,address,timeoutMs,bytesRemaining}` を受け、`{id,status:'ok',match,proof,bytesRead}` または `{id,status:'error',errorCode,bytesRead}` を1行で返す。住所/モデル由来URLを受け取らない。stdout は JSONL だけ、stderr は固定エラー種別だけ。

同じ合成住所を同一 normalizer で2回照合した assertion:

```javascript
assert.equal(first.match.level, 8);
assert.equal(first.match.point.level, 8);
assert.deepEqual(second.proof.fetches, first.proof.fetches);
assert.deepEqual(second.match.record, first.match.record);
```

- [ ] **Step 1: 専用 package と失敗テストを用意する。** `npm install --prefix backend/geolonia --save-exact @geolonia/normalize-japanese-addresses@3.1.3` で lock を作る。test script は `node --test test/*.test.mjs`。`range_response_must_match_requested_bytes` は206/Content-Range、不一致、200の範囲無視を区別する。`caps_streamed_bytes_and_blocks_unsafe_targets` は8 MiB/32 MiB境界、固定外ホスト、非公開IP、リダイレクトを拒否する。`official_normalizer_returns_record_and_cached_proof` は実ライブラリに合成データを与え、rsdt/chiban の8/8と8/3、metadata record、キャッシュ後の取得証跡維持を assert する。`worker_emits_bounded_json_and_classified_errors` は長い入力/壊れたJSON/不正 timeout を扱う。
- [ ] **Step 2: RED を確認する。** `npm test --prefix backend/geolonia`。期待: 新規取得/正規化モジュールが不足して FAIL。
- [ ] **Step 3: fetch.mjs を実装する。** Node の DNS lookup と実接続を同じ検証済み公開IPに結ぶ。固定 API パス、identity encoding、上限付きストリーム読み取り、応答範囲検証、SHA-256/取得日時を管理する。ライブラリの再送を保持する status/ok/json/text を返し、非再送の制限エラーは安定した code で返す。
- [ ] **Step 4: normalize.mjs と worker.mjs を実装する。** pinned export の `requestHandlers.http` を fetcher.request に差し替える。normalize の metadata.rsdt/chiban から元レコードを取得し、必要な取得証跡だけ結合する。ライブラリキャッシュでも proof が消えないようセッション内に取得索引を保持する。再送上限到達後の同じ URL/Range は追加送信しない。各 JSONL 処理に AbortController の期限を付ける。
- [ ] **Step 5: GREEN と依存契約を確認する。** 同 command。期待:実ライブラリ export/合成HTTPで PASS、外部ネットワークなし。`backend/geolonia/node_modules/` を ignore し、MIT ライブラリ/CC BY データの出典情報を後の表示タスクへ渡す。
- [ ] **Step 6: タスクのファイルをコミットする。** message: `feat(agent): add bounded Geolonia normalization worker`。

### Task 4: Python のプロセス管理と候補生成

**Files:** Create `backend/agent/geolonia_client.py`, `backend/agent/geolonia_candidates.py`, `backend/tests/test_geolonia_client.py`, `backend/tests/test_geolonia_candidates.py`; modify `backend/agent/place_search.py` の SearchBudget のみ。

**Interfaces:** `GeoloniaClient(*, executable=None, worker_path=None, clock=time.monotonic)`; `client.session(key: str, budget: SearchBudget) -> GeoloniaSession`; `await client.close() -> None`。`await session.lookup(address: str, *, grounded_prefixes: list[str]) -> dict` は `{status,originalAddress,matchedVariant,match,proof,attempts,unresolved}` を返す。matchedVariant は null または Task 2 の `{address,strategies}`。status は `matched,coarse,empty,unavailable,failed,skipped`。attempts は入力/変換/時刻/結果/除外理由のリスト。`candidate_from_match(store: dict, result: dict) -> dict | None` が v2 店舗候補を返す。`SearchBudget.geolonia_time_remaining() -> float` は共通検索期限を開始し、残り検索時間から35秒を引いた利用可能秒を返す。

```python
self.assertIsNone(candidate_from_match(store_row, coarse_result))
candidate = candidate_from_match(store_row, matched_result)
self.assertEqual(candidate['coordinateEvidence']['version'], 2)
self.assertEqual(candidate['coordinateEvidence']['verification'], 'needs_confirmation')
```

- [ ] **Step 1: 失敗テストを書く。** fake process/clock で `test_no_node_or_dependency_is_unavailable`、`test_bad_stdout_size_or_id_is_failed`、`test_cancel_kills_and_reaps_worker`、`test_six_variants_and_thirty_seconds_are_shared`、`test_web_reserve_and_process_slots` を追加する。session の最大2並行、標準出力64 KiB・stderr4 KiB上限、30秒合算、待機中にも期限到達で終了、Web探索の経過は30秒へ加算しないことを assert する。`test_candidate_preserves_grounded_address_and_sources` は matched だけ生成し、coarse/異なる番地/不完全proofでは None。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_geolonia_*.py' -v`。期待: 新しい client/candidate 関数不足で FAIL。
- [ ] **Step 3: client/session を実装する。** asyncio.create_subprocess_exec を使い、lazy start、JSONL、共通 semaphore2、Task 2 の変種を管理する。最大6は session 全住所の合計、結果/例外を共有して同じ照合を再実行しない。時間計上に起動/枠待ち/照合/再送を含め、Web待機は除く。残り期限/30秒/32 MiBを Node へ伝える。設定/通信異常は分類して返し、cancel はプロセスを terminate・期限付き wait・必要なら kill・reap して再送出する。
- [ ] **Step 4: candidate_from_match と SearchBudget の利用可能時間を実装する。** 既存 sources に必要な dataset sources を加え、v2を作り Task 1 の検証を通す。地番/住居番号と入口未確認の note を残す。sources6/証拠サイズ制限内に収まらなければ候補を省略し理由を返す。
- [ ] **Step 5: GREEN を確認する。** 同 command と `-p 'test_agent_place_search.py'`。期待: fake processで PASS、既存 SearchBudget の回帰 PASS。
- [ ] **Step 6: タスクのファイルをコミットする。** message: `feat(agent): manage Geolonia search deadlines and provenance`。

### Task 5: Geolonia 優先の検索統合と履歴

**Files:** Modify `backend/agent/place_search.py`, `backend/agent/runtime.py`; test `backend/tests/test_agent_place_search.py`, `test_agent_runtime.py`, `test_agent_search_store.py`。`backend/db/agent_search_store.py` は必要な補助情報の保持だけ変更する。

**Interfaces:** `PlaceSearchService(..., budget, *, geolonia=None)` で注入し、runtime は GeoloniaClient を渡して finally で close する。PIPELINE_VERSION は `geolonia-web-coordinates-v2`。Task 4 session は既存 conditions(request) に基づく key で共有する。検索結果に任意 `geolonia: {status,unresolved,supplementalMatches}` を追加する。supplementalMatches は元/照合住所・2粒度・取得証跡・除外理由の最大6件で選択可能IDを持たない。

Geolonia が詳細な一致を返す fake を設定した検索の assertion:

```python
out = await self.service.search(grounded_request)
self.assertEqual(out['pipelineVersion'], 'geolonia-web-coordinates-v2')
self.assertEqual(out['candidates'][0]['coordinateEvidence']['status'], 'address_matched')
self.assertEqual(self.provider.calls, [])
```

- [ ] **Step 1: fake Geolonia の失敗テストを書く。** `test_grounded_address_uses_geolonia_before_web` はmatched時のWeb0回、`test_unknown_address_researches_store_then_geolonia` は住所発見後にWeb verifierより先行、`test_coarse_or_geolonia_failure_falls_back_to_web` は粗い候補なしとWeb成功を assert する。`test_geolonia_failure_does_not_stop_web_provider`、`test_supplemental_history_survives_and_is_not_selectable`、`test_saved_and_explicit_reuse_do_not_fetch`、`test_old_pipeline_reuse_requires_research`、`test_parallel_searches_share_geo_but_rebind_ids` を追加する。visit_date注意書き、海外skip、同一店舗/支店条件と曖昧な住所の未採用も固定応答で検証する。
- [ ] **Step 2: RED を確認する。** `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_agent_place_search.py' -v`。期待: Geolonia の順序/呼出し/履歴の不足で FAIL。
- [ ] **Step 3: 検索へ接続する。** 根拠解決とsaved/reuseの後に根拠住所のlookupを行い、得られた結果を店舗名・支店・地域条件と照合する。Web行の同一性検証を通した住所でもlookupを先行させ、失敗/粗い結果だけ既存verifierへ渡す。合成した店名をGeoloniaの正式店名として扱わない。全体6変種/30秒は新しい住所でもリセットしない。候補比較/visit_date/source再結合を共通finish経路で使う。
- [ ] **Step 4: runtime・履歴説明を接続する。** Agent指示にGeolonia優先/住所不明時のWeb住所発見/粗い結果の区別を追加し、Node不在をOpenAI設定不足へ加えない。各完了試行を既存record_attemptへ保存し、旧履歴読込と証拠単位のサイズ処理を保つ。キャンセル時は完了済み試行を維持し、遅延書込を既存トークン検証に通す。
- [ ] **Step 5: GREEN を確認する。** 上記command、`-p 'test_agent_runtime.py'`、`-p 'test_agent_search_store.py'`。期待:新順序・共有・履歴・既存Web検索すべて PASS。
- [ ] **Step 6: タスクのファイルをコミットする。** message: `feat(agent): prefer Geolonia before web coordinate lookup`。

### Task 6: 確認画面・保存後表示・運用説明

**Files:** Modify `front/src/CoordinateEvidence.jsx`, `front/src/PlaceSources.jsx`, `front/src/AgentPlaces.jsx`; test `front/src/CoordinateEvidence.test.jsx`, `front/src/PlaceSources.test.jsx`, `front/src/AgentPlaces.test.jsx`, `front/src/Trajectory.test.jsx`; modify `backend/tests/agent_browser_server.py`, `backend/README.md`, `backend/API.md`; create `front/tests/e2e/geolonia-coordinates.spec.cjs`。必要なCSSだけ `front/styles.css` または `front/trajectory.css` の既存クラスに追加する。

**Interfaces:** 既存 props を維持する。v2表示は「住所に対応する座標」「番地・住居番号まで照合」「店舗の入口は未確認」。dataset sourceのラベルは「座標データ」、確認checkboxは「住所・出典と地図の位置を確認しました」を継続する。加工表示、Geolonia/データセット出典、`https://creativecommons.org/licenses/by/4.0/` のリンクを確認前後に表示する。

```javascript
expect(screen.getByText('住所に対応する座標')).toBeTruthy();
expect(screen.getByText(/番地・住居番号まで照合/)).toBeTruthy();
expect(screen.queryByText('掲載座標')).toBeNull();
expect(screen.getByRole('link', {name: /CC BY 4.0/}).getAttribute('href'))
  .toBe('https://creativecommons.org/licenses/by/4.0/');
```

- [ ] **Step 1: UIとブラウザの失敗テストを書く。** `address_matched_evidence_keeps_kind_after_confirmation`、`dataset_source_and_license_are_distinct_from_store_sources`、`switching_geolonia_candidate_resets_confirmation` を追加する。BrowserRunner に「Geolonia座標の確認」で v2 詳細候補と v1 候補、位置未確認の粗い店舗を返す独立fixtureを追加する。E2E はradio切替/未確認選択禁止/地図リンク/確認/承認/再読込/保存後の種類・帰属表示を検証する。
- [ ] **Step 2: RED を確認する。** front で `npm test -- src/CoordinateEvidence.test.jsx src/PlaceSources.test.jsx src/AgentPlaces.test.jsx src/Trajectory.test.jsx`。期待:新しい座標種別と出典ラベル不足で FAIL。
- [ ] **Step 3: 表示を実装する。** アプリ内画面として DESIGN.md / MASTER.md と ui-ux-pro-max を読み適用する。v2 statusを明示して、確認後も「掲載座標」や「店舗情報」に分類しない。addressMatch.fetches の sourceId からdataset出典を識別し、店名や出典titleだけで分類しない。残る出典は安全な既存表示を使う。粗い補助結果にradioを作らない。HTML文字列を実行しない。保存済みTrajectoryは既存PlaceSourcesから同じ表示を得る。
- [ ] **Step 4: GREEN とbuildを確認する。** 同Vitest command、frontで `npm run build`、`npx playwright test --config=playwright.agent.config.cjs tests/e2e/geolonia-coordinates.spec.cjs`。E2Eはdesktop1440×900/phone375×812で根拠と承認の可視性、横overflowなし、keyboard focusを検証し、`docs/verification/2026-10-04-geolonia-coordinates/` にスクリーンショットを保存して目視確認する。
- [ ] **Step 5: README/APIを更新する。** Node22以上、`npm ci --prefix backend/geolonia`、不在時Web fallback、予算/優先順/粒度、v2証拠例、旧方式互換、CC BY帰属を記載する。APIの既存Web版説明を新pipelineの説明へ合わせる。front/dist をbuild成果として含める。
- [ ] **Step 6: タスクのファイルをコミットする。** message: `feat(ui): review Geolonia address coordinates and attribution`。

### Task 7: 全体の検証とレビュー

**Files:** Create `docs/verification/2026-10-04-geolonia-coordinates/README.md`; 必要な修正は所有タスクのファイルで行う。

**Interfaces:** 新しい製品インターフェースを追加しない。完成条件は承認済みspecの9節。

- [ ] **Step 1: 全体回帰を実行する。** `KAKEI_DB_PATH=/private/tmp/kakei-geolonia-full.sqlite3 backend/.venv/bin/python -m unittest discover -s backend/tests -v`、`npm test --prefix backend/geolonia`、frontで `npm test`。期待:全件 PASS。front build はTask 6後に変更があった場合だけ再実行する。
- [ ] **Step 2: 関連ブラウザ回帰を実行する。** frontで `npx playwright test --config=playwright.agent.config.cjs tests/e2e/geolonia-coordinates.spec.cjs tests/e2e/web-coordinates.spec.cjs tests/e2e/agent-delete.spec.cjs`。期待:全件 PASS。検証サーバーは使い捨てSQLite/8767で、稼働アプリ8765は変更しない。
- [ ] **Step 3: 公式接続の読み取り確認を行う。** 一時スクリプトで公開の詳細住所と町丁目住所をworkerへ送信し、level/point.level/証跡と粗い結果の不採用を確認する。実モデルの有料呼出しや実DB書込は不要。接続不可や収録不足は固定fixtureの成功と区別して記録する。
- [ ] **Step 4: 完成前の独立レビューを受ける。** 選択された実行方式のレビュー手順に従い、specの全完成条件・v1互換・プロセス終了・Web fallback・帰属表示を確認する。指摘を検証して修正した範囲の検査だけ再実行する。
- [ ] **Step 5: 結果を記録し最終コミットを作る。** READMEにcommands/結果/目視確認/実接続の限界を記載する。`git diff --check` と worktree status を確認する。message: `docs: record Geolonia coordinate verification`。最終報告は変更、検証結果、接続確認の限界、commitを簡潔に伝える。

## Execution handoff

推奨は **Native（このセッションで順に実装）**。7タスクが証拠契約・セッション管理・検索の順序で依存しており、同じ実装者が境界を維持して進め、最後に全体の独立レビューを受ける方法が適する。実装前に利用者がこの計画をレビューし、Native / Subagent-driven の実行方法を選択する。
