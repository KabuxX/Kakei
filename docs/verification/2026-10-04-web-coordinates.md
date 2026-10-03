# Web座標検索の検証 — 2026-10-04

## 変更

地理検索APIを除去し、OpenAI Web検索と引用先の公開HTTPSページを使用。店舗名・住所に対応する本文の緯度経度、構造化geo、既知の店舗ピンURLを検証する。掲載値がない場合は検証済み施設・直線距離と8方位・小さな地区を基準に推定する。

新候補は明示確認が必要。推定の基準・出典・状態は保存後も保持。旧Mapbox地点、提案、履歴の読込を維持する。Mapboxは地図表示に使用。

## 自動検証

- backend: 300 tests PASS（Python 3.14、共有venv、すべてfixture/一時DB）。既存テストでSQLite ResourceWarningあり、失敗なし。
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
- 外部サイトの互換性・DNS・モデルの変動は、既存の実通信記録と今回の固定テストを根拠に判断。レビュー自体はネット接続なし。サイト変更で取得できなくなる可能性は残る。
- 画面とMapboxの表示は実装者のdesktop/phone実画面検証を根拠に判断。レビュー担当の独立ブラウザー検証はなし。未検証の端末で差が出る可能性は残る。
- 生成されたdistはビルドとブラウザーテストで判断し、全ファイルの手動レビューは省略。生成ツール固有の問題を見逃す可能性は残る。
- 地理APIの禁止は既知ホスト・パスと公開HTTPSの接続制限で判断。世界中の全エンドポイントの判別は保証しない。未知のAPI形式には禁止規則の追加が必要になる可能性がある。
- 計画の検索入力に欠けていたvisit_dateとその根拠を追加。仕様3.3の過去の所在地の区別を満たすため。日付ごとに別の検索になり、探索回数が増える可能性がある。
- 検証全体の外側タイムアウトを外し、各公開ページ要求の共有予算・期限とターン上限で制限。外側キャンセルで取得済み根拠が消えるため。追加の外部処理は同じ予算へ必ず登録する必要がある。

## 最終レビューと修正

独立レビューを1回実施し、重要な8指摘を1回の修正工程で対応。bool座標とページ別履歴の欠落も、誤った位置・原因調査への影響から重要に引き上げた。保留した軽微指摘なし。再レビューは行わず、各再現テストの失敗→成功と全体テストで検証。

| 指摘 | RED→GREENのテスト |
| --- | --- |
| 親section・div・複数見出しから別店舗の座標を借用 | test_nested_and_div_only_stores_do_not_lend_coordinates |
| 否定された施設内・相対方向の主体を誤認 | test_negated_building_and_reverse_relative_relationship_are_rejected（英語の肯定関係も別テストで維持） |
| 同一URLの出典ID統合で座標根拠が無効化 | test_same_url_estimate_sources_rebind_and_remain_selectable |
| 後から取得した施設hintの出典IDが消失 | test_same_url_relationship_discovered_later_keeps_resolvable_ids |
| 上限・期限で取得済み候補を喪失 | test_limit_after_success_preserves_verified_coordinates / test_verification_deadline_preserves_page_result_and_history |
| 過去の取引日が検索へ渡らない | test_visit_date_is_grounded_and_warns_before_selection / test_research_includes_visit_date_and_historical_location_instruction |
| JSONのboolを緯度経度として採用 | test_boolean_geo_is_not_a_coordinate |
| ページ別要求・リダイレクト・失敗の履歴が欠落 | test_failed_redirect_keeps_bounded_request_history / test_verification_page_history_is_persisted |

保存前の候補は、visit_dateを渡した場合に「訪問日当時の所在地は未確認」と明記し、既存の確認済み地点を再利用する場合も再確認を求める。推定関係は明示的な施設内、地区内、直線距離と方角のみを採用。曖昧なページ構造や文章は位置未確認になる場合がある。

最終修正後: backend 300 / front 131 / browser 22件成功、build・git diff --check成功。フロント全テストの初回はsandboxのlisten EPERMで失敗し、許可された一時サーバーで再実行して成功。ブラウザーも別ポートの一時DBを使用し、実アプリのDBは変更していない。
