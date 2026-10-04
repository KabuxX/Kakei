# GitHub Pages Offline Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 現在の記録と原本を閲覧でき、東京の同梱地図を外部APIなしで表示するGitHub Pages用DEMOを公開する。

**Architecture:** 通常版と同じReact画面を使い、Viteのdemoモードでruntimeを切り替える。runtimeがブラウザ内mock API、原本URL、初期月、地図と閲覧専用状態を提供し、通常版は既存APIとGoogle Mapsを使う。snapshotと地図は手動で一度生成してコミットし、Pagesはその静的資源だけを配信する。

**Tech Stack:** Python 3.14 / sqlite3、React、Vite、Vitest、MapLibre GL JS、PMTiles、ProtomapsのOSMベースマップ、GitHub Actions / Pages。

**Spec:** `docs/superpowers/specs/2026-10-05-github-pages-offline-demo-design.md`

## Global Constraints

- 閲覧専用。取引41件、軌跡13日・訪問38件・地点13件、会話3件・メッセージ8件、レシート原本2件、予算6カテゴリは設計時の観測値。エクスポート時の差分は報告し、黙って公開対象を増減させない。
- 実DBを変更しない。SQLiteバックアップのコピーからエクスポートし、通常版の保存先・API・Google Maps・既存dev:mockを維持する。
- 公開物にSQLite、`.env`、キー、認証情報、処理リース、内部ログ、Googleの生応答と期限付き座標cacheを含めない。
- Google由来の2地点は同じ店舗を独立の根拠で照合する。providerラベルの付け替えは禁止。確認できなければ訪問を残して位置未確認と報告する。
- 地図は東京本土（23区＋多摩）、島しょ除外。保存範囲は138.90,35.45,139.95,35.95を初期案として本土と訪問地点の包含を検証する。近隣地域の矩形内表示は許容する。
- タイルzoom 0〜14、表示最大zoom 16、PMTilesは50 MiB以内。道路・鉄道・水域・主要地名の日本語表示。範囲を黙って縮めない。
- 外部サービスへ自動通信しない。データ・地図・文字・sprite・worker・原本は同じ公開サイトから読み込む。外部出典リンクの明示的なクリックは許容する。
- `dev:demo`、`build:demo`、`front/dist-demo/`、Pagesの`/Kakei/`を追加。通常`build`と`front/dist/`を維持する。
- `DEMO・閲覧専用`を表示する。月変更・検索・フィルター・詳細・CSV・会話選択・原本表示・地図操作は利用できる。書き込み入口とAgent送信は非表示にする。
- 初期月はsnapshotの最新取引月。通常版のlocalStorageを読まず、DEMOから初期化POSTや会話作成POSTを送らない。
- デザインはアプリ内画面としてDESIGN.mdと既存のページ順序に従う。1440pxと375pxで最初に選択月と収支が見えることを確認する。
- snapshot再生成は手動。CIや通常ビルドは実DB・`.env`・外部地図照合を必要としない。PWAは追加しない。

## Review Focus

1. 会話内の未保存・期限切れの変更案や原本参照が、公開後に暦が進んでも消えず、書き込みの入口を露出しないこと（Task 1/3）。
2. `/Kakei/`配下からの原本・ロゴ・遅延import・直接編集URLが、ルートURLや本物のAPIへ抜けないこと（Task 2/3/6）。
3. Range未対応・不正なContent-Range・同時タイル要求が、無制限の全体再取得や外部URLへの切替を起こさないこと（Task 4）。
4. Google地点・住所不一致・位置未確認の訪問を含む日も、参照・時系列・番号を保って描画可能な区間だけを表示すること（Task 1/2/5）。
5. 通常版ビルドにDEMOの原本やデータが混入せず、公開DEMOが閲覧者の既存localStorageや現在日付を初期化データとして利用しないこと（Task 2/6）。

## File Structure and Contracts

| 単位 | ファイルと責務 |
| --- | --- |
| エクスポート | `backend/demo/export_snapshot.py`：一貫したDBコピーから表示DTOと原本を生成。`backend/demo/validate_snapshot.py`：契約・参照・原本の検証。`backend/export_demo.py`：CLI入口。 |
| コミットするデータ | `front/demo/data/snapshot.json`、`manifest.json`、`curated-places.json`、`front/demo/public/demo-data/receipts/`。curated-placesには独立した根拠と照合日を保存する。 |
| runtime | `front/src/lib/runtime.js`：通常版。`front/demo/runtime.js`：DEMO。Vite alias `@kakei/runtime`で選択する。 |
| mock API | `front/demo/api.js`：読み取りと403/404のResponse。`front/demo/validate.js`：ブラウザ／ビルドで共有するsnapshot検証。 |
| 地図資源 | `front/demo/maps/manifest.json`、`style.js`、`archive-source.js`、`front/demo/public/maps/`。取得手順は`tools/demo/prepare-map.mjs`と`tools/demo/README.md`。 |
| 地図UI | `front/src/components/trajectory/OfflineTrajectoryMap.jsx`：MapLibreの表示と訪問選択。`front/src/lib/offline-trajectory.js`：GeoJSON・描画対象の純粋変換。 |
| 展示UI | App・AppShell・Dashboard・TransactionDetail・TransactionAddress・AgentChat・AgentControls・AgentProposal・ReceiptReviewでreadOnlyの既定値falseを守る。静的地点表示は`front/src/components/places/DemoPlaceResults.jsx`。 |
| 配信 | `front/scripts/{validate-demo,serve-demo-check}.mjs`、`front/vite.config.mjs`、`front/package.json`、`.github/workflows/demo-pages.yml`、`README.md`、`front/README.md`。serve-demo-checkは静的配信と通信制約の確認だけを行い、ブラウザを操作しない。 |

Snapshot v1は`{schemaVersion:1, exportedAt, transactions:[], categories:{}, timeline:{places:{},days:[]}, threads:[], receipts:{}, placeLookup:{}}`。threadsは既存get_threadの表示DTO、receiptsは`{[id]:{id,mimeType,pageCount,sha256,createdAt,transactionId,threadId,path}}`。placeLookupは過去のGoogle place IDから独立照合済みDEMO地点への参照。生応答は保存しない。manifestは版・exportedAt・latestMonth・件数・JSONハッシュ・原本ハッシュを持つ。

runtime両実装は`isDemo:boolean`、`readOnly:boolean`、`snapshotTime:number|null`（秒）、`getInitialMonth(now:Date):Date`、`apiFetch(input:string,init?:RequestInit):Promise<Response>`、`assetUrl(path:string):string`、`receiptUrl(id:string,threadId?:string):string`、`loadTrajectoryMap():Promise<{default:Component}>`を提供する。通常版はfalse/null、今の前月選択、globalThis.fetch、従来API原本URL、GoogleTrajectoryMap。DEMOはsnapshot月・時刻、cloneするmock Response、base付き原本URL、OfflineTrajectoryMapを返す。

### Task 1: 現在のデータを安全に書き出す

**Files:** Create `backend/demo/{__init__,export_snapshot,validate_snapshot}.py`, `backend/export_demo.py`, `backend/tests/test_demo_export.py`, `front/demo/data/{snapshot,manifest,curated-places}.json`, `front/demo/public/demo-data/receipts/*`。

**Interfaces:** Consumes 現在のSQLiteスキーマ。Produces `export_demo(db_path:Path,out_dir:Path,curated_path:Path,captured_at:str)->dict`（manifest）、`validate_snapshot(snapshot:dict,receipts_dir:Path)->None`とSnapshot v1。DBコピーはTemporaryDirectory内、元DBはmode=roで開く。

- [ ] **Step 1 — エクスポートの失敗テストを書く。** 保存済み／期限切れ変更案、未保存レシート、2つのGoogle地点、交通区間を持つ一時DBを作る。`test_demo_export.py`で次を検証する。
  ```python
  assert exported['threads'][0]['messages'][0]['text'] == original_text
  assert receipt_file.read_bytes() == original_bytes
  assert before_database_dump == after_database_dump
  assert exported['timeline']['days'][0]['events'][0]['id'] == original_event_id
  assert not contains_internal_logs_or_google_cache(exported)
  ```
  原本欠落、重複訪問ID、存在しない取引参照、無効予算、Hash不一致は検証エラー。Google地点の座標はcuratedからだけ得る。未照合はcoordinates=nullと`demoPositionUnconfirmed:true`、元の店と参照を保つ。過去日付でも原本を削除しない。
- [ ] **Step 2 — REDを確認。** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_demo_export.py'`。Expected: 未実装importによるFAIL。
- [ ] **Step 3 — exporterとvalidatorを実装。** ローカルAPIの表示DTOに合わせ、コピー上でもexpire処理や外部検索を使わない。threadの表示情報だけを抽出し、許可された字段からDTOを組み立てる。原本は安全なID＋MIME対応拡張子。JSON/原本を全検証してから出力先へ置く。CLIは`--db --output --curated-places`を必須とする。
- [ ] **Step 4 — GREENとDB回帰を確認。** Run `backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py'`。Expected: 全PASS、元DB不変、原本一致。
- [ ] **Step 5 — 独立した地点根拠を記録する。** 2店舗をレシート・店舗公式／オープンデータで照合。curatedは`{[googlePlaceId]:{name,address,coordinates,sourceUrl,attribution,verifiedAt,note}}`、coordinatesは検証済み配列またはnull。Google座標cacheや画面中心を根拠にしない。未確認なら理由を記録する。
- [ ] **Step 6 — 実データを一度エクスポート。** Run `backend/.venv/bin/python backend/export_demo.py --db /Users/spco/Kakei/backend/data/kakei.sqlite3 --output front/demo --curated-places front/demo/data/curated-places.json`。Expected: 件数・位置未確認一覧・ハッシュを表示、原DB不変。観測値との差があれば公開対象を確定する前に報告する。
- [ ] **Step 7 — コミット。** データ・原本・CLI・テストだけをadd。Expected: `feat: export current records for read-only demo`、SQLite/cache/秘密情報がdiffにない。

### Task 2: ブラウザ内mock APIとビルド境界

**Files:** Create `front/{demo/{api,validate,runtime}.js,src/lib/runtime.js,src/lib/runtime.test.js,src/lib/demo-api.test.js}`。Modify `front/src/lib/{api,budget-api,agent-api}.js`, `front/src/lib/trajectory-model.js`, `front/src/pages/Trajectory.jsx`, `front/vite.config.mjs`, `front/package.json`, `.gitignore`。

**Interfaces:** Consumes Snapshot v1とmanifest。Produces runtimeの共通契約、`createDemoFetch(snapshot:Snapshot):typeof apiFetch`、`validateDemoSnapshot(snapshot,manifest):void`。mockは既存GETのenvelopeを使い、書き込みに`{error:{code:'demo_read_only',message:'DEMOは閲覧専用です。'}}`を403で返す。

- [ ] **Step 1 — mock契約と通常版のテストを書く。** 取引・詳細・予算・軌跡・住所・会話・変更案・原本メタデータをfixtureで確認する。
  ```js
  expect((await (await demo('/api/budget')).json()).categories).toEqual(seed.categories);
  expect((await demo('/api/transactions',{method:'POST',body:'{}'})).status).toBe(403);
  expect((await demo('/api/agent/threads/missing')).status).toBe(404);
  expect(realFetch).not.toHaveBeenCalled();
  ```
  POST/PUT/PATCH/DELETE全種拒否、返却JSONの変更が次回結果に影響しないこと、AbortSignal、未知GET、壊れたsnapshot、URLの不正encodeを検証。runtimeは2029年でもsnapshot月と時刻を返す。通常版は前月と従来のfetch/URLを返す。
- [ ] **Step 2 — REDを確認。** Run `npm test --prefix front -- src/lib/demo-api.test.js src/lib/runtime.test.js`。Expected: 未実装でFAIL。
- [ ] **Step 3 — runtimeとmockを実装。** Vite aliasはmode=demoだけDEMO実装へ解決。全API helperのfetch既定値をruntime.apiFetchへ揃える（budgetも含む）。uploadも同じ境界を使ってDEMOでは403。receiptUrlとassetUrlは`import.meta.env.BASE_URL`に従う。mockは未知GETでもネットワークへ落とさない。位置未確認を持つplaceだけnull座標を許容し、通常の壊れた座標は引き続き拒否する。
- [ ] **Step 4 — ビルド境界を実装。** `dev:demo`と`build:demo`を追加しbase=/Kakei/、outDir=dist-demo、DEMO publicDirを選ぶ。通常のpublic資源は必要なロゴをDEMO側へ複製し、hash一致を検証する。通常build/既存mockにはsnapshot importを入れない。
- [ ] **Step 5 — GREENとAPI回帰を確認。** Run `npm test --prefix front`。Expected: 全PASS。各fetch差し込み契約・既存mockテストが維持される。
- [ ] **Step 6 — コミット。** Expected: `feat: serve demo records through browser mock API`。

### Task 3: 全画面を閲覧専用にする

**Files:** Modify `front/src/{app/App.jsx,useAgentChat.js,pages/{Dashboard,AgentChat,TransactionDetail,Trajectory}.jsx,components/layout/AppShell.jsx,components/agent/{AgentControls,AgentProposal}.jsx,components/receipts/ReceiptReview.jsx,components/transactions/{TransactionAddress,TransactionReceipts}.jsx,components/places/GooglePlaceResults.jsx}`, `front/index.html`, `front/styles.css`。Create `front/src/components/places/DemoPlaceResults.jsx`, `front/src/tests/{App.demo,AgentChat.demo,DemoPlaceResults}.test.jsx`。

**Interfaces:** Consumes runtime.readOnly/getInitialMonth/snapshotTime/assetUrl/receiptUrlと既存session.select。Produces readOnly props（既定false）、DEMOでは静的に表示する地点カード。通常のGooglePlaceResultsはapiFetch経由で既存取得を維持する。

- [ ] **Step 1 — 閲覧専用統合テストを書く。** runtimeをDEMOにmockし、実App＋mock APIで次を検証する。
  ```js
  expect(screen.getByText('DEMO・閲覧専用')).toBeVisible();
  expect(screen.queryByRole('button',{name:'取引を追加',exact:true})).toBeNull();
  expect(screen.queryByRole('button',{name:'予算を設定',exact:true})).toBeNull();
  expect(requests.every(r=>r.method==='GET')).toBe(true);
  ```
  初期最新月、既存localStorage内に違うデータがあっても41件snapshotを使うこと、月変更・検索・詳細・CSV、直接/edit・/deleteを閲覧へ案内、保留／期限切れ変更案の状態をsnapshotTimeで固定、レシートリンクが/Kakei/配下、会話選択はGETのみ、原本の閲覧と0会話の空状態を検証する。
- [ ] **Step 2 — REDを確認。** Run `npm test --prefix front -- src/tests/App.demo.test.jsx src/tests/AgentChat.demo.test.jsx src/tests/DemoPlaceResults.test.jsx`。Expected: 表示・操作制限がなくFAIL。
- [ ] **Step 3 — 閲覧専用分岐を実装。** Appがruntimeの初期月とreadOnlyを渡し、書き込みdialog/routes/handlerの入口を遮断する。新規会話・削除・送信composer・保留案の書込actions・住所編集をDEMOでは表示しない。会話一覧と差分、ReceiptReviewの読み取り結果は残す。Agent状態available=falseでも履歴をGETで選べるようにし、原本URLを全箇所でruntimeへ統一する。DEMO静的地点カードは独立出典と位置未確認を表示し、GooglePlaceResultsを起動しない。
- [ ] **Step 4 — base付き資源とコピーを適用。** AppShellのロゴとfaviconのURLをbase対応にする。小さなDEMO表記をトップバーへ置き、通常のカード順を変えない。空・エラー・再試行とkeyboard/focusを維持する。
- [ ] **Step 5 — GREENと全UI回帰を確認。** Run `npm test --prefix front`。Expected: 全PASS、通常版の編集・削除・Agent・レシートテストもPASS。
- [ ] **Step 6 — コミット。** Expected: `feat: present demo screens in read-only mode`。

### Task 4: 東京の地図・文字・スタイルを同梱する

**Files:** Create `tools/demo/{prepare-map.mjs,README.md}`, `front/demo/maps/{manifest.json,style.js,archive-source.js}`, `front/demo/public/maps/{tokyo.pmtiles,fonts/*,licenses/*}`, `front/src/lib/{demo-map-assets,archive-source}.test.js`。Modify `front/package.json`, `front/package-lock.json`。

**Interfaces:** Consumes specの範囲/zoom/50 MiBとsnapshot地点。Produces 地図manifest（版、bounds、tileMaxZoom14、displayMaxZoom16、bytes、sha256、取得元・ライセンス）、`createOfflineStyle(baseUrl:string):StyleSpecification`、`createArchiveSource(url:string,{maxBytes:number,fetchImpl?:typeof fetch}):Source`（PMTiles SourceのgetKey/getBytes契約）。

- [ ] **Step 1 — 資源と取得処理のテストを書く。** 有効な最小archive fixtureとHTTP応答stubを使用する。
  ```js
  expect(style.sources.basemap.url.startsWith('pmtiles://http://localhost:')).toBe(true);
  expect(allResourceUrls(style).every(isSameSite)).toBe(true);
  expect(mapManifest.bytes).toBeLessThanOrEqual(50*1024*1024);
  expect(await source.getBytes(2,3)).toMatchObject({data:bytes.slice(2,5).buffer});
  ```
  正しい206/Content-Range、不正206、200全体応答、複数同時getBytesの全体取得は1回だけ、上限超過、Abort、404、失敗後の再試行、外部URL拒否を検証する。地図・フォント・license欠落とhash不一致は失敗。
- [ ] **Step 2 — REDを確認。** Run `npm test --prefix front -- src/lib/archive-source.test.js src/lib/demo-map-assets.test.js`。Expected: 未実装でFAIL。
- [ ] **Step 3 — 必要な依存と取得手順を用意する。** 公式配布のMapLibre、pmtiles、対応版Protomaps styleを確認しexact版をnpm lockに固定。pmtiles CLIは公式の検証可能な配布を使う。Protomaps固定buildからbboxをzoom0〜14でextractしverify、50 MiBを超えれば仕様を黙って変えず容量を報告する。東京都本土の範囲とsnapshot地点の包含を公式境界データ／地点情報から確認し、地図manifestへ記録する。
- [ ] **Step 4 — 全表示資源をローカル化する。** PMTiles、必要なsprite、日本語対応のOFLフォントとライセンスを同梱する。MapLibreのローカル文字描画で日本語・英数字が表示される設定にし、styleから外部glyph/sprite URLを除く。資源のhashと再生成コマンドをREADMEへ記録する。runtime/build時に取得処理を走らせない。
- [ ] **Step 5 — boundedなarchive sourceを実装する。** 同一サイトのURLだけ許可。正常206は必要なbytesを返し、200は50 MiB以内の全体archiveとして一度だけ保持しsliceする。Content-Lengthだけを信用せず実際のbytesも検証する。失敗したpromiseを永続cacheしない。getBytesのAbortSignalを扱い、別の利用中の要求を壊さない。
- [ ] **Step 6 — GREENを確認してコミット。** Run `npm test --prefix front`。Expected: 全PASS、manifestに範囲・版・hash・出典・license、外部URLなし。Commit `feat: bundle Tokyo basemap for API-free demo`。

### Task 5: 同梱地図に軌跡を表示する

**Files:** Create `front/src/components/trajectory/OfflineTrajectoryMap.jsx`, `front/src/lib/{offline-trajectory.js,offline-trajectory.test.js}`, `front/src/tests/OfflineTrajectoryMap.test.jsx`。Modify `front/demo/runtime.js`, `front/trajectory.css`。

**Interfaces:** Consumes `{day,selectedEventId,onSelectEvent}`、Task4のstyle/source/manifest。Produces GoogleTrajectoryMapと同じpropsのcomponent、`offlineFeatures(day):{stops:FeatureCollection,segments:FeatureCollection}`。訪問番号は元events index+1を維持し、null座標を飛ばしても振り直さない。

- [ ] **Step 1 — 描画と選択のテストを書く。** MapLibre mockと純粋関数を使う。
  ```js
  expect(offlineFeatures(day).stops.features.map(f=>f.properties.number)).toEqual([1,3]);
  expect(offlineFeatures(day).segments.features).toHaveLength(0); // 中間地点未確認
  expect(mapOptions.maxZoom).toBe(16);
  expect(mapOptions.maxBounds).toEqual([[138.90,35.45],[139.95,35.95]]);
  ```
  全13日、0/1/複数地点、住所needs_review、推定座標、未確認地点、選択反映、marker操作からevent ID通知、日付切替とresize、アンマウント解放、reduce motion、WebGL不可、ロード失敗→再試行の成功を検証する。
- [ ] **Step 2 — REDを確認。** Run `npm test --prefix front -- src/lib/offline-trajectory.test.js src/tests/OfflineTrajectoryMap.test.jsx`。Expected: 未実装でFAIL。
- [ ] **Step 3 — 純粋変換とcomponentを実装。** MapLibreのGeoJSON source/layerで色付き区間、番号付き選択markerを表示する。点・区間の公開範囲をmanifestで制約し、日付変更でfitBounds(maxZoom16)、段階色はstageColorを再利用。選択で無関係なmap再生成をしない。必要なイベント・marker・protocolはcleanupする。
- [ ] **Step 4 — エラーと読み上げを実装。** 初期準備、地図失敗と再試行、WebGL不可を表示し、時系列は利用可能にする。keyboardでmarkerを選べ、地図の下の時系列からも選べる。出典とlicenseを常時読めるようにする。既存の時系列スクロール構成を維持する。
- [ ] **Step 5 — GREENと通常地図回帰を確認。** Run `npm test --prefix front`。Expected: 全PASS、GoogleTrajectoryMapテストもPASS。
- [ ] **Step 6 — コミット。** Expected: `feat: render demo trajectories on local Tokyo map`。

### Task 6: 公開ビルドを検証しPages配信を準備する

**Files:** Create `front/scripts/{validate-demo,serve-demo-check}.mjs`, `front/src/lib/demo-build.test.js`, `.github/workflows/demo-pages.yml`, `README.md`。Modify `front/package.json`, `front/vite.config.mjs`, `front/README.md`。

**Interfaces:** Consumes snapshot/地図manifest、DEMO build、runtimeのbase契約。Produces `validate-demo`スクリプト、静的なdist-demo、Pages workflow（データ再生成なし）。

- [ ] **Step 1 — ビルド隔離の失敗テストを書く。** 一時成果物に対して検証する。
  ```js
  expect(()=>validateDemoBuild(fixtureWithMissingReceipt)).toThrow();
  expect(()=>validateDemoBuild(fixtureWithRootAbsoluteAsset)).toThrow();
  expect(()=>validateDemoBuild(fixtureWithBadMapHash)).toThrow();
  expect(normalArtifacts).not.toContain(receiptId);
  ```
  /Kakei/対応HTML・遅延chunk・原本・地図・fontsの存在、SQLite/.env/認証キーの混入拒否、正常版のpublic出力へDEMO原本をコピーしないことを検証する。依存内の未実行URL文字列だけで外部通信と誤判定せず、実際の通信はTask7で検証する。
- [ ] **Step 2 — REDを確認。** Run `npm test --prefix front -- src/lib/demo-build.test.js`。Expected: 未実装でFAIL。
- [ ] **Step 3 — validatorとworkflowを実装。** prebuild検証はsnapshotと地図を読んで整合性／hashを確認し、export/prepare-mapを実行しない。workflowは公式Actionsを検証可能な版に固定、npm ci/test/build:demo後upload-pages-artifact/deploy-pagesを実行。権限はcontents:read/pages:write/id-token:write、concurrency=pages。default branchのpushとworkflow_dispatchを対象にし、データ／地図の取得元へCIから通信しない。
- [ ] **Step 4 — READMEを完成させる。** DEMO URL、閲覧専用、公開snapshotの時刻・対象、地図範囲・zoom・license、dev:demo/build:demo、通常版との違い、手動エクスポート・再生成を記載する。
- [ ] **Step 5 — 通信確認用の静的サーバーを用意する。** `node front/scripts/serve-demo-check.mjs --port 8770`でdist-demoを/Kakei/に配信する。Content-Security-Policyで外部のconnect/script/img/font/workerを禁止し、同じoriginの資源と必要なblob workerだけを許容する。/api/要求はエラーにして記録し、HTTP要求とRange応答を確認できるようにする。サーバーはユーザーのDB/APIに接続せず、ブラウザ操作もしない。
- [ ] **Step 6 — GREENと両ビルドを確認。** Run `npm test --prefix front`、`npm run build --prefix front`、`npm run build:demo --prefix front`、`backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py'`、`git diff --check`。Expected: 全PASS、通常版/DEMOの出力を分離、secretなし、snapshot/地図hash一致。
- [ ] **Step 7 — コミット。** 通常版distにソース変更が反映された場合はその更新も含める。dist-demoは再現可能な生成物としてignoreし、PagesはCIでビルドする。Expected: `build: prepare verified read-only GitHub Pages demo`。

### Task 7: ブラウザで閲覧と外部通信なしを確認する

**Files:** 必要な検証結果はこの計画のscratch workspaceへ保存する。修正が必要なら対象のタスクへ戻り、RED→GREENを確認する。新しいブラウザ操作用CLIを製品へ追加しない。

**Interfaces:** Consumes 一貫したDEMO成果物、Task6の確認用静的サーバー。Produces 公開前の検証結果。通常版の実DBは利用しない。

- [ ] **Step 1 — 一時ポートで配信する。** Run `node front/scripts/serve-demo-check.mjs --port 8770`、/Kakei/配下をcua_replで開く。Expected: Python APIと.envなしで表示。ユーザーの通常版サーバーとDBをテストに使わない。
- [ ] **Step 2 — PCと電話幅を確認する。** cua_replで1440x900と375x812を検証。最新取引月の収支と保存予算、全41件、検索／詳細、両原本、全13日、ピン／時系列選択と日本語地図、3会話と読み取り結果を確認。Expected: 最初に月と収支、横あふれなし、focus/scroll正常、書き込み・送信入口なし。最後にviewportをresetする。
- [ ] **Step 3 — 外部通信を検証する。** 全ページと地図の確認後、cua_replのサポートされたread-only観測でresourceの要求先とconsoleを確認し、サーバーログも読む。Expected: CSP違反や外部API/CDN/font/telemetry要求なし、/api/ HTTP漏れなし。Range無効の同じ確認用サーバーでも地図が表示できることを確認する。GUI操作はcua_replだけを使う。
- [ ] **Step 4 — 結果を記録し全suiteで完了する。** この計画のledgerへ表示・通信・原本・件数・未確認位置を記録する。Run `npm test --prefix front`と`backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py'`。Expected: 全PASS、必要な公開前確認に未実施項目なし。元のDBと通常版サーバーは維持される。

## 全タスク完了後のレビュー・統合・公開

実行スキルの手順でplan/spec/ledgerとbranch全体をfresh reviewerへ渡し、Review Focusを照合する。Critical/ImportantはRED→GREENと全suiteで修正する。Nativeの場合は実行スキルの1回の最終レビューだけとし、Task7で重複dispatchしない。

finishing-a-development-branchで統合方法を確認し、選択に従い統合・pushする。ユーザーはGitHub Pages公開を依頼済み。承認済みの公開データとworkflowをGitHubへ送り、必要なPages設定を公式CLI/APIまたはUIで行う。権限不足・追加認証があれば具体的に報告し、秘密キーを新設しない。

配信後は実際のPages URLで概要、保存日の地図、日本語、会話、原本をcua_replで確認し、同じoriginのRange応答と実際の要求先を検証する。公開URLで閲覧できることを確認してから完了を報告する。位置未確認や容量制約が残れば対象を明記し、公開待ちや実施できなかった確認を成功したと偽らない。

## Self-review

Specのsnapshot・mock・readonly・map・Pages・検証をTasks1〜7へ対応付けた。runtimeとsnapshotの名前はInterfacesに揃え、Review Focus5項目のテストを各所有Taskへ追加した。公開準備と通常版の回帰を同じ計画で検証し、データ再生成はCIから分離する。地図の入手・独立した2地点の照合は実装時の作業として明記し、未確認を偽の座標で埋めない。
