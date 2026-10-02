# 生活軌跡サンプルと Mapbox の設定

軌跡ページは、東京の実在する店舗・駅を使った **2026年9月1日〜30日の架空のサンプル** を表示します。購入、金額、訪問時刻、移動順は実際の行動記録ではありません。地点間は直線で結び、距離もその線から求めた概算です。道路・線路上の実経路ではありません。

## データの役割

- `front/src/data/old-samples.json` — 以前の16件を保存した記録。初期化には使いません。
- `front/src/data/september-transactions.json` — 新規 DB の初期化で概要ページに入る取引。軌跡でも取引 ID を照合します。
- `front/src/data/september-timeline.json` — 軌跡専用の地点、時刻、取引 ID、移動区間。各地点に住所と公式情報への URL を付けています。

既存の SQLite DB は変更しません。既に保存した取引や削除した取引はそのまま残り、軌跡ページは常に上記の固定サンプルを表示します。家賃や定期券の購入など、位置を示さない取引は訪問地点に加えません。画面の支出合計には、その日の取引として含めます。

## Mapbox の公開トークン

[Mapbox GL JS の公式手順](https://docs.mapbox.com/mapbox-gl-js/guides/get-started/use-with-npm/)に従い、Mapbox アカウントの公開アクセストークンを用意します。リポジトリ直下の `.env` に `VITE_MAPBOX_ACCESS_TOKEN` を設定します。Vite は開発時とビルド時にこのファイルを読みます。

```sh
VITE_MAPBOX_ACCESS_TOKEN=pk.your-public-token
```

`.env` は Git の対象外です。この値はブラウザ用のビルドに含まれるため、`pk.` で始まる公開用トークンを使用してください。地図は Mapbox GL JS、地点と線は deck.gl、距離と表示範囲の計算は Turf.js を使用します。Mapbox の地図には出典表示が付きます。

背景地図は Mapbox Standard を使用し、地名ラベルは日本語、地図フォントは Noto Sans CJK JP を指定します。日本語文字にも地図スタイルのフォントを適用するため、端末の代替フォントによるグリフ生成は無効にしています。各日の区間は順番ごとに色を変え、地図下の凡例と時系列の区間番号を対応させています。訪問地点の記録時刻は時系列に表示します。日本語訳がない地図ラベルは元の言語で表示される場合があります。

トークンがない場合、WebGL に対応していない場合、または地図の読み込みに失敗した場合も、日付の切替と時系列一覧は使えます。

## バックエンドなしで画面を確認する

概要と軌跡を新しいサンプルで確認する場合は、mock 環境を起動します。

```sh
cd front
npm run dev:mock
```

`http://127.0.0.1:5173/` の概要には `september-transactions.json`、軌跡には `september-timeline.json` が表示されます。mock 環境は保存済みの SQLite DB を読みません。
