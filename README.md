# Kakei

家計簿・訪問軌跡・Agent Chatをまとめたアプリです。通常版の起動と保存先は[backend/README.md](backend/README.md)、フロント開発は[front/README.md](front/README.md)を参照してください。

公開DEMOの配信先: https://kabuxx.github.io/Kakei/ 。GitHub Pagesの有効化と初回公開後に利用できます。画面は「DEMO・閲覧専用」で、公開snapshotを表示します。月変更、検索、フィルター、詳細、CSV、会話選択、レシート原本表示、地図操作ができます。取引・予算・軌跡の変更とAgent送信はありません。

snapshotは2026-10-04 17:18:05 UTC（2026-10-05 02:18:05 JST）時点です。取引41件、軌跡13日・訪問38件・地点13件、会話3件・メッセージ8件、レシート原本2件、予算6カテゴリを含み、初期表示は最新取引月の2026年10月です。Google由来の2店舗は独立した施設情報・OpenStreetMapで照合し、建物の代表点として表示します。期限付きGoogle座標cacheやGoogleの生応答を公開しません。

地図は東京本土（23区＋多摩、島しょ除外）を含む138.90,35.45,139.95,35.95の矩形です。矩形内の近隣地域も表示します。保存zoomは0〜14、表示上限は16、PMTilesは44,888,591 bytesです。道路・鉄道・水域・主要地名と日本語フォントを同じサイトから読みます。位置のある参照地点12件は範囲内で、未使用の福岡地点1件は表示範囲外です。OpenStreetMap/ProtomapsはODbL-1.0、Natural Earthはpublic domain、Noto Sans JPはOFL-1.1です。[地図manifest](front/demo/maps/manifest.json)と[ライセンス](front/demo/public/maps/licenses/MAP-LICENSE.txt)に出典があります。

```sh
npm ci --prefix front
npm run dev:demo --prefix front
npm run build:demo --prefix front
node front/scripts/serve-demo-check.mjs --port 8770
```

開発用DEMOはViteの表示URLの`/Kakei/`、静的検証は`http://127.0.0.1:8770/Kakei/`を開きます。静的サーバーは外部接続をCSPで禁止し、API要求をエラーとして記録します。`--no-range`を付けるとPMTilesの全体取得fallbackを検証できます。DBやAPIへは接続しません。

通常版の`npm run build --prefix front`はAPIを利用する`front/dist/`を生成します。DEMOの`build:demo`はコミット済みsnapshot、原本、地図、フォントを検証して`front/dist-demo/`へ出力します。通常版のpublicにはDEMO原本をコピーしません。通常版のlocalStorageもDEMOは読みません。`dev:mock`は既存の編集可能なメモリ上のmockのままです。

snapshot再生成は手動です。管理者は公開内容と件数の差分、原本、独立した座標根拠を確認し、読み取り専用SQLiteバックアップから別の出力先にエクスポートしてください。実DBを変更する手順ではありません。

```sh
backend/.venv/bin/python backend/export_demo.py \
  --db /path/to/readonly-backup.sqlite3 \
  --output /path/to/review-demo \
  --curated-places front/demo/data/curated-places.json
```

確認した`data/snapshot.json`・`data/manifest.json`と`public/demo-data/receipts/`を対応する`front/demo/`へ反映します。件数や公開対象の差分を記録してください。地図の取得・範囲抽出・フォント入手はCIから実行せず、出典・hash・licenseを確認した入力を手動で用意します。範囲・zoomを維持した元PMTilesから建物とPOI層を除く再梱包は次の明示操作です。

```sh
node tools/demo/prepare-map.mjs repack /path/to/tokyo-original.pmtiles /path/to/review-tokyo.pmtiles
node tools/demo/prepare-map.mjs validate
npm run validate:demo --prefix front
```

新しい地図やフォントを採用する際は`front/demo/maps/manifest.json`のbytes/hash/出典/範囲包含確認も更新し、検証してからコミットします。再梱包だけではmanifestは更新されません。

Pages workflowはmainへのpushまたは手動起動で`npm ci`、フロントテスト、検証付きDEMOビルドを実行します。データ再生成や外部地図照合は行いません。公開する前にリポジトリ所有者がPagesのSourceをGitHub Actionsへ設定する必要があります。`dist-demo`はignoreし、CIの成果物を配信します。
