# (番号未採番・暫定発行): 検査報告書 - クローズ前improvement2点(yt-dlp依存明示化・言語サポートガイド是正)

> **発行日**: 2026年08月02日 / **発行者**: 査ロール(sa) / **文書種別**: 検査報告書
> **検査対象**: `pyproject.toml`・`uv.lock`・`docs/user-guides/language_support_guide.md`（ブランチ: `feature/closing-improvements-2026-08-02`、main起点） / **宛先**: 計ロール(kei)
> **注記**: 前回同様、文書番号採番インフラ未整備のため番号なしの暫定発行とする(計承認済み)。`config/config.yaml`は本タスク対象外(ユーザー自身が動作確認のため編集中と計から申し送りあり)のため検査対象から除外した。

## 検査結果

### 判定: **合格**

## 1. 検査項目(1: yt-dlp依存関係明示化)

| 確認項目 | 結果 | 備考 |
|---------|------|------|
| pyproject.toml差分 | ✅ | `"yt-dlp>=2025.1.1",` の1行追加のみ(1 insertion/0 deletion)。報告と一致 |
| uv.lock差分 | ✅ | yt-dlpパッケージエントリ(version 2026.7.4)追加。11 insertions/0 deletions |
| `uv sync`再現 | ✅ | 査自身が実行し「Resolved 142 packages」「Audited 135 packages」で正常終了、エラーなし |
| .venv優先ロジックの実機確認 | ✅ | 査自身が`YouTubeClient()`を生成し`yt_dlp_path`を確認したところ`.venv/bin/yt-dlp`であることを確認(報告と一致) |
| .venv内yt-dlpのバージョン | ✅ | `.venv/bin/yt-dlp --version` = `2026.07.04`。uv.lockの解決バージョン(2026.7.4)と一致 |

## 2. 検査項目(2: 言語サポートガイド是正)

| 確認項目 | 結果 | 備考 |
|---------|------|------|
| 差分数量 | △(軽微な不一致) | 査実測: 92 insertions/132 deletions。報告値「93 insertions/132 deletions」との差はinsertions側で1のみ(deletionsは完全一致)。合否に影響しない軽微な誤差と判断 |
| `is_qwen3_model`ベースのエンジン選択記載の正確性 | ✅ | `core/transcription_interface.py`の`UnifiedTranscriber.__init__`が`Qwen3ASREngine.is_qwen3_model(transcription_config.model)`のみで判定し、言語を見ないことをコード直読で確認。記載と一致 |
| `lang_map`記載の正確性 | ✅ | `core/transcription_interface.py`内`lang_map = {"ja": "Japanese", "en": "English"}`の実在を確認 |
| `select_model()`dead code記載の正確性 | ✅ | `core/cli_common.py:select_model()`をリポジトリ全体で検索し、定義以外の呼び出し箇所が0件であることを確認(dead codeという記載は正確) |
| `exec_local.sh`言及削除の妥当性 | ✅ | リポジトリ内に`exec_local.sh`という実ファイルが存在しないことを確認済み(削除は妥当) |
| 実機再現(a: デフォルトQwen3-ASR) | ✅ | 査自身が再現(§3.1) |
| 実機再現(b: --modelでWhisperTranscriptionEngineへ切替) | ✅ | 査自身が再現(§3.2) |

## 3. 証拠: 実機再現ログ(査自身による独立実行)

### 3.1 デフォルト実行(Qwen3-ASR)
```
$ ./tc samples/e2e_sample.wav --no-upload | grep "Qwen/Qwen3-ASR-1.7B"
文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
```

### 3.2 モデル上書き(WhisperTranscriptionEngineへの切替)
```
$ ./tc samples/e2e_sample.wav --model "kotoba-tech/kotoba-whisper-v2.2" --language ja --no-upload
文字起こし開始: モデル=kotoba-tech/kotoba-whisper-v2.2, 言語=ja, デバイス=cuda
perf.WhisperTranscriptionEngine - INFO - Started: transcribe_e2e_sample.wav
...
```
`WhisperTranscriptionEngine`起動ログを確認し、モデル名変更のみでエンジンが切り替わることを実機で確認した。

## 4. 単体テスト

```
$ uv run pytest -q
..................................ss.................                    [100%]
51 passed, 2 skipped in 1.50s
```
報告どおり新規テスト追加なし・全件一致。

## 5. 合格判定前の3点自己反証

- **検証範囲**: 対象3ファイル(pyproject.toml/uv.lock/language_support_guide.md)の差分内容全件と、ドキュメントが主張する技術的記載(エンジン選択・lang_map・dead code)をすべてコード直読で裏取りした。「文言の存在確認」で終わらせず、記載が現在の実装と一致するかを個別に検証した(CLAUDE.mdの過去教訓に基づく)
- **証拠**: 判定根拠は査自身が直接実行したコマンド出力・直接読解したコード。差分数量も査自身の`git diff --numstat`実測に基づく
- **判定**: 検出した不備は§2の軽微な数量誤差(1行)のみで、内容面の不備は無い。config.yamlは計からの事前申し送りどおり対象外として検査から除外した。条件付き合格は用いていない

## 6. 参考情報(合否に影響しない・別タスクの検討材料)

本タスクの対象外だが、`exec_local.sh`言及・`UnifiedConfig.get('whisper', 'language_models')`類似の記載が以下のファイルにも残存していることを確認した(リポジトリ全体grep): `docs/user-guides/TROUBLESHOOTING.md`・`docs/user-guides/configuration.md`・`docs/system-docs/current_status_2025_july.md`・`docs/user-guides/TUTORIAL.md`・`docs/system-docs/system_overview_2025.md`・`DEVELOPMENT.md`・`README.md`。今回の是正と同種の問題が他ファイルにも残っている可能性があるため、将来的な是正対象の候補として記録する(本タスクの合否には無関係)。

## 7. 計ロールへの報告

判定は合格。§2の軽微な数量誤差は記録のみで対応不要。§6は将来検討材料として参考共有する。最終承認をお願いする。

**文書終了**
