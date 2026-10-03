# CLIの使用方法

## 概要
コマンドラインからの文字起こしには、次の 2 つのエントリポイントがあります。

| コマンド | 位置づけ | 特徴 |
|----------|---------|------|
| `./tc` | 推奨 | `config/config.yaml` の `whisper.*` を読んで動作する。モデル・言語・デバイス等をオプションで上書きできる |
| `./transcribe.py` | プロファイル版 | モデル・言語を `--profile` で選ぶ。`config.yaml` の `whisper.model` / `whisper.language` / `whisper.device` は読まない |

`./transcribe`（シェルラッパー）は `.venv` を有効化して `transcribe.py` を実行するだけのコマンドです。
引数はそのまま `transcribe.py` に渡されます。

`./tc` と `./transcribe.py` は Python 製で、`#!/usr/bin/env -S uv run python3` により `uv` 経由で起動します
（`.venv` は自動で使われます）。`./transcribe` だけは `.venv` を直接有効化するので、先に `uv sync` で `.venv` を
作っておく必要があります。

保存・アップロード・変換履歴・一時音声の削除は、どちらも共通の処理（`core/cli_workflow.py` の
`finalize_transcription`）が行います。

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
  実行される。取得した一時音声は、終了前に削除される。表示は `ドライラン: 起動確認OK (input=<音声のパス>)`、
  終了コードは 0。ローカル音声を指定したときは、出力ディレクトリは作られず、何も書き込まれない。
- 実行ログは標準出力と `logs/transcription.log` に出力される（ログ行は `日時 - ロガー名 - INFO - ` で始まる）。
- 入力の取得・文字起こし・保存の途中で失敗・中断しても、YouTube / X と Google Drive 由来の一時音声は削除される
  （削除に失敗したときは警告だけ）。ローカルファイルは削除しない。
- yt-dlp が見つからないときは、自動インストールはせず、`uv sync` を案内するエラーで終了コード 1 で止まる。
  yt-dlp の呼び出しにはタイムアウトがある（メタデータ 60 秒、ダウンロード中に出力が 300 秒途絶えると中断）。
  詳細は [トラブルシューティング](TROUBLESHOOTING.md)。
- 画面には、保存先に続けて結果の先頭 500 文字のプレビュー（`文字起こし結果（最初の500文字）:`）が出る。
- 変換履歴は `output/history.db` に記録される（実行したディレクトリ基準のパスで、`--output-dir` では変わらない。
  記録に失敗しても処理は続行し、`変換履歴の記録に失敗しました: ...` と表示する）。

### 使えるモデルとエンジン

`--model`（または `whisper.model`）の文字列でエンジンが自動で切り替わります
（`core/engine_factory.py` の `create_engine`）。

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

### `./tc` との違い

| 項目 | `./tc` | `./transcribe.py` |
|------|--------|-------------------|
| 起動時の表示 | ログ行のみ | `Transcribe Audio - AI音声文字起こしツール` のバナー、`入力タイプ: ...` を表示 |
| 開始時の表示 | `文字起こし開始: モデル=..., 言語=..., デバイス=...`（ログ） | 常に `日本語音声文字起こしを開始 (デバイス: ...)`（プロファイル 5 や英語でも同じ文言） |
| `--language` | 任意の文字列（`ja` / `en` 以外も受け付ける） | `ja` / `en` のみ |
| 設定ファイルの `whisper.*` | モデル・言語・デバイス・`include_timestamps` を読む | `context_file` だけ読む（モデル・言語はプロファイル） |
| 出力先・アップロード | `--output-dir`、`--no-upload` で変えられる | `output/` 固定。YouTube / Google Drive 入力は常にアップロード |
| 結果のプレビュー | 先頭 500 文字を表示 | 表示しない（保存先を表示） |
| 設定ファイルが無い・読めない | `設定ファイルが見つかりません: <パス>`（YAML の構文エラーはトレースバック） | `設定ファイルエラー: <原因>` を表示して終了コード 1 |
| yt-dlp が無い | エラーを表示して終了コード 1 | `YtDlpNotFoundError` を捕捉せず、トレースバックで終了 |
| 入力を認識できない | `入力を認識できません: <入力>`（終了コード 1） | `エラー: 入力を認識できません: <入力>`（終了コード 1） |

### 保存形式（`[MM:SS]` の有無）

保存形式は [タイムスタンプ機能](../feature/timestamp_feature.md) が正本です。`./transcribe.py` の要点は次のとおりです。

| プロファイル | エンジン | 保存テキスト |
|--------------|----------|--------------|
| 1・3（Whisper 系） | Whisper | 常に 30 秒ごとの `[MM:SS]` 付き（エンジンが付ける） |
| 5（Qwen3-ASR） | Qwen3-ASR | 付かない（`include_timestamps` を渡さないため） |
| 6（カスタム） | 選んだモデルによる | Whisper 系なら付く、Qwen3-ASR なら付かない |

`./tc` は、Qwen3-ASR で `whisper.include_timestamps: true` のとき行頭に `[MM:SS]` を付けます。Nemotron はどちらの
入口でも付きません。

## WebUI

ブラウザから操作できる WebUI（`webui.py`、Streamlit 製）もあります。本番環境では systemd のサービスが
常駐させています。手元で起動する場合は次のコマンドです。

```bash
uv run streamlit run webui.py --server.headless true --server.port 8501
```

「文字起こし」タブで YouTube / X / Google Drive の URL 入力またはファイルのアップロード、
モデル（Qwen3-ASR・kotoba-whisper・whisper-large-v3・Nemotron）・デバイス・言語の選択、タイムスタンプ付与、
認識ヒントの指定ができ、複数の入力はキューに積まれて順に処理されます。利用者に見える要点は次のとおりです。

- 進捗バーと「経過 / 残り約」を表示します（Nemotron、Qwen3-ASR の 300 秒以下の音声、Google Drive のダウンロードは
  経過時間のみ。残り時間は進捗 3% から）。
- アップロードは `output/uploads/<一意>/<ファイル名>` に保存され、7 日を過ぎたものは新しい入力のたびに削除されます。
  URL 入力の作業領域 `output/queue_downloads/` は 1 日で削除されます。
- タイムスタンプ付与にチェックを入れると、保存テキストに `[MM:SS]` が付き、「SRTプレビュー」が出ます。
- 「履歴」タブで、日付範囲とキーワード（3 文字以上）で検索できます。古い履歴の一括削除は 2 段階で、
  データベースの記録だけが消えます。

使い方の手順は [チュートリアル](TUTORIAL.md)、起動・常駐化・内部構成は
[WebUI内部サーバー構成](../system-docs/webui_architecture.md) を参照してください。

## 処理後に出るファイル

| ファイル・ディレクトリ | 内容 | 出す入口 |
|------------------------|------|----------|
| `output/<日時>_transcription.txt` | 文字起こし結果（`--output-dir` で変更できるのは `./tc` だけ） | すべて |
| `output/history.db` | 変換履歴（SQLite）。実行したディレクトリ基準で固定 | すべて |
| `logs/transcription.log` | 実行ログ（pytest 実行中は `logs/transcription_test.log`） | すべて |
| `output/uploads/` | アップロードされたファイル（7 日で削除） | WebUI のみ |
| `output/queue_downloads/` | URL 入力のダウンロードの作業領域（1 日で削除） | WebUI のみ |

YouTube / X の音声は、取得の間 `--output-dir`（WebUI は `output/queue_downloads/<トークン>/`）に置かれ、処理の終了時に削除されます。

## 設定ファイル
`config/config.yaml` の項目は [設定ガイド](configuration.md) を参照してください。
