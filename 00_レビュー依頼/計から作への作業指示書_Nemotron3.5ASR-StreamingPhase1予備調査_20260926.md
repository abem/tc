# 計から作への作業指示書_Nemotron3.5ASR-StreamingPhase1予備調査_20260926

## 1. DoR (Definition of Ready) チェック

- [x] 1. 背景と目的が明確か
- [x] 2. ゴール（完了条件）が定義されているか（機械検査 exit 0 で判定可能か）
- [x] 3. スコープ（範囲）が限定されているか
- [x] 4. 成果物の仕様・要件が明確か
- [x] 5. 依存関係が解決されているか（本指示書は調査のみで環境変更を伴わないため、依存関係の実解決はスコープ外）
- [x] 6. 担当者と期限が設定されているか（担当: saku、期限: 2026-09-30）
- [x] 7. レビュー/承認者が明確か（査読=査(sa)、最終承認=計(kei)）

**発行前の追加検証（正典: 06d_operations.md「5.1 検査健全性の原則」規則1・規則5／ADR-010）**

- [x] 8. 検査コマンド自身が結果に混入しないことを検証したか（規則1）: §3の判定は成果物Markdownファイル内の見出し文字列の存在を`grep`で数える構造チェックであり、検査コマンド自身の起動文字列が対象ファイルの内容に混入することは構造上ない。
- [x] 9. 現況把握に必要な実測項目を網羅して提供したか（規則5）: 現行の依存関係・既存テスト資産の実測値（下記§6）を計が事前実測し提供済み（2026-09-26計実測、対象=現行ブランチ tip）。

## 2. 背景と目的

采方針指示（2026-09-26 11:56、sai→kei、agmsg ccc）により、`nvidia/nemotron-3.5-asr-streaming-0.6b`（Hugging Face）を第3の文字起こしエンジン候補として検討する。

采指示のPhase 1は「既存の日本語テスト音声で本モデルを試験導入し、既存エンジン(Qwen3-ASR/Whisper)と精度・処理速度を実測比較する」ことだが、計の事前実測により以下の未解決事項が判明した：

- 現行の生産用 `.venv` は `transformers==4.57.6` を使用しており、`pyproject.toml` にはコメントで「qwen-asr は transformers<5 を要求する」旨が明記されている（`pyproject.toml` L37-41）。
- 采方針指示は Nemotron の利用経路として「NeMo または Transformers(>=5.13.0)」を挙げている。Transformers経路を選ぶ場合、`transformers>=5.13.0` は現行の生産用 `.venv` の `transformers<5` 制約と直接衝突する。
- モデルカードにVRAM要件の明示値がない（采方針指示に記載済み）。
- 比較試験に使う日本語音声サンプルが未選定（`samples/e2e_sample.wav` は1秒のみでCER/RTF実測には不十分）。

上記の未解決事項があるままPhase1実測（実際のモデル実行・比較測定）に着手すると、生産用`.venv`を破壊するリスク（CLAUDE.md「.venv/ ディレクトリを削除すべからず」「依存関係の大幅な変更は段階的に行うべし」）がある。よって本指示書は、**Phase1実測に着手する前の予備調査（環境衝突可否の判定・隔離実行案の設計・テスト音声の選定案）のみ**を対象とする。実際のモデル実行・比較測定・依存関係の実インストールは、本予備調査完了・計承認後に別途作業指示書を発行する。

## 3. ゴール（完了条件）

予備調査完了報告書（パスは `REPORT` とする。命名規則: `00_レビュー依頼/作から計への予備調査完了報告_Nemotron3.5ASR-StreamingPhase1_[YYYYMMDD].md`）について、以下を実行しいずれも `OK` が出力されること:

```bash
REPORT="00_レビュー依頼/作から計への予備調査完了報告_Nemotron3.5ASR-StreamingPhase1_<YYYYMMDD>.md"

test -f "$REPORT" && echo OK_EXISTS

# 5項目の見出し存在を機械確認(項目本文の内容自体はkeiが目視で妥当性判断する。
# ここでは「見出しとして存在すること」のみを機械検査する)
for pat in "transformers衝突可否" "隔離実行案" "VRAM要件" "テスト音声選定" "Phase1実行計画"; do
  grep -q "^#.*${pat}" "$REPORT" && echo "OK_SECTION_${pat}" || echo "MISSING_SECTION_${pat}"
done

# .venv/ 及び pyproject.toml/uv.lock が調査中に変更されていないことの機械確認
git diff --name-only -- .venv pyproject.toml uv.lock | wc -l | grep -qx 0 && echo OK_NO_ENV_CHANGE || echo FAIL_ENV_CHANGED
```

報告書に含めるべき5項目の内容（機械検査は見出し存在のみ。内容の技術的妥当性はkeiが受領後に確認する）:

1. **transformers衝突可否**: `nemotron-3.5-asr-streaming` をTransformers経路（`transformers>=5.13.0`）で使う場合、現行生産用`.venv`（`transformers==4.57.6`、qwen-asr要求`<5`）と衝突するかの判定。NeMo経路を使えばTransformersバージョン制約を回避できるかの調査結果（NeMoのインストール要件・現行`.venv`との共存可否を含む）。
2. **隔離実行案**: Phase1実測（実際のモデル推論・比較測定）を、生産用`.venv`を一切変更せずに行う具体的な環境構築案（例: 別のuv venv/別ディレクトリでの検証環境作成手順）。コマンド例を含めること。
3. **VRAM要件**: モデルカード・config.json・NeMo/Transformers公式サンプルから、VRAM要件について確認できた情報（明示値がない場合は「明示値なし」と明記し、パラメータ数(600M)から推定できる範囲を記載）。
4. **テスト音声選定**: Phase1実測の比較試験に使う日本語音声サンプルの選定案（既存ローカル資産からの候補、または新規テスト用YouTube URLの提案）。本番のGoogle Driveフォルダを使わないこと。**`output/`配下（`output/queue_downloads/`等）は本番パイプライン実行由来の可能性があるため候補探索から除外すること**（査sa指摘・tc-ops #546査読コメント）。候補ごとに言語・長さ（秒）・入手経路を明記すること。
5. **Phase1実行計画**: 上記1-4の調査結果を踏まえた、Phase1実測（CER・RTF・ピークVRAM実測、Qwen3-ASR/Whisperとの比較）の具体的な実行計画案（隔離環境前提のコマンド案、実測手順、比較の出力形式案）。

## 4. 成果物の仕様・要件

- 予備調査完了報告書（Markdown、上記5項目を含む）
- 実際のモデル実行・推論・比較測定・依存関係の実インストールは本指示書のスコープ外（予備調査のみ）

## 5. 作業範囲（スコープ）

**含む**:
- 上記5項目の調査・設計提案（技術調査・設計方針の提示のみ）
- 既存コード（`core/transcription_interface.py`, `core/config.py`, `pyproject.toml`, `uv.lock`）との整合性確認

**含まない**:
- 生産用 `.venv/` への変更（削除・パッケージインストール等、一切禁止）
- `pyproject.toml` / `uv.lock` の変更
- 実際のモデルダウンロード・推論実行・比較測定（予備調査完了・計承認後、別途作業指示書を発行する）
- `UnifiedTranscriber` へのエンジン追加実装（Phase2相当。本指示書のスコープ外）

## 6. 依存関係と提供資料

- 使用ブランチ: `feature/nemotron35-asr-phase1-investigation-20260926`（計が作成・push済み、dev tip 89731a5から分岐）
- 参照資料:
  - 采方針指示（agmsg ccc、2026-09-26T11:56、sai→kei、原文全文）
  - `core/transcription_interface.py`（UnifiedTranscriber、デュアルエンジン自動切替構成）
  - `core/config.py`（TranscriptionConfig, UnifiedConfig）
- 実測項目（規則5、2026-09-26計実測、対象=現行ブランチtip）:
  - `pyproject.toml` L19: `"transformers>=4.56.1"`
  - `pyproject.toml` L37-41: 「qwen-asr は transformers<5 を要求するため、インストールすると transformers が…（下限固定の経緯）」「transformers 4.57.x でも回帰なし（レビュー検証済み）」
  - `uv.lock` L3002-3019: 実体は `transformers-4.57.6`
  - `samples/e2e_sample.wav`: 16kHz・1.0秒（CER/RTF実測には不十分。§3項目4で代替候補を選定すること）
  - `docs/user-guides/TROUBLESHOOTING.md` L413: テスト用YouTube URLの記載例あり（英語音声のため日本語比較には別途候補が必要）
  - 采方針指示に記載の参考モデル `nvidia/multitalker-parakeet-streaming-0.6b-v1` は、含めるかを作(saku)の判断とする（本指示書は必須としない）
- 遵守事項（CLAUDE.md べからず集より）:
  - `.venv/` ディレクトリを削除・変更すべからず
  - 本番データで実験すべからず（テスト用のYouTube URL・既存ローカル資産を使用する）
  - 依存関係の大幅な変更は段階的に行うべし

## 7. 承認プロセス

- 予備調査完了報告をkeiが受領し、査(sa)の査読を経て、Phase1実測（実際のモデル実行・比較測定）の作業指示書発行の可否を判断する。
- 承認後、Phase1実測のための作業指示書を計が別途起草し、査（sa）の査読を経て正式伝達する。
- 本指示書自体は査（sa）の査読を経て正式伝達する（本ファイルは査読依頼段階のドラフト）。
