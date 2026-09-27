# 計から作への作業指示書_Nemotron3.5ASR-StreamingPhase1実測_20260926

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか（予備調査(#546)で隔離実行案・テスト音声を確定済み）
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: GPU実測ステップは2026-09-26中に完了、報告書全体は2026-09-27まで）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定は成果物Markdownファイル内の見出し・表の存在を`grep`で確認する構造チェックであり、検査コマンド自身の起動文字列が対象ファイルの内容に混入することは構造上ない。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: 予備調査完了報告(#546、saku作成・sa検査合格)の実測値・設計・采(sai)によるVRAM原因確定結果を下記§6に列挙した（2026-09-26時点）。

## 2. 背景と目的

tc-ops #546（Nemotron-3.5-ASR-Streaming追加検討）の予備調査（saku作成・sa検査合格・commit f5bbab9）により、以下が確定した:

- Transformers経路（`transformers>=5.13.0`）は生産用`.venv`（`transformers==4.57.6`固定、qwen-asr要求`<5`）と衝突するため、隔離venv（`uv venv venv-nemotron-poc`等）で実行する。
- テスト音声は候補2（YouTube日本語音声、冒頭抜粋）・候補3（JSUT corpus、CER測定用の参照テキスト付き）を使用する（`output/`配下は除外）。
- VRAM異常（実機で使用中13GB超・該当プロセス検出不可）は、采(sai)がWindows側`nvidia-smi.exe`で原因を特定した: jev-local（ユーザーの別プロセス、`uvicorn jevlocal.app:app --port 8099`）がVRAMを使用していた。ユーザー判断により、jev-localは**計測中のみ停止**され、采が停止後のVRAM状態（使用5300MiB/空き10746MiB/総16376MiB）を確認済み。
- 采がPhase1実測の着手を許可（本指示書の査読合格が前提）。**条件3点（遵守必須）**:
  1. 各エンジンの計測**前後**にベースラインVRAMを記録し、ピークVRAMは差分で評価する
  2. エンジンは1つずつ順番に実行する（同時にロードしない）
  3. GPU実測ステップが終わったら、jev-local再開可の旨を**直ちに**計へ1行報告する（計が采へ報告し、再開はユーザーが行う。全体の報告書完成を待たない）

本指示書は、上記を前提としたPhase1実測（既存2エンジンとNemotronの精度・処理速度比較）を対象とする。

## 3. ゴール（完了条件）

Phase1実測結果報告書（パスは `REPORT` とする。命名規則: `00_レビュー依頼/作から計へのPhase1実測結果報告_Nemotron3.5ASR-Streaming_[YYYYMMDD].md`）について、以下を実行しいずれも `OK` が出力されること:

```bash
REPORT="00_レビュー依頼/作から計へのPhase1実測結果報告_Nemotron3.5ASR-Streaming_<YYYYMMDD>.md"

test -f "$REPORT" && echo OK_EXISTS

# 4項目の見出し存在を機械確認
for pat in "実行環境とベースラインVRAM" "比較結果" "一次判断" "jev-local再開可の報告"; do
  grep -q "^#.*${pat}" "$REPORT" && echo "OK_SECTION_${pat}" || echo "MISSING_SECTION_${pat}"
done

# 比較結果マトリクスに3エンジン(Qwen3-ASR/Whisper/Nemotron)の行があることを機械確認
for engine in "Qwen3-ASR" "Whisper" "Nemotron"; do
  grep -q "${engine}" "$REPORT" && echo "OK_ENGINE_${engine}" || echo "MISSING_ENGINE_${engine}"
done

# 生産用.venv/pyproject.toml/uv.lockが変更されていないことの機械確認
git diff --name-only -- .venv pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_ENV_CHANGE || echo FAIL_ENV_CHANGED
```

報告書に含めるべき4項目の内容（機械検査は見出し・エンジン名の存在のみ。内容の技術的妥当性はkeiが受領後に確認する）:

1. **実行環境とベースラインVRAM**: 隔離venv構築の実施記録、各エンジン計測前後のVRAM実測値（`nvidia-smi`、ベースライン→ロード後→推論後→アンロード後の遷移）。采が条件①で求めるベースライン記録に対応。
2. **比較結果**: 3エンジン（Qwen3-ASR・Whisper・Nemotron-3.5-ASR-Streaming）×テスト音声（候補2・候補3）のマトリクス表。列: エンジン名／CER／RTF／ピークVRAM(MiB、ベースライン差分)／備考。CERは候補3（JSUT、参照テキストあり）を主対象とする（候補2はYouTube自然発話のため参照テキストが無い場合はRTF・動作確認のみでよい。CERを取る場合は参照テキストの作成方法を明記すること）。
3. **一次判断**: 上記比較結果に基づく、Nemotron追加導入の可否（可/否）とその根拠。tc-ops #546の采方針指示にある「Phase1完了条件」（既存エンジンとの精度・速度比較による一次判断可能性）に対応させること。
4. **jev-local再開可の報告**: GPU実測ステップ完了時に計へ送った1行報告の内容・時刻を記録する（既に送信済みの事実の記録。本報告書作成中に重複送信しない）。

## 4. 成果物の仕様・要件

- Phase1実測結果報告書（Markdown、上記4項目を含む）
- 実行に使用した単体スクリプト（隔離venv内、生産コード非import）は`venv-nemotron-poc/`配下等に置き、Git管理対象外（`.gitignore`の`venv*/`パターンでカバー済み）としてよい。ただし比較結果の数値・ログ抜粋は報告書本体に記載すること。
- JSUT corpusの音声ファイル自体はGitにコミットしないこと（再配布不可ライセンス。ローカル保持のみ、結果の数値・引用のみ報告書に記録可）。

## 5. 作業範囲（スコープ）

**含む**:
- 隔離venv（`venv-nemotron-poc`等）の構築、Nemotron-3.5-ASR-Streamingの動作確認・推論実行
- 既存2エンジン（Qwen3-ASR・Whisper、生産用`.venv`使用、`core/transcription_interface.py`経由）での同一音声での比較実測
- CER・RTF・ピークVRAM（差分）の実測、マトリクス表の作成
- 一次判断（可/否+根拠）の提示

**含まない**:
- 生産用`.venv/`・`pyproject.toml`・`uv.lock`への変更
- `UnifiedTranscriber`へのエンジン追加実装（Phase2相当。一次判断が「可」となった場合、別途作業指示書を発行する）
- NeMo経路の実行（予備調査§1で依存解決の不確実性が判明済みのため、Transformers経路を主経路とする。時間的余裕があれば副次的に試みてもよいが必須ではない）

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/nemotron35-asr-phase1-investigation-20260926`（push済み、これに乗ること）
- 参照資料:
  - 予備調査完了報告（`00_レビュー依頼/作から計への予備調査完了報告_Nemotron3.5ASR-StreamingPhase1_20260926.md`、commit f5bbab9）: 隔離venv構築コマンド例（§2）、テスト音声候補の詳細（§4）
  - HuggingFaceモデルカード `nvidia/nemotron-3.5-asr-streaming-0.6b`
- 実測項目（規則5、2026-09-26時点）:
  - jev-local停止後のVRAM状態（采実測）: 使用5300MiB／空き10746MiB／総16376MiB
  - JSUT corpus一次配布元: `https://sites.google.com/site/shinnosuketakamichi/publication/jsut`（ライセンス: 再配布不可、学術・非営利研究・個人利用の範囲で利用可）
  - YouTube候補: `https://www.youtube.com/watch?v=QxnWrMasELQ`（全長27:44。**冒頭180秒(3分)を目安に切り出す**。発話の区切りが悪い場合は前後で調整してよい）
- 遵守事項:
  - 采条件①②③（本指示書§2に記載）
  - CLAUDE.md「.venv/ ディレクトリを削除・変更すべからず」「本番データで実験すべからず」
  - JSUT音声ファイルはGitへコミットしない

## 7. 承認プロセス

- 計が本指示書を査（sa）へ査読依頼し、合格後に正式伝達する（本ファイルは査読依頼段階のドラフト）。
- 作(saku)はGPU実測ステップ完了後、直ちに計へ1行報告する（報告書全体の完成を待たない）。計はこれを受けて直ちに采へ1行報告する（jev-local再開可）。
- 報告書完成後、計が受領し、査(sa)の品質検査を経て、計が最終承認する。承認後、一次判断（可/否）を采へ報告する（tc-ops #546方針指示の報告要件）。
