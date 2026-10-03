# Web Coordinate Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 地理検索APIを使わず、多様なWebページ・地図リンクから店舗座標を探し、取得できなければ根拠のある推定位置を確認・保存できるようにする。

**Architecture:** 既存のLangChain単一agentと `search_place` を維持し、検索・公開ページ取得・座標検証・推定を分離する。新しい `coordinateEvidence` を既存地点へ追加し、候補選択・SQLite・軌跡画面を通して推定状態と出典を保持する。既存Mapbox地点の互換処理を残し、新規検索のMapbox Geocoding要求を除去する。

**Tech Stack:** Python 3.14、FastAPI、LangChain、OpenAI Responses Web search、httpx/httpcore、SQLite、React 19、Vite、deck.gl、Mapbox GL JS、unittest、Vitest、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-04-web-coordinate-search-design.md`（利用者承認済み）。実装者は仕様書と計画を両方読む。

## Global Constraints

- 座標取得にMapbox GeocodingやGeoapifyなどの地理検索APIを使わない。
- 公式サイトだけへのドメイン制限を設けない。公開ページ・共有リンクを使い、ネイティブアプリを自動操作しない。
- OpenAIのWeb検索APIは継続利用する。地図表示は現在のMapboxを継続する。
- アプリ内部は既存どおり `[経度, 緯度]`。有限値、緯度±90・経度±180。
- 推定は `same_building` / `relative_offset` / `area_anchor`。保存後も `status=estimated` は変えない。
- 新候補の掲載座標・推定座標は両方明示確認を要求し、既存 `confirmed=true` を使用する。
- agent全体180秒、リース190秒。検索145秒、turn期限15秒前まで。
- Web最大6要求・各35秒・各 `max_tool_calls=3`。抽出最大6要求・各15秒。
- 公開ページ最大16 HTTP要求・各5秒・同時実行3。リダイレクトも要求として数え、最大3リダイレクト。
- 公開ページ512KiB、履歴段階200KiB、結果40KiB、候補8KiB、会話要約8KiB。段階最大20件。
- 1検索最大5店舗・各店舗最大3候補。新形式は出典最大6件、観測1〜4件、note500文字、excerpt2048文字。
- 100mを超える掲載値の差は `coordinate_conflict`。推定精度の数値確率・誤差半径を作らない。
- `relative_offset` は8方位・整数距離1〜5000m。徒歩時間・経路距離から直線距離を作らない。
- `pipelineVersion=web-coordinates-v1`。旧地点・旧提案・旧履歴は読める状態を維持する。
- `.env`・利用モデルを無断変更しない。キー・Cookieを外部ページへ送らない。実DBに検証データを書かない。
- アプリ内の外観は `DESIGN.md`、一般UXは `MASTER.md` とui-ux-pro-max。公開サイトのレイアウトを適用しない。

## Review Focus

1. 引用ページから短縮地図リンクへ移ると店舗の文脈が失われる場合、出典の対応関係を保ち、表示中心を店舗ピンに昇格させない（Task 2・3）。
2. 同じ施設に複数の店舗・支店がある場合、施設名だけで別店舗の座標を採用しない（Task 3・5）。
3. ターン後半の予算切れで推定候補が得られた場合、途中終了と推定の両方が残り、取消後の候補追加を防ぐ（Task 6）。
4. 同じ検索を並列共有・履歴再利用する場合、出典IDの再採番後も推定根拠が解決でき、サイズ制限で根拠だけが消えない（Task 7）。
5. 掲載候補と推定候補を切り替えた場合、前候補のチェック状態を流用せず、保存後も推定表示・距離説明が残る（Task 8・9）。

## File Structure and Execution

新しい責務は小さなモジュールに分ける。

| ファイル | 責務 |
| --- | --- |
| `backend/agent/coordinate_contracts.py` | 調査行、公開ページ、検証候補、推定入力の内部TypedDict |
| `backend/services/coordinate_evidence.py` | 座標根拠の保存形式・整合検証。外部通信しない |
| `backend/agent/public_pages.py` | 出典に結び付いた公開HTTPSページ取得・DNS/リダイレクト検証 |
| `backend/agent/map_links.py` | サービス別の地図URL解析。店舗ピンと表示中心を区別 |
| `backend/agent/web_coordinates.py` | 本文・構造化データ・地図リンクと店舗同一性の照合 |
| `backend/services/coordinate_math.py` | 外部依存のない球面座標計算。検証と推定で共用 |
| `backend/agent/coordinate_estimation.py` | 検証済み基準地点・対応関係からの推定候補作成 |
| `backend/agent/web_places.py` | 引用付きWeb探索と構造化抽出。座標確定権限は持たない |
| `backend/agent/place_search.py` | 探索・検証・推定を予算内で調停し、履歴へ記録 |
| `front/src/CoordinateEvidence.jsx` | 新形式の説明・推定範囲・確認状態の表示 |
| `front/src/lib/trajectory-estimates.js` | 地図の推定リングの生成・破棄 |

Task 1〜7はバックエンド、Task 8は既存画面の拡張、Task 9は一時DBでの統合検証。順番に実装し、各TaskでRED→GREEN→コミットする。独立した機能群への分割は不要で、すべて同じ地点候補の流れに必要。

実行方法は前回指定の **Native** を維持する。計画レビュー後、`superpowers:executing-plans` と `superpowers:using-git-worktrees` を読み、専用worktreeで実装する。計画作成段階では製品コードを変更しない。

以下のPythonコマンドはworktreeのルートから `/Users/spco/Kakei/backend/.venv/bin/python` を使う。共有venvを使い、不要な環境を作らない。既存フロント依存がなければlockfileに従う `npm ci`。テストのHTTP・DNSはfixtureで差し替え、通常テストで実サイトへ接続しない。

---

### Task 1: 座標根拠の契約とSQLite往復

**Files:** Create `backend/agent/coordinate_contracts.py`, `backend/services/coordinate_evidence.py`, `backend/tests/coordinate_fixtures.py`, `backend/tests/test_coordinate_evidence.py`。Modify `backend/services/place_evidence.py`, `backend/services/trajectory_validation.py`, `backend/services/trajectory_mutation.py`, `backend/db/schema.py`, `backend/db/trajectory_store.py`, `backend/agent/place_contracts.py`, `backend/tests/test_schema.py`, `backend/tests/test_place_evidence.py`。

**Interfaces:**

- `validate_coordinate_evidence(place: dict) -> None`: 保存属性の形、ID参照、座標・method・status・precisionの整合を検証。失敗は `ValidationError`。原文との照合はTask 3の責務。
- `CoordinateCandidate`: `{id, name, address, coordinates, sourceUrl, attribution, sources, coordinateEvidence, matchReasons}`。candidate IDはサーバー発行。
- `PublicPage`: `{url, final_url, redirects: list[str], content_type, body: bytes, retrieved_at: float}`。本文は実行中だけ保持。
- `DiscoveryRow`: 既存WebPlace属性に `role: 'store'|'anchor'`, `urls: list[str]`, `hints: list[EstimationHint]` を追加。anchor行は候補店舗にせず、元店舗のhintにあるanchorName/anchorAddressと対応する基準地点の調査結果。
- `EstimationHint`: `{method, anchorName, anchorAddress, relationSourceIds, relationExcerpt, distanceMeters: int|None, bearingDegrees: int|None, areaScope: str|None}`。`areaScope` は `block` / `neighborhood` / `district`。モデル出力にanchor座標を含めない。
- `VerifiedAnchor`: `{name, address, coordinates, sources, observations}`。`VerificationResult`: `{candidates: list[CoordinateCandidate], anchors: list[VerifiedAnchor], unresolved: list[str]}`。
- `rebind_candidate_sources(candidate: dict, mapping: dict[str,str]) -> dict` は `services/coordinate_evidence.py` に定義。sourcesとsourceIds/relationSourceIds/observations.sourceIdを同時に再採番する。

テスト用 `coordinate_fixtures.py` は `PUBLISHED_PLACE`, `ESTIMATED_PLACE`, `STORE_ROW`, `ANCHOR`, `BUILDING_HINT` を定義する。店名は「ドトールコーヒーショップ 西鉄福岡駅店」、テスト住所は既存web fixture、座標は `[130.4,33.59]`。ESTIMATED_PLACEはsame_buildingの確認前候補。すべて独立したdictとして作り、テストで変更する際はdeepcopyする。

- [ ] **Step 1:** `test_coordinate_evidence.py` に掲載、建物推定、方角距離推定、地区推定の正常fixtureを作り、sources参照欠落、未知属性、両方のgeocoding属性、NaN、method/precision不一致、距離0/5001、方角46度を拒否するテストを追加。既存DBからの移行と同期→読込→変更→JSON応答で `coordinateEvidence` が等しいこと、旧Mapbox記録が同じままであること、ID再採番後の全参照が解決することを追加。

```python
def test_unresolved_coordinate_source_is_rejected(self):
    place = copy.deepcopy(PUBLISHED_PLACE)
    place['coordinateEvidence']['sourceIds'] = ['missing']
    with self.assertRaises(ValidationError):
        validate_coordinate_evidence(place)
```

- [ ] **Step 2:** Run `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p test_coordinate_evidence.py -v`。Expected: 新形式が未知属性または未実装でFAIL。
- [ ] **Step 3:** 内部型を作り、仕様§6の厳密検証を実装する。新形式だけsources上限6、旧形式は既存規則。nullable `coordinate_evidence_json` を冪等追加し、すべての地点INSERT/SELECTと許可属性に対応する。公開APIを新設しない。
- [ ] **Step 4:** 上記と `test_schema.py`, `test_place_evidence.py`, `test_trajectory_mutation.py`, `test_trajectory_store.py` を `unittest discover -p <filename> -v` で実行しPASS。既存行の座標・geocoding・訪問参照が変わらないことを確認。
- [ ] **Step 5:** このTaskの列挙ファイルだけstageし、`git commit -m "feat: persist web coordinate evidence with legacy compatibility"`。

### Task 2: 公開ページの取得と共有リンク展開

**Files:** Create `backend/agent/public_pages.py`, `backend/tests/test_public_pages.py`。Modify `backend/requirements.txt`。

**Interfaces:**

- `PublicPageClient(*, resolver=None, network_backend=None)` はasync context manager。`fetch(url: str, *, allowed_urls: set[str], budget: SearchBudget, timeout: float) -> PublicPage`。
- `resolve_public_addresses(host: str) -> list[str]` はasync。すべての解決結果が公開IPでなければ拒否。検証済みIPへ接続し、Host/TLS SNIは元hostname。
- Task 6が公開する `SearchBudget.run('page', canonical_url, call)` をHTTP hopごとに使う。Task 2のテストは同じsignatureのFakeBudget。
- 失敗は既存 `PlaceProviderError`。コードは `unsafe_url`, `unsafe_address`, `unsupported_endpoint`, `redirect_limit`, `page_too_large`, `unsupported_content`, `timeout`, `network`。

- [ ] **Step 1:** DNS・network stream境界をstubし、内部IPv4/IPv6、公開と私有の混在DNS、公開先から内部URLへのredirect、DNS rebindingを拒否するテストを作る。接続先は検査したIP、TLS SNIとHostは元hostname、Authorization/Cookieはないことをassert。3redirect成功・4redirect失敗、各hop予算計上、512KiB成功・512KiB+1失敗、キャンセルを追加。

```python
async def test_private_dns_is_rejected_before_connect(self):
    # setUp supplies pages with resolver returning ['127.0.0.1'] and a connection spy.
    with self.assertRaises(PlaceProviderError) as failure:
        await self.pages.fetch('https://example.com/shop', allowed_urls={'https://example.com/shop'}, budget=self.budget, timeout=5)
    self.assertEqual(failure.exception.code, 'unsafe_address')
    self.assertEqual(self.connect_calls, [])
```

- [ ] **Step 2:** Run `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p test_public_pages.py -v`。Expected: 未実装でFAIL。
- [ ] **Step 3:** 既存環境の `httpx==0.28.1`, `httpcore==1.0.9` を直接依存として明記する。httpcoreのAsyncConnectionPoolに検証済みIPへ接続するnetwork backendを与え、proxy環境を継承しない。初期URLはallowed_urls所属、redirectは各段階で検査。timeoutは各hopの上限とし、全体期限はbudgetに従う。公開ページのみGET・自動retryなし・本文上限とresponse closeを実装する。公開Google Maps URLの `api=1` は版指定であり、キーを使う地理検索APIの要求と区別する。
- [ ] **Step 4:** 上記テストを実行しPASS。引用された短縮URL→実URLを返し、途中URLを含むredirectsと最終URLが保持されることを確認。地理検索API・内部RPCと認証付きURLの拒否をassert。
- [ ] **Step 5:** `git add backend/agent/public_pages.py backend/tests/test_public_pages.py backend/requirements.txt`、`git commit -m "feat: fetch bounded public pages with pinned DNS and redirects"`。

### Task 3: 掲載座標と地図リンクの検証

**Files:** Create `backend/agent/map_links.py`, `backend/agent/web_coordinates.py`, `backend/tests/test_web_coordinates.py`, `backend/tests/fixtures/web_coordinates/`（店名住所付きHTML/JSON/リンクfixture）。

**Interfaces:**

- `parse_map_link(url: str) -> dict|None`: `{coordinates, kind: 'map_pin_url'|'map_viewport', targetName: str|None}`。既知形式だけ解釈。
- `verify_page(row: DiscoveryRow, page: PublicPage, source: dict) -> VerificationResult`: pure function。本文・geo・リンク・店舗同一性を検証。
- `WebCoordinateVerifier(pages: PublicPageClient, budget: SearchBudget)`: `async verify(row: DiscoveryRow, *, timeout: float) -> VerificationResult`。出典と取得済みリンクに限って取得し、同URLの取得を共有する。
- 出力のobservationsは取得済み原文/値/URLに結び付き、`coordinateEvidence.verification='needs_confirmation'`。地図表示中心はcandidatesに入れず、対応確認したanchorsにだけ入る。
- role=anchorの行は元hintの名前・住所へ照合したうえでanchorsだけを返す。店舗の候補を増やさない。

- [ ] **Step 1:** 本文の「緯度33.590・経度130.400」、同店のJSON-LD LocalBusiness.geo、第三者ブログ掲載値から `[130.400,33.590]` を返すテストを追加。Google `/maps/search/?api=1&query=LAT,LON` と店舗詳細内の単一 `!3dLAT!4dLON` はpinの解析対象、`/@LAT,LON,ZOOM` とcenterはviewport。Apple `ll=LAT,LON&q=名称` はラベル付きpin、llのみはviewport。OSM mlat/mlonはmarker、map fragmentのみはviewport。URL単独では店舗同一性を証明せず、原文・リンクの文脈も要求。Yahoo/Mapion/NAVITIME等も調査対象だが、目的地の意味を確認できない未知形式はNoneとして本文・geo・別サイトへ進む。

```python
def test_map_viewport_is_not_a_store_pin(self):
    parsed = parse_map_link('https://www.google.com/maps/@33.59,130.4,18z')
    self.assertEqual(parsed['kind'], 'map_viewport')
    self.assertEqual(parsed['coordinates'], [130.4, 33.59])
```

- [ ] **Step 2:** 別支店・同一施設の他店舗・複数geo・緯度経度入替・無効値・モデル回答のみの数値・自作URLを拒否するテストと、短縮URLの店舗文脈を引き継ぐテストを追加。Run `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p test_web_coordinates.py -v`。Expected: 未実装でFAIL。
- [ ] **Step 3:** HTMLParserとJSON解析で本文・JSON-LD・リンクを抽出する。本文の数値は明示ラベル付きだけ採用し、座標を含む同一店舗の単位で照合。URLの緯度経度順序・意味をサービス別関数へ分ける。Googleのquery_place_idがある場合は座標queryがfallbackになるため、店名/address対応の追加検証なしでpin座標を確定しない。店名住所対応のないURL数字を採用しない。検証した基準地点はanchorsに返す。
- [ ] **Step 4:** 上記とTask 1・2のテストを実行しPASS。出典外URLへのアクセスが0件で、表示中心だけでは掲載候補が0件になることを確認。
- [ ] **Step 5:** このTaskの新規ファイルをstageし、`git commit -m "feat: verify published coordinates from pages and map links"`。

### Task 4: 基準地点からの位置推定

**Files:** Create `backend/services/coordinate_math.py`, `backend/agent/coordinate_estimation.py`, `backend/tests/test_coordinate_estimation.py`。Modify `backend/services/coordinate_evidence.py`（計算結果の整合検証）。

**Interfaces:**

- `services.coordinate_math.destination(anchor: list[float], distance_meters: int, bearing_degrees: int) -> list[float]`: 地球半径6,371,000mの球面前進計算、経度を[-180,180]へ正規化。servicesからagentへ依存させない。
- `estimate_coordinates(row: DiscoveryRow, anchors: list[VerifiedAnchor]) -> list[CoordinateCandidate]`: 紐付いたhintsのみ使い、掲載候補の取得は行わない。
- 建物/地区はanchor座標をそのまま使う。relative_offsetはdestinationで計算。ID生成はUUID。Task 1のvalidatorは同じdestinationを使って結果を誤差1m以内で検証する。

- [ ] **Step 1:** fixtureの同一建物で座標等値・status estimated・precision building、東100mで経度増加・緯度ほぼ一定・距離100m±1m、日付変更線を越える正規化、8方位をテストする。地区対応ならprecision area。徒歩5分・駅近く・都市中心・店名に駅名だけ・別支店の関係・relationship原文なしでは候補0件をassert。

```python
def test_building_estimate_remains_estimated(self):
    row = {**copy.deepcopy(STORE_ROW), 'hints': [copy.deepcopy(BUILDING_HINT)]}
    result = estimate_coordinates(row, [copy.deepcopy(ANCHOR)])
    self.assertEqual(result[0]['coordinates'], ANCHOR['coordinates'])
    self.assertEqual(result[0]['coordinateEvidence']['status'], 'estimated')
    self.assertEqual(result[0]['coordinateEvidence']['verification'], 'needs_confirmation')
```

- [ ] **Step 2:** Run `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p test_coordinate_estimation.py -v`。Expected: 未実装でFAIL。
- [ ] **Step 3:** 採用優先順位はsame_building→relative_offset→area_anchor。anchorとrelationの出典・店名・住所・地区対応を検証し、最大3候補。精度数値は生成せずnoteに範囲未確認を含める。距離/方角は原文の数値・8方位から検証し、モデルの提案値だけで計算しない。
- [ ] **Step 4:** 上記と `test_coordinate_evidence.py` を実行しPASS。座標改ざん・出典欠落・不正パラメータをvalidatorでも拒否。
- [ ] **Step 5:** このTaskのファイルをstageし、`git commit -m "feat: estimate positions from verified geographic anchors"`。

### Task 5: 幅広いWeb探索と根拠付き抽出

**Files:** Modify `backend/agent/web_places.py`, `backend/agent/place_contracts.py`, `backend/tests/test_agent_web_places.py`。Create `backend/tests/web_coordinate_fixtures.py`。

**Interfaces:**

- `WebPlaceProvider.research(request: dict, *, strategy: str='store', prior: dict|None=None, timeout: float) -> dict`。strategyは `store` / `maps` / `address` / `anchor`。priorは検証済み店名住所・未確認理由・試行済み条件だけ。
- `WebPlaceProvider.extract(report: dict, *, timeout: float) -> list[DiscoveryRow]`。hintsのrelationExcerptは引用段落内の連続原文、relationSourceIdsは実在ID。urlsはAPIのsources/actionか引用段落の実在リンクに限る。
- reportは既存text/sources/supports/actions/usage/retrievedAtに `discoveredUrls: list[str]` を追加する。数値座標は確定出力しない。

- [ ] **Step 1:** Responsesの要求で公式ドメイン限定なし・max_tool_calls3・store falseをassert。第三者店舗ページと公開マップを返すfixture、施設関係を含む引用からurls/hintsを抽出するfixtureを作る。引用のない住所・自作URL・別支店の関係・店舗を含まない段落・外部文書の命令を拒否。

```python
async def test_web_research_is_not_official_domain_only(self):
    await self.provider.research({'query': STORE_ROW['name']}, strategy='maps', timeout=35)
    self.assertEqual(self.sent[0]['max_tool_calls'], 3)
    self.assertNotIn('filters', self.sent[0]['tools'][0])
    self.assertFalse(self.sent[0]['store'])
```

- [ ] **Step 2:** Run `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -p test_agent_web_places.py -v`。Expected: 新schema・max_tool_calls・探索strategyに関してFAIL。
- [ ] **Step 3:** 既存の引用段落へのbindingを維持してschemaとpromptを拡張する。同じ施設の複数店を別rowにし、出典/アクションURLを発見用に収集。anchor戦略は元店舗の検証済みhintをpriorで渡し、基準地点をrole=anchorで返す。座標検証不能・移転時期不明の説明を返す。privateな取引額・レシート本文を検索へ送らない。
- [ ] **Step 4:** 上記テストを実行しPASS。店舗・施設の関係を単なる店名文字列から推論しないこと、モデルに編集ツールを付与しないことを確認。
- [ ] **Step 5:** このTaskのファイルをstageし、`git commit -m "feat: research coordinates across public websites and maps"`。

### Task 6: 検索調停・予算・agent接続の切替

**Files:** Modify `backend/agent/place_search.py`, `backend/agent/limits.py`, `backend/agent/runtime.py`, `backend/agent/place_http.py`, `backend/agent/place_matching.py`, `backend/db/agent_search_store.py`（段階上限のみ）, `backend/tests/test_agent_place_search.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_agent_place_matching.py`。Remove `backend/agent/geocoding.py`, `backend/tests/test_agent_geocoding.py`（旧保存形式のテストは残す）。

**Interfaces:**

- `SearchBudget.run(stage: str, key: str, call)`: stageはweb/extract/page。pageは各hopを数え、同時実行3。ローカルestimate/compareは要求予算を消費しない。
- `PlaceSearchService(web: WebPlaceProvider, verifier: WebCoordinateVerifier, searches, resolver, context, budget)`、`search(request: dict) -> SearchResult` は既存外部契約を維持する。
- `compare_candidates(candidates: list[CoordinateCandidate]) -> list[CoordinateCandidate]`: 平均せず、同店の100m超差へcoordinate_conflict。候補は店舗ごと最大3。
- `configuration()` は専用MapboxキーなしでplacesAvailable=true、OpenAIの既存model選択は維持。

- [ ] **Step 1:** 住所のみ→maps追加探索→第三者掲載座標、掲載なし→anchor探索→推定、全失敗→位置未確認をテスト。Strategyはstoreから開始し、既知店名住所があればmaps→address→anchorへ進む。店情報も未取得なら店名・支店・施設の条件を具体化してstoreを再探索する。

```python
async def test_store_without_pin_gets_a_grounded_estimate(self):
    # setUp returns store facts, no published store coordinates, then a verified building anchor.
    result = await self.service.search(self.req)
    self.assertEqual(result['pipelineVersion'], 'web-coordinates-v1')
    self.assertEqual(result['candidates'][0]['coordinateEvidence']['status'], 'estimated')
    self.assertIn('anchor', self.provider.strategies)
```

- [ ] **Step 2:** 予算web6/extract6/page16、各35/15/5秒、page同時3、145秒期限・最終15秒留保、同条件共有、100m差、認証停止、取得中取消、期限直前の推定partialをテスト。Run `unittest discover` で `test_agent_place_search.py` と `test_agent_runtime.py`。Expected: 旧構成・予算・設定・promptでFAIL。
- [ ] **Step 3:** 新pipelineを配線し、解決済みの候補は探索を終了。anchor行はhintへの対応を確認して基準点としてのみ検証し、店舗のstore_reasons条件に混ぜない。予算やサイト失敗を未存在扱いしない。saved推定地点のmetadataを保持し、area推定だけ1kmフィルターを緩め、実際の地域矛盾は拒否。Task 1のID再採番helperを使用。address_formatは互換として受理し検索のidentityから外す。段階上限を20へ更新。Runtimeにページclient/verifierを生成・finallyでcloseし、Mapbox要求設定をplace_httpから外す。
- [ ] **Step 4:** 上記と `test_agent_place_matching.py` を実行しPASS。旧runtime testのGeocoder patchをverifier境界のfixtureへ変更する。外部通信はOpenAIと出典に結び付いた公開GETのみというassertを入れる。全ツール8回の既存上限は維持し、内部Web探索6要求と混同しない。
- [ ] **Step 5:** このTaskのファイルをstageし、`git commit -m "feat: switch agent place discovery to web verification and estimation"`。

### Task 7: 候補選択・検索履歴・根拠の保持

**Files:** Modify `backend/services/agent_places.py`, `backend/db/agent_search_store.py`, `backend/tests/test_agent_places.py`, `backend/tests/test_agent_search_store.py`, `backend/tests/test_agent_api.py`, `backend/tests/test_agent_store.py`。

**Interfaces:** 既存 `choose(..., confirmed=False)` を維持。新形式のverification=needs_confirmationではconfirmedを要求し、保存時にverificationだけuser_confirmedへ変更する。`bounded_result()` / `bounded_candidates()` の返却形式を維持し、根拠の削除は候補全体の省略にする。

- [ ] **Step 1:** 推定・掲載の未確認選択拒否→確認選択→承認→API再読込でstatus/method/basis/sources保持、旧Mapbox提案の選択可をテスト。履歴にweb/extract/verify/estimate/compareが保存され、20段階は可・21は拒否。新versionの再利用で全参照IDが解決し、旧versionは再検索案内になることをassert。

```python
def test_confirming_an_estimate_does_not_publish_it(self):
    commands, metadata = choose(self.connection, self.commands, self.metadata, candidate_id='estimated', confirmed=True)
    evidence = metadata['authorizedPlaces']['shop']['coordinateEvidence']
    self.assertEqual(evidence['verification'], 'user_confirmed')
    self.assertEqual(evidence['status'], 'estimated')
```

- [ ] **Step 2:** 必須出典を削らない40KiB/8KiB上限、並列検索の別IDと同じ検証結果、同施設の複数候補の別ID、不正candidate ID、住所変更後の再利用拒否を追加。Run `unittest discover` で `test_agent_places.py`, `test_agent_search_store.py`, `test_agent_api.py`。Expected: 確認不要・根拠欠落・4段階制限でFAIL。
- [ ] **Step 3:** 新形式をauthorizedPlacesへ原文通りコピーし、statusを変えない。Task 1のID再採番helperを提案・履歴要約にも使い、末尾の候補全体を省略して必須根拠の原子性を守る。旧Geocoder patch付きAPIテストを新verifier境界へ変更し、旧Mapbox保存形式のfixtureテストは維持する。
- [ ] **Step 4:** 上記と `test_agent_store.py`, `test_place_evidence.py` を実行しPASS。過去の助手文章は新座標の出典に使われず、未保存・省略した候補をモデル/画面へ返さないことを確認。
- [ ] **Step 5:** このTaskのファイルとTask 6のbinding利用箇所をstageし、`git commit -m "feat: require coordinate review and preserve evidence through search history"`。

### Task 8: 掲載・推定・未確認の画面表示

**Files:** Create `front/src/CoordinateEvidence.jsx`, `front/src/CoordinateEvidence.test.jsx`, `front/src/lib/trajectory-estimates.js`, `front/src/lib/trajectory-estimates.test.js`。Modify `front/src/AgentPlaces.jsx`, `front/src/AgentPlaces.test.jsx`, `front/src/PlaceSources.jsx`, `front/src/PlaceSources.test.jsx`, `front/src/Trajectory.jsx`, `front/src/Trajectory.test.jsx`, `front/src/TrajectoryMap.jsx`, `front/src/lib/trajectory-model.js`, `front/src/lib/trajectory-model.test.js`, `front/src/AgentProposal.jsx`, `front/styles.css`, `front/trajectory.css`。

**Interfaces:**

- `<CoordinateEvidence evidence={coordinateEvidence} sources={sources}/>` は状態・方法・範囲・根拠noteを表示。HTMLを描画しない。
- `attachEstimatedMarkers(map, events, Marker=mapboxgl.Marker) -> cleanup`: 推定eventの有効coordinatesだけに装飾用DOM markerを追加。32pxの破線外周・pointer-events none・aria-hidden。mapboxgl.Markerを既存APIとして使い、新地理検索や新npm依存なし。
- `buildTrajectoryDays()` に `hasEstimatedCoordinates: boolean` を追加し、推定位置があれば距離説明と凡例へ反映。`locationStatus=needs_review` の座標除外を維持。

- [ ] **Step 1:** 新候補で確認チェックなしは選択不可、推定→掲載へのradio変更でチェック解除、selected candidateのstatusに応じて正確な確認文言を出すテストを作る。Sources表示は新形式と旧Mapboxを区別し、user_confirmed推定も「推定位置」。不正URL・HTMLを実行しないことをassert。

```jsx
it('keeps the estimate label after user confirmation', () => {
  render(<CoordinateEvidence evidence={{...estimatedEvidence, verification:'user_confirmed'}} sources={sources} />);
  expect(screen.getByText('推定位置')).toBeInTheDocument();
  expect(screen.getByText(/誤差範囲は未確認/)).toBeInTheDocument();
});
```

- [ ] **Step 2:** Run `npm --prefix front test -- --run src/AgentPlaces.test.jsx src/PlaceSources.test.jsx src/CoordinateEvidence.test.jsx`。Expected: 新形式表示・確認制御が未実装でFAIL。
- [ ] **Step 3:** 新形式の確認文を仕様§10どおり表示し、同じconfirmed引数を送る。推定リングmarkerとcleanup、凡例、タイムラインに文字表示を追加。距離に「推定位置を含む概算」、誤差数値は出さない。note・sourceを表示し、提案diffの新属性も日本語ラベルへ追加。
- [ ] **Step 4:** 地図helperに公開・推定・無効座標・locationStatus needs_reviewの混在fixtureを渡し、推定だけmarkerが作られcleanupでremoveされるテストを実行。`npm --prefix front test` がPASS。モデルfixtureでhasEstimatedCoordinatesと直線距離説明を確認。
- [ ] **Step 5:** このTaskのファイルをstageし、`git commit -m "feat: display and confirm published and estimated positions"`。

### Task 9: 一時DBでの統合・実API確認・配布ビルド

**Files:** Modify `backend/tests/agent_browser_server.py`, `backend/README.md`, `backend/API.md`, `front/dist/`。Create `front/tests/e2e/web-coordinates.spec.cjs`, `docs/verification/2026-10-04-web-coordinates.md`, `docs/verification/2026-10-04-web-coordinates/`（画像・結果）、`.superpowers/web-coordinates/live.py`（ignored実API検証スクリプト）。

**Interfaces:** BrowserRunnerの既存分岐より先に「Web座標の確認」/「推定位置の確認」のdeterministic分岐を追加し、Task 1の新形式fixtureを使う。実API確認は `WebPlaceProvider` / `PlaceSearchService` の同じ経路を一時DBへ接続し、実DBを参照しない。

- [ ] **Step 1:** Playwrightで掲載/推定候補の未確認選択不可、候補切替で確認解除、確認→選択→承認→reload→軌跡で推定note/source/距離表示保持を検証。1440×900と375×812でリンク・確認・保存が可視、横スクロールなし。fixtureサーバーは常に一時DB。

```js
test('estimated place needs explicit review before selection', async ({page}) => {
  // Test setup submits 「推定位置の確認」 and selects its radio candidate.
  await expect(page.getByRole('button', {name:'この地点を選ぶ'})).toBeDisabled();
  await page.getByRole('checkbox', {name:'この推定位置を確認しました'}).check();
  await expect(page.getByRole('button', {name:'この地点を選ぶ'})).toBeEnabled();
});
```

- [ ] **Step 2:** `npm --prefix front run build` の後、`KAKEI_TEST_PYTHON=/Users/spco/Kakei/backend/.venv/bin/python npm --prefix front run test:e2e -- --config playwright.agent-search.config.cjs tests/e2e/web-coordinates.spec.cjs`。Expected: fixture追加前は候補の期待がFAIL。実装後PASS。地図描画はトークンなしfixtureでは検証しないため、Task 8のリングテストと区別する。
- [ ] **Step 3:** BrowserRunner分岐を実装し、README/APIの検索手順・予算・座標根拠・旧形式互換・Mapboxキー不要を更新する。旧MapboxのAPI利用説明を現在の必須条件として残さない。
- [ ] **Step 4:** `/Users/spco/Kakei/backend/.venv/bin/python -m unittest discover -s backend/tests -v`、`npm --prefix front test`、`npm --prefix front run build`、`KAKEI_TEST_PYTHON=/Users/spco/Kakei/backend/.venv/bin/python npm --prefix front run test:e2e -- --config playwright.agent-search.config.cjs`、`git diff --check`。Expected: 全PASS。失敗があれば原因に対応するTaskへ戻り、具体的な回帰テストを追加する。
- [ ] **Step 5:** 一時DB・既存モデル設定でドトールコーヒーショップ 西鉄福岡駅店を確認。Web最大3要求・公開ページ最大8hop、検索期限は本番定数。モデル、日時、実検索語、取得元、結果、通信失敗を検証記録へ残す。キーを出力しない。トークンなしでconfiguration可、地理検索API要求0件を同時に確認。外部サイトで未確認ならその結果を正確に報告し、固定テストの成功と分ける。
- [ ] **Step 6:** 画面をdesktop/phoneで撮影・目視し、確認カードと保存後の推定表示を記録。利用できる本番の地図表示トークンで推定リングの描画も読み取り専用で確認する。preview不可の場合は理由と未確認範囲を記録し、描画を確認済みとしない。
- [ ] **Step 7:** 変更全体へ `superpowers:requesting-code-review` を適用し、Nativeの全体レビューを1回行う。重要な指摘を修正して該当テストを実行。`superpowers:verification-before-completion`、`superpowers:finishing-a-development-branch` に従って結果を報告し、承認済みの統合範囲だけ実行する。
- [ ] **Step 8:** 検証記録・ドキュメント・配布distをstageし、`git commit -m "test: verify web coordinates and ship reviewed frontend assets"`。実データ・.env・キー・raw HTML本文をコミットしない。

## Plan Self-Review

- 仕様§1〜3 → Task 3・5・6（広い探索、地理検索API除去、店舗同一性）。
- 仕様§4 → Task 4（3推定方式と不採用条件）。
- 仕様§5 → Task 2・3（公開取得、URL根拠、DNS/redirect、本文検証）。
- 仕様§6〜7 → Task 1・7（属性往復、候補権限、明示確認、互換性）。
- 仕様§8〜9 → Task 6・7（180/190/145秒、段階20、共有予算、設定・prompt）。
- 仕様§10〜11 → Task 8・9（画面、地図、全テスト、一時DB実API）。
- Review Focusの5項目は上記Taskのテストに割り当て済み。PublicPage/DiscoveryRow/VerifiedAnchor/VerificationResultはTask 1、取得clientはTask 2、verifierはTask 3、推定関数はTask 4が定義し、後続Taskで同じsignatureを使う。
- 製品コードの実装は計画承認後。Nativeの選択は保持し、実装方法の再選択は求めない。

## Parser References

- [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started): queryと表示centerの区別、query_place_idの優先、api=1は公開Maps URLの版指定（2026-10-04確認）。
- [Apple Map Links](https://developer.apple.com/library/archive/featuredarticles/iPhoneURLScheme_Reference/MapLinks/MapLinks.html): llとqの組合せによるpin、ll単独の表示中心（2026-10-04確認）。公開新URL形式は実データが取得できるものだけ追加し、未確認形式へ推測パーサーを作らない。
