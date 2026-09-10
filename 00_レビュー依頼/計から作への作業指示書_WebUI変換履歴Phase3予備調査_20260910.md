# 計から作への作業指示書_WebUI変換履歴Phase3予備調査_20260910

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 2026-09-12）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定は成果物Markdownファイル内の見出し文字列の存在を`grep`で数える構造チェックであり、検査コマンド自身の起動文字列（`grep`のコマンドライン）が対象ファイルの内容に混入することは構造上ない（プロセス確認のような自己マッチのリスクが存在しない検査種別のため、二段確認は不要と判断）。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: 実装方式検討に必要な現行コードの実測値（DBスキーマの実カラム名、既存関数の実在箇所・行番号）を§6に列挙した（いずれも2026-09-10計実測、現行dev tip 2819907で確認済み）。

## 2. 背景と目的

tc-ops #438（WebUI構築と変換履歴管理機能）はPhase1（履歴DB）・Phase2（WebUIプロトタイプ）が実装・main反映済み（done_ratio 80%）。

采による2026-09-10実態確認（Redmine #438 journal #3334）により、当初要望のうちPhase3相当の以下2点が未実装であることが確認された:

1. 履歴一覧のキーワード検索（日付絞り込みは実装済み、キーワード検索のみ欠落）
2. 複数履歴のMarkdown形式「まとめ出力」（NotebookLM等へのインポート想定）

本指示書は、上記2機能の**実装方式の予備調査**のみを対象とする（実装着手は本予備調査の完了・計承認後に別途指示する）。

## 3. ゴール（完了条件）

予備調査完了報告書（パスは `REPORT` とする。命名規則: `00_レビュー依頼/作から計への予備調査完了報告_WebUI変換履歴Phase3_[YYYYMMDD].md`）について、以下を実行しいずれも `OK` が出力されること:

```bash
REPORT="00_レビュー依頼/作から計への予備調査完了報告_WebUI変換履歴Phase3_<YYYYMMDD>.md"

test -f "$REPORT" && echo OK_EXISTS

# 4項目の見出し存在を機械確認(項目本文の内容自体はkeiが目視で妥当性判断する。
# ここでは「見出しとして存在すること」のみを機械検査する)
for pat in "キーワード検索" "まとめ出力" "整合性確認" "影響範囲"; do
  grep -q "^#.*${pat}" "$REPORT" && echo "OK_SECTION_${pat}" || echo "MISSING_SECTION_${pat}"
done
```

報告書に含めるべき4項目の内容（機械検査は見出し存在のみ。内容の技術的妥当性はkeiが受領後に確認する）:

1. キーワード検索の実装方式案（対象カラム、既存の日付絞り込みUI・`_render_history_tab()` との統合方法、SQLクエリ方式）
2. Markdownまとめ出力の実装方式案（対象履歴の選択UI、出力フォーマット案、ダウンロード方式）
3. 既存コード（`webui.py` / `core/cli_workflow.py` の履歴DBスキーマ・`_render_history_tab()`）との整合性確認結果（現状コードと設計書時点の乖離有無）
4. 影響範囲・リスク（既存機能への影響、パフォーマンス上の懸念があれば明記）

## 4. 成果物の仕様・要件

- 予備調査完了報告書（Markdown、上記4項目を含む）
- 実装自体は本指示書のスコープ外（予備調査のみ）

## 5. 作業範囲（スコープ）

**含む**:
- 上記2機能の実装方式検討（技術調査・設計方針の提示のみ）
- 既存コードとの整合性確認

**含まない**:
- 実際のコード実装（予備調査完了・計承認後、別途作業指示書を発行する）
- Phase3のうち上記2点以外の項目（追加の要望がある場合は別途起票する）
- UIブラッシュアップ等、要望原文に含まれない範囲の拡張

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/webui-history-phase3-search-export-20260910`（計が作成・push済み、dev tip 2819907から分岐）
- 参照資料:
  - Redmine tc-ops #438（要望原文・Phase1-2実装経緯全体）
  - `00_レビュー依頼/作から計への設計書_変換履歴DB設計_20260806.md`（既存DBスキーマ設計）
  - `00_レビュー依頼/作から計への設計書_WebUIフレームワーク選定とプロトタイプ方針_20260806.md`
  - `docs/system-docs/webui_architecture.md`
  - 現行 `webui.py` / `core/cli_workflow.py` / `core/webui_workflow.py`
- 実測項目（規則5、2026-09-10計実測、対象=現行dev tip 2819907）:
  - `transcription_history`テーブルの実カラム一覧（`core/cli_workflow.py` L132-153）: `id, processed_at, source_type, source_original, source_title, model_name, device, language, diarization_enabled, include_timestamps, context_hints_used, char_count, duration_sec, processing_time_sec, failed_chunks, repeated_chunks, result_text, output_text_path, gdrive_url, notes`（キーワード検索の対象候補は`source_title`/`source_original`/`result_text`/`notes`）
  - `_render_history_tab()`の実在箇所: `webui.py` L531（呼び出しはL602）
  - `ensure_history_table()`の実在箇所: `core/cli_workflow.py` L161

## 7. 承認プロセス

- 予備調査完了報告をkeiが受領し、実装計画（設計方針・影響範囲）を確認の上、実装着手の可否を判断する。
- 承認後、実装のための作業指示書を計が別途起草し、査（sa）の査読を経て正式伝達する（通常フロー: 予備調査→計承認→実装→査検査→dev反映）。
- 本指示書自体は査（sa）の査読を経て正式伝達する（本ファイルは査読依頼段階のドラフト）。
