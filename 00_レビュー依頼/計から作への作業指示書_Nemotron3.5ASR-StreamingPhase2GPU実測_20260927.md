# 計から作への作業指示書_Nemotron3.5ASR-StreamingPhase2GPU実測_20260927

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか（Phase2実装・緊急是正まで完了済み）
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 2026-09-28）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定はファイル存在・pytest結果・出力テキストの確認であり、検査コマンド自身が対象コードに混入することは構造上ない。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: Phase2実装・緊急是正の到達点を下記§6に列挙した。

## 2. 背景と目的

tc-ops #546は、Phase2実装（GPU不要範囲、commit fbca18a）と本番不具合の緊急是正（言語自動判定・デバイス指定、commit e48756b）まで完了した。残るは、Phase2設計report §7で「GPU使用・要事前連絡」としたステップ5（初回E2E動作確認）・ステップ6（長尺音声実測、チャンク処理閾値の検証）のみである。

采指示（2026-09-26T15:24:47Z、sai→kei）により、本指示書の起草・査読までは待機せずに進めてよい。**査読合格後、実際にGPUを使う直前に計経由で采へ1行報告すること（jev-localの停止をユーザーに依頼するため）。**

隔離venvは前回是正でコード上`venv-nemotron`へ改名済みだが、物理ディレクトリは未構築（旧`venv-nemotron-poc/`が残存）。本指示書で`scripts/setup_nemotron_venv.sh`を実行し`venv-nemotron/`を新規構築する。**旧`venv-nemotron-poc/`の削除は、新venvでの動作確認後に行うこと（采指示、切り戻し手段を残すため）。**

**査(sa)査読で判明した重大な抜け（是正済み）**: Phase2設計report §5は「長音声チャンク処理: 要」（`CHUNK_THRESHOLD_SEC=300`単位で分割しサブプロセスを複数回呼び出す設計）と結論していたが、Phase2実装（commit fbca18a）・緊急是正（commit e48756b）のいずれにも**チャンク処理コードは実装されていなかった**（`core/nemotron_engine.py`・`scripts/nemotron_infer.py`にチャンク分割ロジックなし、査sa実測でgrep該当なしを確認）。査の線形外挿再計算により、10分音声でも推定ピークVRAM 17671MiB（総量16376MiBを1295MiB超過）、15分で6247MiB超過、20分で11198MiB超過と判明。**チャンク処理未実装のまま長尺音声でGPU実測するとVRAM不足でクラッシュする可能性が高い。** よって本指示書は、チャンク処理の実装（GPU不要）をGPU実測着手前の成果物として追加し、実装→動作確認の順序で進める。

## 3. ゴール（完了条件）

```bash
# チャンク処理が実装されていること(GPU実測着手前の前提条件)
grep -q "CHUNK_THRESHOLD_SEC\|chunk" core/nemotron_engine.py && echo OK_CHUNK_LOGIC_IMPLEMENTED || echo MISSING_CHUNK_LOGIC

# チャンク分割ロジックの単体テスト(GPU不要、音声長からの分割数・境界計算を検証)が存在すること
grep -rlq "chunk" tests/test_core_nemotron_dispatch.py tests/test_core_nemotron_language.py tests/test_core_nemotron_chunk.py 2>/dev/null && echo OK_CHUNK_TEST_EXISTS || echo MISSING_CHUNK_TEST

# 新venvが構築されていること
test -d venv-nemotron && test -x venv-nemotron/bin/python && echo OK_NEW_VENV_BUILT

# E2E動作確認: 実際にWebUI経由(または隔離venv+core/nemotron_engine.py直接呼び出し)で
# 日本語音声を変換し、結果テキストが得られること(完了報告に実行ログ・結果抜粋を記載)

# 長尺音声(10-20分規模)でのチャンク処理実測結果が完了報告に記載されていること
# (チャンク処理実装後の実測。ピークVRAM・処理時間・チャンク境界での欠落や反復の有無)

# 既存2エンジン(Qwen3-ASR/Whisper)の回帰確認: 同一環境でいずれかの音声を変換し、
# Nemotron追加による影響がないことを確認

# 全pytest(既存+新規)がpassすること
uv run python -m pytest tests -q 2>&1 | tail -5

# 生産用.venv/pyproject.toml/uv.lockが変更されていないことの機械確認
git diff --name-only -- .venv pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_ENV_CHANGE || echo FAIL_ENV_CHANGED

# 旧venv-nemotron-poc/の扱い: 新venvでの動作確認が完了報告に記載された後、
# 削除するかどうかは計が確認して判断する(本指示書内での削除は必須としない)
```

## 4. 成果物の仕様・要件

**フェーズA（GPU不要、フェーズBの前提条件・先に完了させること）**:

1. **チャンク処理の実装**: `NemotronSubprocessEngine.transcribe()`（`core/nemotron_engine.py`）に、Phase2設計report §5の対策案（`CHUNK_THRESHOLD_SEC=300`秒を暫定閾値とし、超過時は300秒単位で音声を分割、`scripts/nemotron_infer.py`のサブプロセスを複数回呼び出して結果を連結する）を実装する。既存`Qwen3ASREngine._transcribe_long_audio`（`core/transcription_interface.py` L693-826）の分割・結合パターン（境界での単語結合防止の半角スペース区切り等）を参考にしてよいが、Nemotronはサブプロセス経由のため呼び出し方式は独自設計となる。
2. **チャンク分割の単体テスト（GPU不要）**: 音声長から分割数・各チャンクの開始/終了時刻が正しく計算されることを検証するテスト（`tests/`配下、新規または既存ファイルへの追加）。モデル推論・サブプロセスの実実行はモックで代替してよい。
3. **隔離venv再構築**: `scripts/setup_nemotron_venv.sh`を実行し`venv-nemotron/`を新規構築する（`transformers==5.17.0`／`torch==2.14.0`で固定、Phase2設計report §3のとおり）。

**フェーズB（GPU使用、フェーズA完了後に着手。着手直前に計経由で采へ1行報告）**:

4. **E2E動作確認**: 日本語の短い音声（Phase1で使用したJSUT候補等、`output/`配下は使わない）で、Nemotronを選択してWebUI（または隔離venv経由の直接呼び出し）から変換を実行し、結果テキスト・処理時間・ピークVRAMを完了報告に記載する。
5. **長尺音声でのチャンク処理実測**: フェーズAで実装したチャンク処理を、10-20分規模の音声で実際に動作させ、`CHUNK_THRESHOLD_SEC=300`（5分）の妥当性を検証する。チャンク境界での欠落・反復の有無、ピークVRAM（チャンクごとの推移）、総処理時間を記載する。閾値の見直しが必要と判断した場合は、その根拠と変更案を完了報告に記載する（実際の閾値変更は本指示書のスコープ内で行ってよい）。
6. **既存エンジンの回帰確認**: 同一環境でQwen3-ASRまたはWhisperのいずれかで変換を実行し、Nemotron追加による影響がないことを確認する。
7. **旧venv-nemotron-poc/の扱い**: 新venvでの動作確認が完了した後、削除してよいかを計に確認する（削除の実施自体は計の判断後でよい）。

## 5. 作業範囲（スコープ）

**含む**:
- チャンク処理の実装・単体テスト（フェーズA、GPU不要）
- 隔離venv（`venv-nemotron/`）の新規構築
- GPU使用を伴う実際のモデル推論によるE2E確認・長尺音声実測（フェーズB）
- 既存2エンジンの回帰確認
- チャンク閾値の見直し（必要と判断した場合）

**含まない**:
- 生産用`.venv/`・`pyproject.toml`・`uv.lock`への変更
- `UnifiedTranscriber`のインターフェース自体の変更（Phase2実装で完了済み）
- tc-ops #547（Qwen3-ASR電話音声の欠落・反復暴走調査）— 別指示書で並行対応

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/nemotron35-asr-phase1-investigation-20260926`（継続使用）
- 参照資料:
  - Phase2設計予備調査完了報告（commit 509e7ab）§5（チャンク処理閾値）・§7（実装計画ステップ5-6）
  - Phase2実装（commit fbca18a）・緊急是正（commit e48756b）
  - 采指示（agmsg ccc、2026-09-26T15:24:47Z、sai→kei、原文）
- 遵守事項:
  - CLAUDE.md「.venv/ ディレクトリを削除・変更すべからず」「本番データで実験すべからず」
  - GPU使用前に計経由で采へ連絡すること（jev-local停止確認のため）。**着手前ではなく、実際にモデルロード・推論を行う直前でよい。**
  - 旧`venv-nemotron-poc/`は新venvでの動作確認前に削除しないこと

## 7. 承認プロセス

- 計が本指示書を査（sa）へ査読依頼し、合格後に正式伝達する（本ファイルは査読依頼段階のドラフト）。査読合格時、GPU使用直前に計経由で采へ1行報告する（着手時点ではなく、実際にGPUを使う直前）。
- 完了後、計が受領し、査(sa)の品質検査を経て、計が最終承認する。承認後、Phase2の一連の作業（tc-ops #546）が完了となる。
