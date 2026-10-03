# Web座標検索の検証 — 2026-10-04

## 変更

地理検索APIを除去し、OpenAI Web検索と引用先の公開HTTPSページを使用。店舗名・住所に対応する本文の緯度経度、構造化geo、既知の店舗ピンURLを検証する。掲載値がない場合は検証済み施設・直線距離と8方位・小さな地区を基準に推定する。

新候補は明示確認が必要。推定の基準・出典・状態は保存後も保持。旧Mapbox地点、提案、履歴の読込を維持する。Mapboxは地図表示に使用。

## 自動検証

- backend: 288 tests PASS（Python 3.14、共有venv、すべてfixture/一時DB）。
- front: 131 tests PASS。
- browser: 22 tests PASS（一時DB）。1440×900 / 375×812で確認解除、位置確認、選択、保存、再読込、推定表示、出典、距離説明と横スクロールなしを検証。
- build PASS。地図helperの破線リング作成・削除と住所再確認時の座標除外も検証。

## 実API

既存の `gpt-6-luna` とキーを使用。実DB・.envは変更していない。各試行はWeb最大3・公開ページ最大8要求に制限し、一時DBを廃棄した。実検索語、出典URL、日時、通信上限、結果は [live-summary.json](2026-10-04-web-coordinates/live-summary.json)。

最初の2試行は店舗の出典を取得したが抽出で候補が0件になった。郵便番号・国名・Markdownの表記と不完全な施設hintで店舗住所まで棄却する不具合を再現テストで修正した。

修正後（03:26:35 JST、66.13秒）はWeb3/抽出3/公開ページ6要求で1候補を取得した。店舗名・住所と同一Restaurantの構造化geoを検証。

- 店舗: ドトールコーヒーショップ 西鉄福岡駅店
- 住所: 〒810-0001 福岡県福岡市中央区天神2-11-3
- 座標: `[130.39893258983207, 33.590460407060675]`（経度・緯度）
- 掲載元: [食べログの同店舗ページ](https://tabelog.com/fukuoka/A4001/A400103/40034161/)
- method: structured_geo / status: published / verification: needs_confirmation。

一部ページが512KiB上限を超え、検索全体はpartial、未確認理由はpage_too_large。入口や実際の精度は未確認で、自動保存していない。固定テストの成功は実サイト全体の取得成功を保証しない。専用Mapboxキーを外してもplacesAvailable=true。新経路に地理検索API要求はない。

## 画面確認

[確認カード（desktop）](2026-10-04-web-coordinates/confirmation-desktop.png) / [phone](2026-10-04-web-coordinates/confirmation-phone.png)、[保存後の軌跡（desktop）](2026-10-04-web-coordinates/trajectory-desktop.png) / [phone](2026-10-04-web-coordinates/trajectory-phone.png)を目視した。

既存の地図表示用トークンで、別の一時DBに合成fixtureの推定地点を表示。[地図（desktop）](2026-10-04-web-coordinates/map-preview-desktop.png) / [phone](2026-10-04-web-coordinates/map-preview-phone.png)を目視し、破線リング1件、地図canvasあり、エラーなし。これは地図描画の検証であり、fixtureの座標は実店舗を裏付けるものではない。

## 実装中の判断

- 検証結果に店舗同一性、検証済みhint、ページ内リンクを内部項目として追加。推定と短縮リンクへ原文の根拠を渡すため。誤りなら内部呼出側の修正が必要。
- HTML/JSONの小さな生成fixtureをテスト内に置いた。別店舗の混在ケースを読みやすくするため。複雑な実ページでは追加fixtureが必要になる可能性がある。
- 推定関数はモデルのhintsではなく内部verifiedHintsを受け取る。ページ検証を省略できないようにするため。呼出側には明示の検証段階が必要。
