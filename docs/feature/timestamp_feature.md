# タイムスタンプ機能 詳細仕様書

## 概要

文字起こし結果に、音声の先頭からの経過時間を `[MM:SS]` 形式で付ける機能です。
付き方はエンジンによって異なります。

| エンジン | タイムスタンプ |
|---|---|
| Qwen3-ASR（既定） | オプトイン。`tc` は `config/config.yaml` の `whisper.include_timestamps: true`、WebUI は「タイムスタンプ付与」のチェックで有効化。ForcedAligner を使い、保存ファイルの各行の行頭に `[MM:SS]` を付ける。`transcribe.py` は設定を渡さないので付かない |
| Whisper | 常時。設定に関係なく、エンジンが30秒ごとに `[MM:SS]` を行頭に付ける |
| Nemotron | 非対応。出力はタイムスタンプなしの1つのテキスト |

録音時刻（壁時計の時刻）を基準にした表示や、音声ファイルのメタデータ読み取りは実装していません。
`[MM:SS]` は常に音声先頭からの経過時間です。

## Qwen3-ASR のタイムスタンプ（`whisper.include_timestamps`）

### 設定

```yaml
# config/config.yaml
whisper:
  include_timestamps: true   # 既定は false
```

- 既定は `false`（既存の出力形式を変えないため）。
- `tc` は `whisper.include_timestamps` を読みます。WebUI は設定パネルの「タイムスタンプ付与」
  チェックボックスで切り替えます（Nemotron を選ぶと無効になります）。
- `transcribe.py`（Rich 対話型）は `include_timestamps` を渡さないため、Qwen3-ASR のタイムスタンプは付きません。
  これは保存関数の違いではなく、設定を渡さないことによる違いです（保存は3つの入口とも同じ関数が行います。下記）。
- この設定が作用するのは Qwen3-ASR だけです。Whisper 系は、設定に関係なく常に30秒ごとに付き、Nemotron は付きません。

### 仕組み

1. Qwen3-ASR で文字起こしします（Qwen3-ASR は300秒を超える音声をチャンクに分割します）。
2. 音声とその文字起こしテキストを ForcedAligner（`Qwen/Qwen3-ForcedAligner-0.6B`）に渡し、
   文字・単語単位の時刻を得ます。長音声ではチャンクごとに行い、チャンクの開始秒を加算します。
3. 文節ごとに改行された各行を、アライナー出力の対応する区間に近似的に対応付け、
   各行の開始・終了秒を `TranscriptionSegment`（`start` / `end`）に設定します。
   厳密な1対1対応の保証はなく、音声位置の目安として使う近似処理です。
4. 保存時に、各セグメントの先頭に `[MM:SS] `（開始秒）を付け、1セグメント1行で保存します。整形は
   `core.cli_workflow.format_transcript_text`（`save_transcription_text` から呼ばれる）で、`tc`・`transcribe.py`・WebUI が
   同じ `finalize_transcription` 経由で使います（`tc` の `save_result()` は、これを呼ぶだけの薄いラッパーです）。
   付く条件は、`result.metadata["timestamps_included"]` が真で、かつ `result.segments` があるときだけです。
   それ以外は `result.text` をそのまま保存します。分は 60 を超えても繰り上げません（75分30秒は `[75:30]`）。

ForcedAligner のモデル重みはメインモデルとは別のチェックポイントで、初回利用時に追加でダウンロードされます
（GPU メモリを約1.2GB追加で使います）。ForcedAligner のロードや実行に失敗した場合は、警告をログに出して
タイムスタンプなしの通常出力にフォールバックします。結果の `metadata["timestamps_included"]` で、
タイムスタンプが付いたかどうかを判別できます。

### 出力例

```
[00:00] こんにちは。
[00:03] 今日は文字起こしのテストをしています。
[00:08] それでは、
[00:09] 始めましょう。
```

### 保存先による違い

| 出力 | `[MM:SS]` |
|---|---|
| `tc` が保存するテキスト（`output/YYYYMMDD_HHMMSS_transcription.txt`） | `include_timestamps: true` で、アライナーが成功すれば付く |
| WebUI が保存するテキスト（同じファイル名） | 「タイムスタンプ付与」にチェックを入れ、アライナーが成功すれば付く（`tc` と同じ） |
| `transcribe.py` が保存するテキスト | Qwen3-ASR では付かない（`include_timestamps` を渡さないため。保存関数は同じ） |
| WebUI の画面の「文字起こし結果」欄 | 付かない（`result.text` をそのまま表示する。`[MM:SS]` が付くのは保存ファイル） |
| WebUI の「SRTプレビュー」 | チェックを入れたとき、SRT 形式で表示。区間の情報（セグメント）が無いときは「SRTを生成できるタイムスタンプ情報がありません」と表示される |

Whisper 系は、エンジンが `result.text` の中に `[MM:SS]` を入れているので、どの入口でも保存ファイルに付きます
（`timestamps_included` は設定されず、保存関数は `result.text` をそのまま保存します）。

## Whisper のタイムスタンプ

`WhisperTranscriptionEngine` は、音声を30秒ごとのチャンクに分け、各チャンクの文字起こしの行頭に
`[MM:SS]`（チャンクの開始秒）を付けます（`_add_timestamps_to_text`）。行内に `[MM:SS]` が紛れた場合は、
行頭に寄せます（`_ensure_timestamps_at_line_start`）。`TranscriptionResult.segments` は、このテキスト中の
`[MM:SS]` を解析した30秒区間です。

```
[00:00] はい、ではお願いします。
[00:30] ありがとうございます。
```

## 実行方法と確認

```bash
# 設定の include_timestamps を true にして、ローカルファイルを処理（アップロードなし）
./tc audio.wav --no-upload

# 最新の出力ファイルを確認
ls -la output/
head -20 output/YYYYMMDD_HHMMSS_transcription.txt
```

## トラブルシューティング

#### タイムスタンプが付かない

次の順に確認してください。

- 使っているモデルが Qwen3-ASR か（Whisper は常に付きます。Nemotron は付きません）
- `whisper.include_timestamps` が `true` か（`tc` の場合）、または WebUI の「タイムスタンプ付与」にチェックを入れたか。
  `transcribe.py` は `include_timestamps` を渡さないため、Qwen3-ASR では付きません
- 見ているのが保存ファイルか（WebUI の画面の結果欄には付きません。保存された `output/..._transcription.txt` を見てください）
- ログに「ForcedAlignerのロードに失敗しました」「ForcedAlignerの実行に失敗しました」が出ていないか
  （ログは `logs/transcription.log`）。初回はモデルの追加ダウンロードにネットワークが必要です

## テスト

- `tests/test_core_transcription_interface_timestamps.py`: エンジン側のタイムスタンプ処理
- `tests/test_tc_save_result.py`: `tc` の `save_result()`（`format_transcript_text` を呼ぶ薄いラッパー）が `[MM:SS]` を付ける処理

```bash
uv run pytest tests/test_core_transcription_interface_timestamps.py tests/test_tc_save_result.py -v
```
