# 作から計への作業完了報告：WebUI変換履歴Phase3実装（#438）

**報告日**: 2026-09-10
**報告者**: 作成ロール（作/saku）
**対象作業指示書**: 計から作への作業指示書_WebUI変換履歴Phase3実装_20260910.md（commit a500ca7）

## 完了報告

- #438実装: キーワード検索（FTS5+同期トリガー）・Markdownまとめ出力（チェックボックス選択+download_button）の実装 ✅ 完了
- 変更ファイル（未コミット、Git管理は計に依頼）:
  - `core/cli_workflow.py`（`ensure_history_table()` DDL拡張）
  - `webui.py`（`_render_history_tab()` UI拡張）
  - `tests/test_core_cli_workflow_history_fts.py`（新規、FTS5往復結合テスト5件）

## §3 完了条件コマンド実行結果（生ログ）

```
$ grep -q "CREATE VIRTUAL TABLE IF NOT EXISTS transcription_history_fts" core/cli_workflow.py && echo OK_FTS_TABLE
OK_FTS_TABLE

$ for op in INSERT UPDATE DELETE; do grep -qi "AFTER ${op}" core/cli_workflow.py && echo "OK_TRIGGER_${op}" || echo "MISSING_TRIGGER_${op}"; done
OK_TRIGGER_INSERT
OK_TRIGGER_UPDATE
OK_TRIGGER_DELETE

$ grep -q "transcription_history_fts.*rebuild\|rebuild.*transcription_history_fts" core/cli_workflow.py && echo OK_REBUILD
OK_REBUILD

$ grep -q "history_keyword" webui.py && echo OK_KEYWORD_UI
OK_KEYWORD_UI
$ grep -q "MATCH" webui.py && echo OK_FTS_QUERY
OK_FTS_QUERY
$ grep -q "history_select_" webui.py && echo OK_SELECT_CHECKBOX
OK_SELECT_CHECKBOX
$ grep -q "st.download_button" webui.py && echo OK_DOWNLOAD_BUTTON
OK_DOWNLOAD_BUTTON

$ uv run pytest -q 2>&1 | tail -5
..............................................................s......... [ 64%]
........................................                                 [100%]
111 passed, 1 skipped in 7.45s

$ grep -rq "MATCH" tests/ && echo OK_FTS_ROUNDTRIP_TEST_PRESENT
OK_FTS_ROUNDTRIP_TEST_PRESENT
```

## pytest件数（着手時→更新後）

- 着手時（原本ファイル内容に一時復元して計測、新規テストファイル除外）: `106 passed, 1 skipped`
- 更新後（新規テスト5件を含む全体）: `111 passed, 1 skipped`
- 差分: +5（新規追加分のみ、既存テストの回帰0件）

## 実装内容の要旨（予備調査からの変更点あり・要確認事項）

予備調査完了報告のFTS5仮想テーブル定義に**トークナイザ指定を追加**した。予備調査時点の定義（`tokenize`未指定＝既定の`unicode61`）で結合テストを実施したところ、**分かち書きされていない日本語文字列に対する部分一致検索が機能しないことを実測で確認**した（`unicode61`は空白等の区切り文字がない文字列を1トークンとして扱うため）。

対策として `tokenize='trigram'`（3文字連続n-gram、SQLite 3.34以降。本機`sqlite3.sqlite_version`は3.45.1で対応確認済み）を採用し、結合テスト5件全て合格を確認した。この変更は作業指示書§4「採用方式（予備調査どおり）」からの技術的補完であり、キーワード検索の対象カラム・トリガー構成・UI設計自体に変更はない。

**制約事項（完了報告として明記）**: trigram tokenizerは3文字未満のクエリでは検索結果が得られない（n-gramの最小単位が3文字のため）。1〜2文字のキーワード検索は現仕様では非対応。UI上での制約表示等が必要か、計の判断を仰ぎたい。

## Git管理依頼

計ロールに以下のファイルのGit管理を依頼します（ブランチ: `feature/webui-history-phase3-search-export-20260910`）:
- `core/cli_workflow.py`（更新）
- `webui.py`（更新）
- `tests/test_core_cli_workflow_history_fts.py`（新規）
- 本完了報告書

変更内容: #438 Phase3（キーワード検索・Markdownまとめ出力）の実装。

## セルフチェック（7項目）

| # | 確認項目 | 結果 |
|---|---|---|
| 1 | 成果物はすべて作成/更新したか | ☑ |
| 2 | 命名規則は遵守されているか | ☑ |
| 3 | フォーマットや構造は要件通りか | ☑（§3全コマンドのOK_*出力を添付） |
| 4 | 誤字脱字、記述ミスはないか | ☑ |
| 5 | リンク切れや参照エラーはないか | ☑ |
| 6 | スコープ外の作業を含んでいないか | ☑（UIブラッシュアップ等は実施していない。既存の日付絞り込み・履歴削除ロジックは無変更） |
| 7 | スクリプトは正常に動作するか | ☑（pytest 111 passed, 1 skipped。既存テストの回帰0件） |

**セルフチェック完了宣言:**
私、作ロールは、上記チェックリストに基づきセルフチェックを実施し、すべての項目を満たしていることを宣言します。

**署名**: 作ロール
**日付**: 2026年09月10日
