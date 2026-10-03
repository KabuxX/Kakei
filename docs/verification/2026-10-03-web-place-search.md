# Web店舗検索への移行検証

2026-10-03。ブランチ `feat/web-place-search`。実装は隔離worktreeで行い、稼働アプリのDBと `.env` は変更していない。

## 検証結果

- Backend: `python -m unittest discover -s backend/tests` — 231件成功。
- Front: `npm --prefix front test` — 21ファイル、102件成功。
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

## 実API確認の制限

実APIの通し確認は未実施。ルート `.env` にはOpenAI・通常モデル・地図表示用Mapboxトークンがあるが、`MAPBOX_GEOCODING_ACCESS_TOKEN` が未設定。既存トークンを専用設定にも使うか利用者へ質問中。`.env` を無断変更せず、課金資格を変更しない。外部通信は0件。この記録の店名・住所・座標は合成fixtureであり、実店舗の確認結果ではない。

`KAKEI_AGENT_SEARCH_MODEL` は未設定時に既存モデルへフォールバック。Web検索のモデル対応状況とMapbox永久保存モードの利用資格は実接続時に確認が必要。キーは表示しない。

## 制限と互換性

検索はWeb調査→ツールなし構造化→Mapbox永久保存モードの住所照合。都道府県や国の固定なし。住所を十分に照合できなければ未確認候補として残し、選択させない。旧検索は閲覧できるが、新方式の再利用対象外。

turn120秒・リース130秒。検索85秒かつturn終了10秒前。Web3回/抽出3回/住所10件、住所同時2。HTTP512 KiB、候補8 KiB、結果40 KiB、検索256 KiB、履歴32 KiB、要約8 KiB。超過時の省略・部分結果を保存する。

## 実装上の判断

- Task 5: `test_agent_places.py` のprovider非依存テストとfixtureは残した。削除すると候補選択・改ざん拒否の既存検証と旧履歴fixtureのimportが失われるため。判断が誤りなら旧名のテストファイルが残ることがコストで、製品のGeoapify依存は残らない。

独立レビューはこの検証後に実施し、結果を追記する。
