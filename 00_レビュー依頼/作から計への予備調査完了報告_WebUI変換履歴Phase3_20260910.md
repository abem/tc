# 作から計への予備調査完了報告：WebUI変換履歴Phase3（#438）

**報告日**: 2026-09-10
**報告者**: 作成ロール（作/saku）
**対象作業指示書**: 計から作への作業指示書_WebUI変換履歴Phase3予備調査_20260910.md
**調査方法**: `feature/webui-history-phase3-search-export-20260910` ブランチへの切替は行わず、`git show <branch>:<path>` による読み取りで現行コードを確認（現在ブランチ`dev`は変更していない）。実装は行っていない。

---

## 1. キーワード検索の実装方式案

**対象カラム**: `source_title` / `source_original` / `result_text` / `notes`（作業指示書§6の指定どおり）。

**実装方式**: 設計書（`作から計への設計書_変換履歴DB設計_20260806.md` §2-1・§5）が既に見込んでいたFTS5仮想テーブルを採用する。

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS transcription_history_fts
USING fts5(source_title, source_original, result_text, notes,
           content='transcription_history', content_rowid='id');
```

- external contentテーブル方式のため、`transcription_history` への INSERT/UPDATE/DELETE を `transcription_history_fts` に同期するトリガー3本（`AFTER INSERT` / `AFTER UPDATE` / `AFTER DELETE`）を `ensure_history_table()`（`core/cli_workflow.py` L161）内のDDL群に追加する必要がある。既存データ（トリガー導入前に登録済みの行）はトリガーの対象外のため、導入時に一度 `INSERT INTO transcription_history_fts(transcription_history_fts) VALUES('rebuild')` でバックフィルする。
- **UI統合方法**: `webui.py` の `_render_history_tab()`（L531）内、既存の日付範囲入力（`col1`/`col2`、L537-541）の下に `st.text_input("キーワード検索", key="history_keyword")` を追加する。
- **SQLクエリ方式**: キーワード入力があれば、既存の `WHERE` 組み立て（L556-563の `conditions` リスト）に `id IN (SELECT rowid FROM transcription_history_fts WHERE transcription_history_fts MATCH ?)` を追加する（既存の日付条件とAND結合、既存の条件組み立てパターンをそのまま拡張できる）。

## 2. Markdownまとめ出力の実装方式案

**対象履歴の選択UI**: `_render_history_tab()` の一覧ループ（L546以降、`for row in rows:`）内、各 `st.expander` の先頭に `st.checkbox("出力対象に含める", key=f"history_select_{row['id']}")` を追加し、選択状態を `st.session_state` で保持する。

**出力フォーマット案**:
```markdown
## {processed_at} - {title}（{model_name}）

{result_text}

---
```
を選択行ごとに連結した1つのMarkdown文字列を生成する（NotebookLM等への単体アップロードを想定した自己完結形式）。

**ダウンロード方式**: 一覧の下に「選択履歴をまとめ出力」ボタンを配置し、押下時に上記形式で文字列を組み立てて `st.download_button(data=..., file_name="history_summary_<YYYYMMDD_HHMMSS>.md", mime="text/markdown")` で提供する（サーバー側にファイルを残さない方式。既存の履歴削除機能・GDriveアップロードと独立）。

## 3. 整合性確認

現行dev tip（commit 2819907）を実測し、作業指示書§6記載の実測値との差異を確認した。

| 項目 | 作業指示書記載値 | 実測結果（2026-09-10, dev tip 2819907） | 差異 |
|---|---|---|---|
| `transcription_history` 実カラム一覧 | 19カラム（id〜notes） | `core/cli_workflow.py` L132-153 のDDLと完全一致 | なし |
| `_render_history_tab()` 実在箇所 | L531定義・L602呼び出し | `git show`実測で定義L531・呼び出しL602を確認 | なし |
| `ensure_history_table()` 実在箇所 | L161 | `git show`実測でL161を確認 | なし |

設計書時点（2026-08-06）とdev tip（2026-09-10）の間で、キーワード検索・まとめ出力に関わる既存コードの乖離は検出されなかった。設計書§2-1・§5が示すFTS5拡張方針は現行コードにそのまま適用可能である。

## 4. 影響範囲・リスク

- **既存機能への影響**: 日付絞り込み（既存の`conditions`組み立て）とキーワード検索は独立した`AND`条件として追加するため、既存動作への影響なし。まとめ出力はダウンロードのみでサーバー状態を変更せず、既存の削除機能（`_render_history_cleanup_section()`）とも独立。
- **パフォーマンス上の懸念**: FTS5導入時、既存データのバックフィル（`rebuild`）が必要。件数が多い場合は初回導入時のみ実行コストが発生するが、以降はトリガーによる差分更新のため軽微。
- **リスク**: external contentのFTS5テーブルはトリガーでの同期が前提であり、トリガー追加を失念すると検索結果が徐々に陳腐化する（サイレント障害になりやすい）。実装時はトリガー導入とセルフ機械検証（`INSERT`後に`MATCH`で拾えるかの結合テスト）を完了条件に含めることを推奨する。
- **スコープ外事項**: UIブラッシュアップ等、本予備調査のスコープ外の拡張は含めていない。

---

## セルフチェック（7項目）

| # | 確認項目 | 結果 |
|---|---|---|
| 1 | 成果物はすべて作成/更新したか | ☑（本報告書のみ。実装は対象外） |
| 2 | 命名規則は遵守されているか | ☑（作業指示書§3指定のファイル名と一致） |
| 3 | フォーマットや構造は要件通りか | ☑（4見出し: キーワード検索/まとめ出力/整合性確認/影響範囲） |
| 4 | 誤字脱字、記述ミスはないか | ☑ |
| 5 | リンク切れや参照エラーはないか | ☑（参照した設計書2点・webui_architecture.mdは実在確認済み） |
| 6 | スコープ外の作業を含んでいないか | ☑（実装コード変更は行っていない） |
| 7 | （スクリプトの場合）正常に動作するか | 該当なし（本タスクはスクリプト作成なし） |

**セルフチェック完了宣言:**
私、作ロールは、上記チェックリストに基づきセルフチェックを実施し、すべての項目を満たしていることを宣言します。

**署名**: 作ロール
**日付**: 2026年09月10日
