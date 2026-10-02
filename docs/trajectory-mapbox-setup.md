# 生活軌跡サンプルと Mapbox の設定

軌跡ページは、東京の実在する店舗・駅を使った **2026年9月1日〜30日の架空のサンプル** を表示します。購入、金額、訪問時刻、移動順は実際の行動記録ではありません。地点間は直線で結び、距離もその線から求めた概算です。道路・線路上の実経路ではありません。

## データの役割

- `front/src/data/old-samples.json` — 以前の16件を保存した記録。初期化には使いません。
- `front/src/data/september-transactions.json` — 新規 DB の初期化で概要ページに入る取引。軌跡でも取引 ID を照合します。
- `front/src/data/september-timeline.json` — 軌跡専用の地点、時刻、取引 ID、移動区間。各地点に住所と公式情報への URL を付けています。

既存の SQLite DB は変更しません。既に保存した取引や削除した取引はそのまま残り、軌跡ページは常に上記の固定サンプルを表示します。家賃や定期券の購入など、位置を示さない取引は訪問地点に加えません。画面の支出合計には、その日の取引として含めます。

## Mapbox の公開トークン

[Mapbox GL JS の公式手順](https://docs.mapbox.com/mapbox-gl-js/guides/get-started/use-with-npm/)に従い、Mapbox アカウントのアクセストークンを用意します。Vite のビルド時に次の環境変数を指定してください。

```sh
cd front
VITE_MAPBOX_ACCESS_TOKEN=pk.your-public-token npm run build
```

トークンはソースコードや Git に保存しないでください。`VITE_` で始まる値はブラウザ用のビルドに含まれるため、公開可能なトークンを使用してください。地図は Mapbox GL JS、地点と線は deck.gl、距離と表示範囲の計算は Turf.js を使用します。Mapbox の地図には出典表示が付きます。

トークンがない場合、WebGL に対応していない場合、または地図の読み込みに失敗した場合も、日付の切替と時系列一覧は使えます。

## バックエンドなしで画面を確認する

取引 API を使わず軌跡だけ確認する場合は、ビルド済みの `front/dist` を静的に配信します。

```sh
python3 -m http.server 8765 --directory front/dist
```

`http://localhost:8765/#trajectory` を開いてください。概要の新規初期化は取引 API を使うため、この静的プレビューでは保存されません。
