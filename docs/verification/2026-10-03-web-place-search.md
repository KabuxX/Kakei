# Web店舗検索への移行検証

2026-10-03。ブランチ `feat/web-place-search`。実装は隔離worktreeで行い、稼働アプリのDBは変更していない。利用者の許可後、ルート `.env` に既存のMapboxトークンを専用変数として追加した。

## 検証結果

- Backend: `python -m unittest discover -s backend/tests` — 237件成功。
- Front: `npm --prefix front test` — 21ファイル、103件成功。
- Build: `npm --prefix front run build` — 成功。既存Mapboxチャンクの500 kB警告あり。生成distはコミットしない。
- Browser: `playwright.agent-search.config.cjs`、一時SQLite、port8767 — 15件成功。
- `git diff --check` 成功。製品コードからGeoapify通信・環境依存がなくなったことを検索確認。

ブラウザでは出典付き候補を選択して保存、軌跡で店舗出典とMapboxの補間表示を確認した。未確認候補にradioはなく、そのIDで選択APIを呼ぶと400。変更案なし応答の引用は会話の再読込後も維持。旧形式の候補も選択・保存できる。

初回の新ブラウザfixtureは時刻根拠の無効値を含んだため選択後の検証で失敗した。既存契約の `exact` に修正。電話幅では会話一覧が別UIになるため、会話再読込の操作をdesktopに戻して検証した。製品コードをテストに合わせて緩和していない。

## 画面確認

1440pxと375pxで出典・未確認理由・手動入力を撮影し目視確認。横スクロールなし。出典リンクはradioの外側、座標入力へfocusすると会話のスクロール領域内で表示される。店舗情報と座標帰属は別表示。既存のメッセージ入力欄を維持。

- [Desktop](2026-10-03-web-place-search/web-evidence-desktop.png)
- [Phone・出典](2026-10-03-web-place-search/web-evidence-phone.png)
- [Phone・座標入力](2026-10-03-web-place-search/web-manual-phone.png)

## 実API確認

利用者の許可により、既存の地図表示用トークンを `MAPBOX_GEOCODING_ACCESS_TOKEN` にも設定した。`KAKEI_AGENT_SEARCH_MODEL` 未設定のため既存 `gpt-6-luna` を使用。追加課金設定の変更なし、キー表示なし。

実APIはWeb調査2要求（内部アクション計3: search 2/open_page 1）、構造化4要求（取得済みレポートの再処理2を含む）、Mapbox住所2要求。上限のWeb3回・Mapbox5住所以内。最初のsandbox内試行は外部接続できず、許可後に実接続を実施。

- OpenAI: HTTP200。公式店舗ページ `https://shop.doutor.co.jp/doutor/spot/detail?code=2010774` と「〒810-0001 福岡県福岡市中央区天神2-11-3」を取得。
- Webのusage: 初回 input8406/output200/total8606、2回目 input10205/output197/total10402。構造化の再処理はtotal883、932、最終947。初回構造化のusageは記録していない。
- 最終検索取得時刻: UNIX 1791034374.3405519（2026-10-03 JST）。名称・住所・引用を1つの店舗として抽出でき、一時DBに保存。
- Mapbox: `permanent=true` でHTTP200。最上位はaddress/rooftopだが、番地・街区・丁目が `unmatched`、confidenceなし。ほかにblock/別番地/localityなどが返ったため自動確定せず、出典付き「位置未確認」として残した。永久保存要求のHTTP成功は確認したが、契約資格全体を別途監査したものではない。

実接続で、国コードの大文字JPと、name/branchが別々に返る場合に候補が消える問題を検出。国コードは大小文字を正規化し、支店の結合は同じ引用文に完全店名が連続して存在する場合のみ認める。両方にRED→GREENの回帰テストを追加した。

店舗検索は成功したが、この店舗の座標は自動確定していない。手動座標入力が必要。合成fixtureの座標を実店舗の位置として扱っていない。

## 制限と互換性

検索はWeb調査→ツールなし構造化→Mapbox永久保存モードの住所照合。都道府県や国の固定なし。住所を十分に照合できなければ未確認候補として残し、選択させない。旧検索は閲覧できるが、新方式の再利用対象外。

turn120秒・リース130秒。検索85秒かつturn終了10秒前。Web3回/抽出3回/住所10件、住所同時2。HTTP512 KiB、候補8 KiB、結果40 KiB、検索256 KiB、履歴32 KiB、要約8 KiB。超過時の省略・部分結果を保存する。

## 実装上の判断

- Task 5: `test_agent_places.py` のprovider非依存テストとfixtureは残した。削除すると候補選択・改ざん拒否の既存検証と旧履歴fixtureのimportが失われるため。判断が誤りなら旧名のテストファイルが残ることがコストで、製品のGeoapify依存は残らない。

## 独立レビューと修正

独立レビュアー（gpt-6-astra）による全ブランチレビューを1回実施。Criticalなし、Important4件、Minorなし、判断保留なし。4件とも修正し、各回帰テストの失敗を確認してから修正を適用した。再レビューは行わず、全体のテストとビルド・ブラウザ操作を再実行した。

1. 別支店の住所／引用の後に書かれた住所を根拠にできる問題。支持範囲は引用位置までとし、店名と住所が直接対応する表記だけを受理。未確認・推定を含む根拠は不採用。`test_citation_cannot_bind_another_branch_or_later_address` RED→GREEN。
2. 番地末尾の「の3」を建物名として省略できる問題。住所が完全一致するか、空白で明確に区切られた建物名・階だけを省略可能にした。`test_address_suffix_cannot_hide_a_missing_house_number` RED→GREEN。
3. 同一URLの引用が重複IDとなり選択できない問題。候補ごとのsourcesをURLで重複排除。選択処理まで確認。`test_duplicate_url_citations_remain_selectable` RED→GREEN。
4. 結果40 KiBの上限で候補が無言で消える問題。副次出典→候補の順で丸ごと省略し、集約出典を残る候補と同期。候補・出典の省略件数、partial、理由を保持し画面に表示。`test_result_size_omissions_are_partial_and_explicit` とフロント省略表示テスト RED→GREEN。

最終結果: Backend237件、Front103件、Browser15件成功、build・diff check成功。記録済み実APIの引用・抽出結果も通信なしで再処理し、住所付き店舗が維持されることを確認した。追加の実API通信なし。

保留した軽微指摘: なし。
