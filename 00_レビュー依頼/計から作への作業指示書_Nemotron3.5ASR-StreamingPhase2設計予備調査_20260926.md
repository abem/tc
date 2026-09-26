# 計から作への作業指示書_Nemotron3.5ASR-StreamingPhase2設計予備調査_20260926

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか（Phase1予備調査・実測の成果を§6で提供）
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 2026-09-27）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定は成果物Markdownファイル内の見出し文字列の存在を`grep`で確認する構造チェックであり、検査コマンド自身の起動文字列が対象ファイルの内容に混入することは構造上ない。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: 既存コードの実在箇所（`webui.py`のモデル選択箇所、`core/transcription_interface.py`のディスパッチロジック）を計が実測し§6に列挙した（2026-09-26計実測、対象=現行ブランチtip）。

## 2. 背景と目的

采方針指示（2026-09-26T13:34:49Z、sai→kei、ユーザー指示）により、tc-ops #546 はPhase2（WebUIでNemotron-3.5-ASR-Streamingを選択肢として追加）に進む。Phase1の一次判断「否」はユーザー判断で上書きされた（判断自体の訂正作業はPhase1のCER是正として別途継続中。Phase2はこれと並行して進める）。

目的は「選択肢として追加する」ことであり、デフォルト（`Qwen/Qwen3-ASR-1.7B`）の置き換えではない。生産用`.venv`は不変（Nemotronはtransformers>=5.13.0が必要でqwen-asrの`<5`制約と衝突するため、予備調査#546で確認済み）。

本指示書は、実装（コード変更）に入る前の**設計・予備調査**のみを対象とする。采指示の設計上の必須条件7点（下記§6に転記）を満たす具体的な実装方式を確定させ、実装フェーズの作業指示書の土台とする。

## 3. ゴール（完了条件）

設計・予備調査完了報告書（パスは `REPORT` とする。命名規則: `00_レビュー依頼/作から計への設計予備調査完了報告_Nemotron3.5ASR-StreamingPhase2_[YYYYMMDD].md`）について、以下を実行しいずれも `OK` が出力されること:

```bash
REPORT="00_レビュー依頼/作から計への設計予備調査完了報告_Nemotron3.5ASR-StreamingPhase2_<YYYYMMDD>.md"

test -f "$REPORT" && echo OK_EXISTS

for pat in "サブプロセス呼び出し設計" "既存モデル名判定への影響と回帰テスト設計" "隔離venv構築スクリプト設計" "出力形式の整合設計" "長音声チャンク処理の要否" "エラーハンドリング設計" "実装計画"; do
  grep -q "^#.*${pat}" "$REPORT" && echo "OK_SECTION_${pat}" || echo "MISSING_SECTION_${pat}"
done

# 生産用.venv/pyproject.toml/uv.lockが変更されていないことの機械確認
git diff --name-only -- .venv pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_ENV_CHANGE || echo FAIL_ENV_CHANGED
```

報告書に含めるべき7項目の内容（機械検査は見出し存在のみ。内容の技術的妥当性はkeiが受領後に確認する）:

1. **サブプロセス呼び出し設計**: `UnifiedTranscriber`からNemotronを隔離venv経由で呼び出す具体案（サブプロセス起動コマンド、入出力の受け渡し方式（JSON等）、タイムアウト・異常終了時の扱い）。采条件①のとおりサブプロセス方式を基本とし、別方式を採る場合はtransformers衝突を回避できる根拠を明記すること。
2. **既存モデル名判定への影響と回帰テスト設計**: `core/transcription_interface.py` L933-938のディスパッチロジック（`Qwen3ASREngine.is_qwen3_model`判定→非該当はWhisperへの現行catch-all）に、nemotron判定をどう挿入するか（既存判定より前に置く等）の具体案。既存モデル名（`Qwen/Qwen3-ASR-1.7B`・`kotoba-tech/kotoba-whisper-v2.2`・`openai/whisper-large-v3`等）の振り分け結果が変わらないことを保証する回帰テストの設計（テストケース一覧）。**加えて、以下を明記し回帰テストのテストケースに含めること（デフォルト不変、査sa是正指摘反映）**:
   - `webui.py` L109-112のselectbox: Nemotronは`options`リストの**末尾**に追加し、`index=0`は変更しない（デフォルト`Qwen/Qwen3-ASR-1.7B`が維持されることの確認方法を明記）
   - `./tc`のCLIデフォルト: `config/config.yaml` L9（`model: Qwen/Qwen3-ASR-1.7B`）を経由する設定であり、本指示書のスコープでは`config/config.yaml`・`tc`のコードは変更しないため不変。ただし共有される`core/transcription_interface.py`のディスパッチロジック変更の影響は受けるため、上記の回帰テストケース一覧に`"Qwen/Qwen3-ASR-1.7B"`が引き続き`Qwen3ASREngine`へ解決されることを含めること
   - 参考（本機能のスコープ外、CLIデフォルトの補足情報）: レガシーCLI`transcribe.py`は`--profile`未指定時、L82-83のロジック（`selected_key = profile_num if profile_num and profile_num in profiles else "1"`）によりプロファイル"1"（`kotoba-tech/kotoba-whisper-v2.2`、L60）がデフォルトとなる。これは`./tc`とは独立した別の仕組みであり、本Nemotron追加でL72（プロファイル"5"内の`"model": "Qwen/Qwen3-ASR-1.7B"`という値。これ自体はデフォルト決定ロジックではない）を含め一切変更しないため影響なし
3. **隔離venv構築スクリプト設計**: 予備調査（#546、`venv-nemotron-poc/`のPoC手順）を踏まえた、再現可能なビルドスクリプトの設計（配置場所、実行方法、PoCディレクトリへの非依存）。
4. **出力形式の整合設計**: Nemotronのサブプロセス出力を`TranscriptionResult`/`TranscriptionSegment`（`core/transcription_interface.py` L27-71）へ変換する方式。WebUIの結果表示・履歴・ダウンロード・Driveアップロードの各経路（`webui.py`）が動作するための要件確認。
5. **長音声チャンク処理の要否**: Phase1実測（候補2=YouTube 180秒、候補3=JSUT 70秒）はチャンク分割なしで動作した。生産で扱う長尺音声（数十分規模）でのメモリ・処理時間の見積もりに基づき、チャンク処理の要否を判断する。
6. **エラーハンドリング設計**: 隔離venv未構築時に分かりやすいエラーを出し、他エンジンの動作に影響させない設計（例外の種類、UI表示、他エンジン選択時への波及がないことの確認方法）。
7. **実装計画**: 上記1-6を踏まえた実装ステップ・テスト計画・GPU使用が必要なタイミング（実装のどの段階でGPU実測・E2Eが必要か。采条件⑥のとおりGPU使用直前に采へ連絡が必要なため、いつ連絡が必要になるかを明確化する）。

## 4. 成果物の仕様・要件

- 設計・予備調査完了報告書（Markdown、上記7項目を含む）
- 実際のコード変更（`webui.py`・`core/transcription_interface.py`等の変更）・依存インストール・GPU実行は本指示書のスコープ外（設計のみ）

## 5. 作業範囲（スコープ）

**含む**:
- 上記7項目の設計・調査（技術調査・設計方針の提示のみ）
- 既存コード（`webui.py`, `core/transcription_interface.py`, `core/config.py`）の該当箇所の実測・整合性確認

**含まない**:
- 生産用`.venv/`・`pyproject.toml`・`uv.lock`への変更
- 実際のコード変更（`webui.py`・`core/transcription_interface.py`等）
- 隔離venvの実構築・GPU実行（設計段階のため。実行が必要な最小限の動作確認（import可否等、CPU/非GPU範囲）は許容する）

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/nemotron35-asr-phase1-investigation-20260926`（Phase1と同一ブランチで継続。ブランチ名にphase1とあるがdevへのマージ前はこのまま使用してよい。改名が必要と判断すれば計へ提案すること）
- 参照資料:
  - 采方針指示全文（agmsg ccc、2026-09-26T13:34:49Z、sai→kei）
  - Phase1予備調査完了報告（`00_レビュー依頼/作から計への予備調査完了報告_Nemotron3.5ASR-StreamingPhase1_20260926.md`）: 隔離venv構築コマンド例、単体スクリプト設計
  - Phase1実測結果報告（`00_レビュー依頼/作から計へのPhase1実測結果報告_Nemotron3.5ASR-Streaming_20260926.md`）: 実際に動作したNemotron推論スクリプト（`nemotron_infer.py`、証跡`WORK_20260926_220529_phase1/`）
- 実測項目（規則5、2026-09-26計実測、対象=現行ブランチtip）:
  - `webui.py` L109-112: モデル選択`selectbox`、現行options `["Qwen/Qwen3-ASR-1.7B", "kotoba-tech/kotoba-whisper-v2.2", "openai/whisper-large-v3"]`、`index=0`（デフォルト`Qwen/Qwen3-ASR-1.7B`）
  - `core/transcription_interface.py` L416-420: `Qwen3ASREngine.is_qwen3_model()`（`"qwen3-asr" in name or "qwen3_asr" in name`）
  - `core/transcription_interface.py` L933-938: `UnifiedTranscriber.__init__`のディスパッチ（`is_qwen3_model`が真ならQwen3ASREngine、偽ならelse節でWhisperTranscriptionEngineへ）
  - `core/transcription_interface.py` L27-71: `TranscriptionSegment`/`TranscriptionResult`のフィールド定義
  - `config/config.yaml` L9: `model: Qwen/Qwen3-ASR-1.7B`（`./tc`のCLIデフォルトはこの設定値を経由する。本指示書では変更しない）
  - `transcribe.py` L82-83: レガシーCLIの`--profile`未指定時のデフォルト解決ロジック（`selected_key = profile_num if profile_num and profile_num in profiles else "1"`）。プロファイル"1"（L57-62）は`kotoba-tech/kotoba-whisper-v2.2`であり、`./tc`とは独立した別の仕組み。本指示書では変更しない（参考情報。L72はプロファイル"5"内の値でありデフォルト決定ロジックではない）
- 采条件7点（本指示書§2参照、原文はagmsg ccc 2026-09-26T13:34:49Z）
- 遵守事項:
  - CLAUDE.md「.venv/ ディレクトリを削除・変更すべからず」「既存のクラス名やメソッド名を変更する際は影響範囲を調査すべし」「import文の変更は依存関係を確認してから行う」
  - GPU使用が必要な作業は、実施前に計経由で采へ連絡すること（jev-local停止要否の確認のため）

## 7. 承認プロセス

- 設計・予備調査完了報告をkeiが受領し、査(sa)の査読を経て、実装（コード変更）の作業指示書発行の可否を判断する。
- 承認後、実装のための作業指示書を計が別途起草し、査（sa）の査読を経て正式伝達する。
- 本指示書自体は査（sa）の査読を経て正式伝達する（本ファイルは査読依頼段階のドラフト）。査読合格時、采へ1行報告する（采指示の報告要件）。
