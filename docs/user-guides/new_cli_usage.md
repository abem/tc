# CLIの使用方法

## 概要
コマンドラインからの文字起こしには、次の 2 つのエントリポイントがあります。

| コマンド | 位置づけ | 特徴 |
|----------|---------|------|
| `./tc` | 推奨 | `config/config.yaml` の `whisper.*` を読んで動作する。モデル・言語・デバイス等をオプションで上書きできる |
| `./transcribe.py` | プロファイル版 | モデル・言語を `--profile` で選ぶ。`config.yaml` の `whisper.model` / `whisper.language` / `whisper.device` は読まない |

`./transcribe`（シェルラッパー）は `.venv` を有効化して `transcribe.py` を実行するだけのコマンドです。
引数はそのまま `transcribe.py` に渡されます。

どちらも Python 製で、`#!/usr/bin/env -S uv run python3` により `uv` 経由で起動します。

## 入力に使えるもの

入力は `core/utils.py` の `detect_input_type` が自動判定します。

- YouTube の動画 URL
- X（旧 Twitter）の動画投稿 URL（`twitter.com` / `x.com` の `/<ユーザー>/status/<数字>` 形式）
- Google Drive の URL（`https://drive.google.com/...`）
- ローカルの音声ファイル

認識できない入力はエラーになります。入力を省略した場合は `config.yaml` の `gdrive.url` を使います。

## ./tc

```bash
./tc [入力] [オプション]

位置引数:
  input              YouTube / X の動画 URL・Google Drive URL・ローカルファイルパス
                     （省略時は config.yaml の gdrive.url を使用）

オプション:
  --output-dir DIR   出力ディレクトリ（デフォルト: output）
  --no-upload        Google Driveへのアップロードをスキップ
  --model MODEL      使用するモデル（config.yaml の whisper.model を上書き）
  --language LANG    言語コード（config.yaml の whisper.language を上書き）
  --device DEVICE    cuda / cpu / auto（config.yaml の whisper.device を上書き）
  --folder-id ID     Google Drive 入力の結果のアップロード先フォルダID
  --dry-run          設定読み込みと入力解決までで終了する（起動確認用）
  -h, --help         ヘルプ表示
```

### 使用例

```bash
# YouTube動画
./tc "https://www.youtube.com/watch?v=abc123"

# X(旧Twitter)の動画投稿
./tc "https://x.com/<ユーザー名>/status/<投稿ID>"

# ローカルファイル（英語指定・アップロードなし）
./tc /path/to/audio.wav --language en --no-upload

# 引数なし: config.yaml の gdrive.url を処理する
./tc
```

### 動作の要点

- 結果は `<出力ディレクトリ>/<日時>_transcription.txt` に保存される。
- Google Drive へのアップロードは、入力が YouTube または Google Drive の URL のときだけ行われる
  （ローカルファイルと X の URL はアップロードされない）。
  - Google Drive 入力: 元ファイルと同じフォルダに保存する。`--folder-id`（または `gdrive.upload_folder_id`）を
    指定した場合はそのフォルダに保存する。
  - YouTube 入力: Drive 上の「ボイス共有」フォルダの下に `YY_MM_DD_<動画タイトル>` フォルダを作って保存する
    （`handlers/gdrive.py` の `upload_youtube_transcription`）。`--folder-id` は使われない。
- `--dry-run` は文字起こしだけを省略する。URL を指定した場合、音声のダウンロード（YouTube / X / Google Drive）は
  実行される。
- 実行ログは標準出力と `logs/transcription.log` に出力される。

### 使えるモデルとエンジン

`--model`（または `whisper.model`）の文字列でエンジンが自動で切り替わります
（`core/transcription_interface.py` の `UnifiedTranscriber.__init__`）。

| モデル名に含まれる文字列 | エンジン | 例 |
|--------------------------|----------|----|
| `nemotron` | NemotronSubprocessEngine | `nvidia/nemotron-3.5-asr-streaming-0.6b` |
| `qwen3-asr` / `qwen3_asr` | Qwen3ASREngine | `Qwen/Qwen3-ASR-1.7B`（デフォルト） |
| 上記以外 | WhisperTranscriptionEngine | `kotoba-tech/kotoba-whisper-v2.2`、`openai/whisper-large-v3` |

Nemotron は専用の仮想環境 `venv-nemotron/` が必要です。未構築のまま指定すると、
`scripts/setup_nemotron_venv.sh` の実行を促すエラーになります。

```bash
# 初回のみ: Nemotron用の隔離環境を作る（既に venv-nemotron/ があれば何もしない）
./scripts/setup_nemotron_venv.sh

./tc audio.wav --model nvidia/nemotron-3.5-asr-streaming-0.6b --no-upload
```

## ./transcribe.py

```bash
./transcribe.py [入力] [オプション]

オプション:
  --profile, -p NUM   プロファイル番号（1 / 3 / 5 / 6）
  --language, -l LANG 言語（ja / en）。プロファイルの言語を上書きする
  --folder-id ID      Google Drive 入力の結果のアップロード先フォルダID
  --help              ヘルプ表示
```

`--output-dir` / `--no-upload` / `--model` / `--device` は持ちません。出力先は `output/` 固定で、
YouTube または Google Drive の入力は常にアップロードされます。

### プロファイル

| 番号 | 内容 | モデル |
|------|------|--------|
| 1（省略時） | 日本語（高速） | `kotoba-tech/kotoba-whisper-v2.2` |
| 3 | English | `openai/whisper-large-v3` |
| 5 | 日本語（最高精度・Qwen3-ASR） | `Qwen/Qwen3-ASR-1.7B` |
| 6 | カスタム設定 | 対話式に言語・モデル・デバイスを選ぶ |

番号に該当するプロファイルが無い場合（2・4 など）は、プロファイル 1 が使われます。
プロファイル 6 で選べるモデルは Qwen3-ASR・Whisper 系です（Nemotron は選べません）。

### 使用例

```bash
# 既定のプロファイル1で処理
./transcribe.py "https://www.youtube.com/watch?v=abc123"

# Qwen3-ASRで処理
./transcribe.py /path/to/audio.wav --profile 5

# 英語プロファイル
./transcribe.py /path/to/audio.wav --profile 3
```

入力を省略した場合は `config.yaml` の `gdrive.url` を使い、それも無ければ入力を対話式に尋ねます。

## WebUI

ブラウザから操作できる WebUI（`webui.py`、Streamlit 製）もあります。

```bash
uv run streamlit run webui.py --server.headless true --server.port 8501
```

「文字起こし」タブで YouTube / X / Google Drive の URL 入力またはファイルのアップロード、
モデル（Qwen3-ASR・kotoba-whisper・whisper-large-v3・Nemotron）・デバイス・言語の選択、タイムスタンプ付与、
認識ヒントの指定ができ、複数の入力はキューに積まれて順に処理されます。「履歴」タブで過去の変換結果を検索できます。
起動方法の詳細・常駐化は [WebUI内部サーバー構成](../system-docs/webui_architecture.md) を参照してください。

## 設定ファイル
`config/config.yaml` の項目は [設定ガイド](configuration.md) を参照してください。
