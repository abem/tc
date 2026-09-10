# 計から作への作業指示書_WebUI変換履歴Phase3実装_20260910

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 2026-09-13）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定はソースコード中の構造パターン（DDL・関数呼び出し）の`grep`件数確認、および`pytest`の合否判定であり、検査コマンド自身の起動文字列が検査対象パターンと一致することは構造上ない。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: 実装対象箇所の現行行番号を計が2026-09-10に`webui.py`を直接Readして再実測し、下記§6に記載した（saku予備調査報告の一部行番号引用と3〜20行程度の差異があったため、計自身の実測値に置き換えている）。

## 2. 背景と目的

tc-ops #438 Phase3相当の未実装2点（履歴一覧のキーワード検索、複数履歴のMarkdownまとめ出力）について、saku予備調査完了報告（`00_レビュー依頼/作から計への予備調査完了報告_WebUI変換履歴Phase3_20260910.md`）を計が受領・承認した。本指示書はその実装着手を指示する。

採用方式（予備調査どおり）:
1. キーワード検索: FTS5仮想テーブル（external content方式）+ 同期トリガー3本
2. Markdownまとめ出力: 履歴一覧へのチェックボックス選択 + `st.download_button`

## 3. ゴール（完了条件）

```bash
# 3-1. FTS5仮想テーブル定義の存在
grep -q "CREATE VIRTUAL TABLE IF NOT EXISTS transcription_history_fts" core/cli_workflow.py && echo OK_FTS_TABLE

# 3-2. 同期トリガー3本(INSERT/UPDATE/DELETE)の存在
for op in INSERT UPDATE DELETE; do
  grep -qi "AFTER ${op}" core/cli_workflow.py && echo "OK_TRIGGER_${op}" || echo "MISSING_TRIGGER_${op}"
done

# 3-3. 既存データのbackfill(rebuild)呼び出しの存在
grep -q "transcription_history_fts.*rebuild\|rebuild.*transcription_history_fts" core/cli_workflow.py && echo OK_REBUILD

# 3-4. webui.pyにキーワード検索UI・検索条件・チェックボックス・ダウンロードボタンが存在
grep -q 'st.text_input(' webui.py | true  # (既存箇所と衝突しうるため件数ではなく後続の個別grepで判定)
grep -q "history_keyword" webui.py && echo OK_KEYWORD_UI
grep -q "MATCH" webui.py && echo OK_FTS_QUERY
grep -q "history_select_" webui.py && echo OK_SELECT_CHECKBOX
grep -q "st.download_button" webui.py && echo OK_DOWNLOAD_BUTTON

# 3-5. 新規/既存テストが全件成功(回帰なし)し、FTS5往復(INSERT後MATCHで拾える)の結合テストが含まれること
uv run pytest -q 2>&1 | tail -5
grep -rq "MATCH" tests/ && echo OK_FTS_ROUNDTRIP_TEST_PRESENT
```

- 上記いずれも該当する `OK_*` / `MISSING_*` の出力を完了報告に添付すること（実行結果の生ログを貼付、記述確認での代替は不可）。
- pytestは既存件数からの増分・回帰0件であることを報告書に明記する（既存件数は着手時に`uv run pytest -q 2>&1 | tail -3`で計測してから着手すること）。

## 4. 成果物の仕様・要件

- `core/cli_workflow.py`: `ensure_history_table()`（L161）内のDDL群に、FTS5仮想テーブル定義・同期トリガー3本・初回rebuild呼び出しを追加。既存の`transcription_history`テーブル定義・既存呼び出し元は無変更（後方互換）。
- `webui.py`: `_render_history_tab()`（L531定義）内、以下を追加。
  - キーワード検索入力欄（既存の日付入力`col1`/`col2`, L538-542の下）
  - `conditions`リスト（L550-559）へのFTS5 `MATCH`条件追加（既存の日付条件とAND結合）
  - 一覧ループ（`for row in rows:`, L569）内、各`st.expander`にチェックボックス追加
  - 選択済み履歴をMarkdown連結し`st.download_button`で提供するUI（一覧の下）
- 新規/更新テスト: FTS5往復（INSERT→MATCH検索で拾えること）を検証する結合テストを`tests/`配下に追加。
- 完了報告（agmsg経由、kei宛）: §3の全コマンド実行結果（生ログ）、pytest件数（既存→更新後）、実機確認内容（可能な範囲で）を含むこと。

## 5. 作業範囲（スコープ）

**含む**:
- キーワード検索（FTS5）の実装
- Markdownまとめ出力の実装
- 上記に必要な結合テストの追加

**含まない**:
- UIブラッシュアップ等、要望原文・予備調査報告に含まれない拡張
- 既存の日付絞り込み・履歴削除機能のロジック変更（既存動作を壊さないこと自体は完了条件に含む）
- Git操作（計の専任、実装完了後は計がコミット・査検査依頼・dev反映を行う）

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/webui-history-phase3-search-export-20260910`（計が作成・push済み、dev tip 2819907から分岐、現時点で予備調査報告ドラフトのみ計未コミット）
- 参照資料:
  - `00_レビュー依頼/作から計への予備調査完了報告_WebUI変換履歴Phase3_20260910.md`（採用方式の詳細）
  - `00_レビュー依頼/作から計への設計書_変換履歴DB設計_20260806.md` §2-1・§5
  - Redmine tc-ops #438
- 実測項目（規則5、2026-09-10計実測、対象=`webui.py`現行内容・dev tip 2819907相当）:
  - `_render_history_tab()`定義: L531
  - 日付入力欄（`col1`/`col2`）: L538-542
  - `conditions`リスト組み立て: L550-559（`conditions = []`がL550、`if conditions:`分岐がL558-559）
  - 履歴一覧ループ`for row in rows:`: L569（予備調査報告記載のL546とは差異があるため本実測値を正とする）
  - `_render_history_cleanup_section()`呼び出し: L544
  - `ensure_history_table()`定義: `core/cli_workflow.py` L161

## 7. 承認プロセス

1. saku完了報告をkeiが受領（agmsg）
2. kei一次確認（§3各コマンドの実行結果・pytest件数を確認）
3. 査（sa）へ検査依頼（実機グラウンディング検査含む: FTS5往復・キーワード検索・まとめ出力ダウンロードの実動作確認）
4. 査合格後、計が最終承認・feature/webui-history-phase3-search-export-20260910 → dev マージ・push
5. main反映はユーザー明示承認まで保留（従来通り）
6. 本指示書自体は査（sa）の査読を経て正式伝達する（本ファイルは査読依頼段階のドラフト）
