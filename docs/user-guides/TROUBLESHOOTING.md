# トラブルシューティングガイド 🛠️

音声文字起こしシステムで発生する可能性のある問題と解決方法をまとめました。

見出しの書き方は 2 種類です。`エラー: ...` は、このリポジトリのコードが出す文言（画面やログにそのまま出ます）です。
`現象: ...` は、外部ライブラリ（PyTorch、yt-dlp、Google API など）が原因で、エラーの文が一定しないものです。
外部ライブラリが出す文言には、出典を書きました。

## 📋 目次

- [環境・インストール関連](#環境インストール関連)
- [GPU・CUDA関連](#gpucuda関連)
- [音声処理関連](#音声処理関連)
- [YouTube・Google Drive関連](#youtubegoogle-drive関連)
- [文字起こし品質関連](#文字起こし品質関連)
- [設定・認証関連](#設定認証関連)
- [パフォーマンス関連](#パフォーマンス関連)
- [ログ・デバッグ関連](#ログデバッグ関連)

## 🔧 環境・インストール関連

### エラー: `ModuleNotFoundError: No module named 'torch'`

**原因:** PyTorchがインストールされていない

**解決策:**
```bash
# 依存関係がインストール済みか確認 (uv 管理)
uv run python -c "import torch; print('✓ torch OK')"

# 依存関係の再インストール
uv sync

# ※pip で個別インストールする手順は廃止されました。
#   依存関係は pyproject.toml/uv.lock を情報源として uv sync で管理されます。
```

**確認方法:**
```bash
uv run python3 -c "import torch; print('PyTorch version:', torch.__version__)"
uv run python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

### エラー: `ModuleNotFoundError: No module named 'transformers'`

**原因:** Transformersライブラリがインストールされていない

**解決策:**
```bash
# uv で依存関係を再同期 (pyproject.toml/uv.lock が情報源)
uv sync

# ※依存パッケージを uv.lock の外で個別に追加するとバージョン不整合の原因になるため、
#   pyproject.toml の依存を編集して uv sync してください。
```

### 現象: `uv sync` が Python 3.12 を要求して失敗する

**原因:** このプロジェクトは Python 3.12 以上が必要です（`pyproject.toml` の `requires-python = ">=3.12"`）。
uv が使える Python 3.12 以上を見つけられていません。エラーの文は uv が出すもので、このリポジトリには無い文言です。

**解決策:**
```bash
# Python 3.12 を uv で入れる
uv python install 3.12

# 依存関係をインストール (.venv を自動作成)
uv sync
```

### エラー: `./tc: Permission denied`

**原因:** 実行権限がない

**解決策:**
```bash
# 実行権限を付与
chmod +x tc transcribe transcribe.py

# 確認
ls -la tc transcribe transcribe.py
```

### エラー: `.venv` の依存関係が壊れている / `ModuleNotFoundError`

**原因:** .venv の依存関係が破損・不整合を起こしている

**解決策:**
```bash
# .venv を削除して依存関係を再インストール (uv が管理)
rm -rf .venv
uv sync
```

### エラー: `Nemotron隔離venvが未構築です`

**原因:** Nemotron モデル（`nvidia/nemotron-3.5-asr-streaming-0.6b` など、モデル名に `nemotron` を含むもの）を指定したが、
専用の仮想環境 `venv-nemotron/` が無い

**解決策:**
```bash
# Nemotron用の隔離環境を作る
./scripts/setup_nemotron_venv.sh

# venv-nemotron/ が壊れている場合は、削除してから作り直す
# （スクリプトは venv-nemotron/ が既にあると何もせずに終了する）
rm -rf venv-nemotron
./scripts/setup_nemotron_venv.sh
```

## ⚡ GPU・CUDA関連

### 現象: `CUDA out of memory`

出典: PyTorch が出す文言です（このリポジトリのコードには無い）。

**原因:** GPU メモリ不足

**解決策1: CPUを使用**
```bash
./tc --device cpu "audio.wav"
```

**解決策2: GPU メモリ確認・クリア**
```bash
# GPU使用状況確認
nvidia-smi

# 他のGPUプロセスを終了
sudo fuser -v /dev/nvidia*
sudo kill -9 <process_id>

# Pythonプロセス再起動
```

### 現象: CUDA が使えない（`torch.cuda.is_available()` が `False`）

このリポジトリのコードに `CUDA device not found` という文言はありません。`--device cuda`（または `config.yaml` の
`device: cuda`）で GPU が使えないときの文は PyTorch 側のもので、一定しません。

**原因:** CUDA ドライバーまたはPyTorchのCUDA版がインストールされていない

**まず試すこと:** `--device auto` なら、CUDA が使えるときは `cuda`、使えないときは `cpu` になります
（`core/utils.py` の `resolve_device`）。

**解決策:**
```bash
# CUDA確認
nvidia-smi
nvcc --version

# PyTorchのCUDAサポート確認 (uv 経由)
uv run python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())"

# CUDA版PyTorchの再インストール (.venv を作り直して uv sync で復元)
# ※torch の CUDA ビルドは uv.lock で管理されているため、pip での個別上書きは避ける。
rm -rf .venv
uv sync
```

### 現象: `RuntimeError: No CUDA GPUs are available`

出典: PyTorch が出す文言です（このリポジトリのコードには無い）。

**原因:** GPU が認識されていない、またはドライバーの問題

**解決策:**
```bash
# GPU確認
lspci | grep -i nvidia

# ドライバー確認
nvidia-smi

# ドライバー再インストール（Ubuntu）
sudo apt purge nvidia-*
sudo apt autoremove
sudo apt install nvidia-driver-535  # 適切なバージョン

# システム再起動
sudo reboot
```

### 現象: `torch.cuda.OutOfMemoryError` (継続的に発生)

出典: PyTorch の例外名です（このリポジトリのコードには無い）。

**原因:** GPUメモリリークまたは断片化

**解決策:**
```python
# 明示的なメモリクリア（デバッグ用）
import torch
torch.cuda.empty_cache()
torch.cuda.synchronize()
```

```bash
# システム再起動（根本的解決）
sudo reboot

# または GPU リセット
sudo nvidia-smi --gpu-reset
```

## 🎵 音声処理関連

### エラー: `入力を認識できません: <入力>`

**原因:** 入力のファイルが存在しない、またはURLの形式が対応外（`./tc` は終了コード 1 で止まります）

`./tc` が受け付ける入力は、YouTube の動画URL、X（旧 Twitter）の動画投稿URL
（`https://x.com/<ユーザー名>/status/<数字>` 形式）、Google Drive のURL（`https://drive.google.com/...`）、
存在するローカルファイルのパスです。これ以外は `入力を認識できません: ...` になります。

**解決策:**
```bash
# ファイル存在確認
ls -la audio.wav

# ファイル形式確認
file audio.wav

# 読み込めない形式は変換する
ffmpeg -i audio.mp3 audio.wav
ffmpeg -i audio.m4a audio.wav
ffmpeg -i audio.ogg audio.wav
```

WebUI でアップロードできるファイルは `wav` / `mp3` / `mp4` / `m4a` / `flac` / `ogg` です
（`core/config.py` の `SystemConfig.allowed_file_types`）。

`Audio file not found: <パス>`（`FileNotFoundError`）は、エンジンが音声ファイルを開く直前の確認が出す文言です。
`./tc` と `./transcribe.py` は、入力の認識の段階で先に `入力を認識できません` で止まるため、通常はこの文言には
なりません（Python API から直接呼んだときや、入力の認識のあとでファイルが消えたときに出ます）。

### 警告: `チャンクが失敗し` / `反復ループを検出しました`

**原因:** 長い音声は自動で分割して処理されます（Qwen3-ASR は 300 秒ごと）。そのうち一部の分割区間で
認識に失敗した、または同じ語句を繰り返す出力になった

実行後に `⚠️  警告: N個のチャンクが失敗し...` または `⚠️  警告: N個のチャンクで反復ループを検出しました...`
が表示され、出力テキストの該当位置に `[チャンクN失敗]` / `[チャンクN反復検出のため破棄]` が入ります。

**解決策:**
```bash
# ログで該当チャンクのエラー内容を確認
grep -n "Chunk" logs/transcription.log | tail -20

# 同じファイルをもう一度処理する（一時的な失敗なら解消することがある）
./tc audio.wav --no-upload

# 音声を手動で分割して個別に処理する
ffmpeg -i long_audio.wav -t 1800 -c copy part1.wav
ffmpeg -i long_audio.wav -ss 1800 -t 1800 -c copy part2.wav
./tc part1.wav --language ja
./tc part2.wav --language ja
```

### 現象: 音声ファイルが読み込めない（`Unable to load audio file` ではない）

このリポジトリのコードに `Unable to load audio file` という文言はありません。音声のデコードは librosa などの
外部ライブラリが行い、読めないときの文は一定しません。

**原因:** 音声ファイルが破損またはエンコードの問題

**解決策:**
```bash
# ファイル修復
ffmpeg -i broken_audio.wav -c:a pcm_s16le fixed_audio.wav

# 音声情報確認
ffprobe -v error -show_format -show_streams audio.wav

# 再エンコード
ffmpeg -i audio.wav -ar 16000 -ac 1 -c:a pcm_s16le clean_audio.wav
```

### 現象: サンプリングレートが原因ではないかと疑うとき

このリポジトリのコードに `Sample rate not supported` という文言はありません。Qwen3-ASR（長音声）・Whisper・Nemotron は、
音声を読み込む時点で 16 kHz に変換する実装なので、サンプリングレートだけが原因になることは通常ありません。
読み込みに失敗するときは、前の項目（音声ファイルが読み込めない）と同じ手順を試してください。

手動で 16 kHz に揃えて試す場合:

**解決策:**
```bash
# サンプリングレート確認
ffprobe -v quiet -select_streams a:0 -show_entries stream=sample_rate audio.wav

# 16kHzに変換（推奨）
ffmpeg -i audio.wav -ar 16000 audio_16khz.wav

# 変換後処理
./tc audio_16khz.wav --language ja
```

## 📺 YouTube・Google Drive関連

### エラー: `yt-dlp が見つかりません。プロジェクトのディレクトリで uv sync …`

文言の全体は `yt-dlp が見つかりません。プロジェクトのディレクトリで `uv sync` を実行して依存関係をインストールしてください(自動インストールは行いません)。` です。

**原因:** yt-dlp の実行ファイルを、`PATH`、現在の Python と同じ `bin/`、実行したディレクトリの `.venv/bin/yt-dlp` の
順に探しても見つからなかった。自動で `pip install` はしません（uv 管理の `.venv` を書き換えないため）。

**解決策:**
```bash
# プロジェクトのディレクトリで依存関係を同期する（yt-dlp は pyproject.toml の依存に入っている）
uv sync

# 確認
uv run yt-dlp --version
```

入口ごとの見え方:
- `./tc`: ログに `ERROR` として出て、終了コード 1 で止まります。
- `./transcribe.py`: このエラー（`YtDlpNotFoundError`）を捕捉せず、トレースバックで終了します（終了コード 1）。
- WebUI: 該当の項目が失敗になり、完了済み一覧の `[失敗]` に同じ文が出ます。

### エラー: `Failed to get video info` / `Audio extraction failed`

**原因:** YouTube / X のURLの形式、プライベート動画、削除された動画、地域制限、ネットワークの不調、または
yt-dlp が動画の取得に失敗した（YouTube と X の動画は yt-dlp で取得します）。取得できなかった理由は、
同じ時刻のログ（`logs/transcription.log`）の `Failed to get video info: ...` の行に、yt-dlp のエラー文として
出ます。

**解決策:**
```bash
# URL形式確認
echo "https://www.youtube.com/watch?v=VIDEO_ID"  # 正しい形式（YouTube）
echo "https://x.com/<ユーザー名>/status/<投稿ID>"   # 正しい形式（X）

# 手動ダウンロード（デバッグ用。yt-dlp は uv 環境にインストール済み）
uv run yt-dlp --extract-audio --audio-format wav "動画のURL"

# yt-dlp のバージョン確認（動画サイトの仕様変更で古いと失敗することがある）
uv run yt-dlp --version
```

ブラウザで開いて公開されていない動画のときは、公開動画のURLで試してください。

### 取得が止まる・タイムアウトで失敗する（yt-dlp）

yt-dlp の呼び出しには、次のタイムアウトがあります（`handlers/youtube.py`）。

| 場面 | 上限 | 画面・ログの文言 |
|------|------|------------------|
| メタデータの取得 | 60 秒 | ログに `Timed out getting video info (60s): <URL>`、続けて `Failed to get video info` で止まる |
| ダウンロード中に yt-dlp の出力が途絶える | 300 秒 | `yt-dlp出力が300秒間停止したため中断: <URL>` |
| 単発の通信の無応答 | 30 秒 | yt-dlp 自身が検知する（`--socket-timeout 30`）。そのあとの文は yt-dlp が出す |

どれも、再実行すると解消することがあります（一時的なネットワークの不調など）。繰り返すときは、
`uv run yt-dlp --version` と手動ダウンロード（上の「手動ダウンロード」）で、yt-dlp 単体で取得できるか確認してください。
ダウンロードの途中で止まったときの部分ファイル（`.part` など）は、削除されずに残ることがあります。`./tc` では
`--output-dir`（既定は `output/`）に、WebUI では `output/queue_downloads/<トークン>/` に残り、WebUI のものは 1 日を過ぎると
自動で削除されます。

### エラー: `Google Drive APIの認証に失敗しました: …`

英語の `Google Drive authentication failed` という文言はありません。画面とログには日本語の
`Google Drive APIの認証に失敗しました: <原因>`（`handlers/gdrive_auth.py`）が出ます。`<原因>` には、
認証ファイルが無いなどの具体的な理由が入ります。

**原因:** 認証ファイルまたは権限の問題

認証ファイルは、`./tc` を実行したディレクトリ直下の `credentials.json`（OAuthクライアント情報）と
`token.pickle`（認証済みトークン）が固定名で使われます（`config.yaml` で場所は変えられません）。

**解決策:**
```bash
# credentials.json確認（実行するディレクトリ直下に置く）
ls -la credentials.json

# 認証ファイル権限確認
chmod 600 credentials.json

# Google Drive API有効化確認
# https://console.cloud.google.com/apis/library/drive.googleapis.com
```

- `token.pickle` が無い・壊れている・更新できない場合は、再認証が始まります。表示される認証URLを
  ブラウザで開いて認証し、リダイレクト先の完全なURLを貼り付けてください（標準入力で待機するため、
  バックグラウンド実行や入力を受け付けない環境では先に進めません）。
- OAuth同意画面の公開ステータスが「テスト」の場合は、自分のGoogleアカウントを「テストユーザー」に追加します。

### エラー: `Failed to download file: …` / `Failed to upload file: …`

Google Drive からのダウンロード、または結果のアップロードに失敗したときの文言です（`handlers/gdrive.py`）。
`:` のあとに、Google API が返した理由が付きます。API の使用量の制限、権限（共有されていないファイル）、
ファイルIDの誤りなどが原因になりますが、具体的な文は Google API 側のもので一定しません。

**解決策:**
- 少し時間をおいて、同じコマンドを再実行する
- Drive 上のファイルに、認証したアカウントがアクセスできるか確認する
- 先に Drive から手動でダウンロードし、ローカルファイルとして処理する（`--no-upload` を付ければ結果は `output/` にだけ残る）

入口ごとの見え方:
- ダウンロードの失敗: `./tc` は例外のトレースバックで止まります。WebUI は該当の項目が `[失敗]` になります。
- アップロードの失敗（`./tc`）: 結果のテキストは先に `output/` に保存済みです。そのあと例外で止まるため、
  変換履歴（`output/history.db`）には記録されません。Drive 入力の一時音声は削除されます。
- アップロードの失敗（`./transcribe.py`）: `Google Driveアップロードエラー: …` と表示され、処理は続行します。
- アップロードの失敗（WebUI）: `Google Driveアップロードに失敗しました: …` の警告が出て、結果は保存・履歴記録されます。
- `アップロードに失敗しました`（`./tc`）: アップロードの処理は例外なく終わったが、Drive 上のURLが得られなかったときです。

### WebUI で失敗したとき

- 文字起こし中の失敗: 画面に `文字起こしに失敗しました: <原因>` が出て、その項目は完了済み一覧に `[失敗]` として残ります。
  後ろに待っている項目は、そのまま次の処理に進みます。
- 入力の取得（ダウンロード等）の失敗: 同じく `[失敗]` として残ります。原因の文は、上の各項目（yt-dlp、Google Drive）を
  参照してください。詳しいログは `logs/transcription.log` にあります（`状態遷移 item_id=... ->FAILED` の行）。
- 履歴の記録の失敗: `変換履歴の記録に失敗しました: ...` の警告が出ますが、文字起こしの結果は保存されています。
- 一時音声の削除の失敗: 警告が出るだけで、結果は失敗になりません。


## 📝 文字起こし品質関連

### 問題: 文字起こし結果が短すぎる

**原因:** 音声品質の問題、言語指定の不一致、または一部区間の認識失敗

**解決策:**
```bash
# ログを保存して確認（ログは logs/transcription.log にも記録される）
./tc "audio.wav" --no-upload 2>&1 | tee debug.log

# 出力テキストに [チャンクN失敗] / [チャンクN反復検出のため破棄] が無いか確認
grep -n "チャンク" output/*_transcription.txt

# 言語を明示する（既定は自動判定）
./tc --language ja "audio.wav"

# 別のモデル（別のエンジン）で比較する
./tc --model openai/whisper-large-v3 --language ja "audio.wav"
```

### 問題: 句読点がない

**原因:** モデルの出力の違い

**解決策:**
```bash
# モデルによって出力は異なるため、別のモデルを試して比較する
./tc --model Qwen/Qwen3-ASR-1.7B "audio.wav"
./tc --model kotoba-tech/kotoba-whisper-v2.2 --language ja "audio.wav"
```

### 問題: 専門用語が正しく認識されない

**原因:** 音声が不明瞭、または固有名詞・専門用語が誤変換されている

**解決策:**
```bash
# 音声品質向上
ffmpeg -i audio.wav -af "loudnorm,highpass=f=200" enhanced_audio.wav

# 認識ヒントを登録する（Qwen3-ASR専用）
cp config/context_hints.txt.sample config/context_hints.txt
# context_hints.txt に、誤変換される語を1行に1つずつ書く
```

認識ヒントの詳細は [設定ガイド](configuration.md) の `context_file` を参照してください。
ヒントに書いた語が、発話されていない区間の出力に混入することがあるため、結果は目視で確認してください。

### 問題: タイムスタンプが付かない

**原因:** エンジンと入口によって、付き方が違います。

| 使っているもの | `[MM:SS]` |
|----------------|-----------|
| Whisper 系のモデル | 設定に関係なく、常に 30 秒ごとに付く |
| Qwen3-ASR（既定）を `./tc` で | `whisper.include_timestamps: true` のときだけ付く |
| Qwen3-ASR を WebUI で | 「タイムスタンプ付与」にチェックを入れたときだけ、**保存ファイル**に付く（画面の結果欄は付かない） |
| Qwen3-ASR を `./transcribe.py` で | 付かない（設定を渡さないため） |
| Nemotron | 付かない |

**解決策:**
```yaml
# config/config.yaml
whisper:
  include_timestamps: true   # Qwen3-ASRで有効。初回は ForcedAligner を追加でダウンロードする
```

ForcedAligner の読み込みや実行に失敗したときは、警告のログを出してタイムスタンプなしで保存されます。
詳細は [timestamp_feature.md](../feature/timestamp_feature.md) を参照してください。

## ⚙️ 設定・認証関連

### エラー: `設定ファイルが見つかりません`

**原因:** config/config.yaml が存在しない

**解決策:**
```bash
# 設定ファイル確認
ls -la config/config.yaml

# Gitで管理されている版に復元
git checkout config/config.yaml
```

復元できない場合は、次の最小構成で作成できます（各項目は [設定ガイド](configuration.md) を参照）。

```yaml
# config/config.yaml
gdrive:
  url: null
  upload_folder_id: null

whisper:
  model: Qwen/Qwen3-ASR-1.7B
  language: null
  device: cuda
  context_file: "config/context_hints.txt"
  include_timestamps: false
```

### 現象: `config/config.yaml` が YAML として読めない

このリポジトリのコードに `Invalid configuration format` という文言はありません。YAML の構文エラーは PyYAML が
例外（`yaml.YAMLError` の仲間）として出します。`./tc` はそのままトレースバックで止まり、`./transcribe.py` は
`設定ファイルエラー: <原因>` と表示して終了コード 1 で終わります。WebUI は読み込みの失敗を無視して起動します。

**原因:** YAML形式エラー

**解決策:**
```bash
# YAML構文チェック (uv 経由)
uv run python3 -c "import yaml; yaml.safe_load(open('config/config.yaml'))"

# インデント確認（スペース2個）
cat -A config/config.yaml

# 設定ファイル修復
# エラー行をエディタで修正
nano config/config.yaml
```

## 🚀 パフォーマンス関連

### 問題: 処理が遅い

**原因:** デバイス設定、モデル、または音声ファイルサイズ

**解決策:**
```bash
# GPU使用確認
./tc --device cuda "audio.wav"

# GPU監視（別ターミナルで実行）
uv run python3 scripts/gpu_monitor.py
# または
watch -n 1 nvidia-smi

# より軽いモデルを使う（transcribe.py のカスタム設定でも選べるWhisper系モデル）
./tc --model openai/whisper-medium "audio.wav"

# 音声ファイル圧縮
ffmpeg -i large_audio.wav -ar 16000 -ac 1 compressed_audio.wav
```

初回の実行ではモデルのダウンロード・ロードの時間が加わります。

### 問題: メモリ使用量が多い

**原因:** 大きなモデルまたは長い音声ファイル

**解決策:**
```bash
# メモリ・スワップ領域確認
free -h
swapon --show

# CPUで実行してGPUメモリを使わない
./tc --device cpu "audio.wav"

# 音声を分割して個別に処理する
ffmpeg -i long_audio.wav -t 1800 -c copy part1.wav
```

WebUI は複数の入力を同時には処理せず、キューで順番に処理します。

### 問題: ディスクの空きが減る

```bash
# output/ の中で何が大きいか確認する
du -sh output/* | sort -h
```

- `output/uploads/`: WebUI のアップロード。保存から 7 日を過ぎたものは、新しい入力を追加するたびに削除されますが、
  それまでは残ります（処理後にすぐには消えません）。
- `output/queue_downloads/`: WebUI の URL 入力の作業領域。処理後の音声は削除され、空のディレクトリや失敗時の
  部分ファイルが残ります。1 日を過ぎたものは、同じタイミングで削除されます。
- `output/*_transcription.txt` と `output/history.db`: 自動では削除されません。
- Google Drive からダウンロードした音声は、システムの一時ディレクトリに保存され、処理の終了時に削除されます。

## 📊 ログ・デバッグ関連

### 問題: ログが出力されない

**原因:** ログディレクトリの権限、または実行したディレクトリの違い

実行ログは標準出力と `logs/transcription.log`（実行したディレクトリ直下の `logs/`、10MBごとにローテーション、
5世代保持）に出力されます。ログレベルは INFO 固定で、設定では変えられません。pytest の実行中だけは、本番のログを汚さないよう
`logs/transcription_test.log` に出力されます。

**解決策:**
```bash
# ログディレクトリ権限確認
ls -la logs/
chmod 755 logs/

# ログファイルの末尾を確認
tail -n 50 logs/transcription.log
```

### 問題: デバッグ情報が欲しい

**解決策:**
```bash
# 実行ログを別ファイルにも保存
./tc "audio.wav" 2>&1 | tee debug.log

# ログファイル確認
tail -f logs/transcription.log

# システムログ確認
dmesg | tail
```

### 問題: エラーメッセージが不明確

**解決策:**
```bash
# Python トレースバック表示
./tc "audio.wav" 2>&1 | tee debug.log

# ステップバイステップ実行 (uv 経由)
uv run python3 -c "
from core.config import UnifiedConfig
UnifiedConfig.load()
print('Config OK')

from core.transcription_interface import UnifiedTranscriber  
print('Import OK')

import torch
print('CUDA available:', torch.cuda.is_available())
"
```

## 🔧 システム全体のリセット

### 完全リセット手順

**軽度な問題の場合:**
```bash
# 仮想環境リセット (uv 管理)
rm -rf .venv
uv sync

# 設定リセット
git checkout config/config.yaml
```

**重大な問題の場合:**

先に次のファイルを退避してください（リポジトリの外にコピーする）。

- `config/config.yaml`（Git 管理下のファイル。`git reset --hard` で、編集した内容が失われます）
- `credentials.json`、`token.pickle`、`config/context_hints.txt`、`output/history.db`（`.gitignore` で除外されている
  ファイルなので、次の `git clean -fd` では消えません。ただし `-x` を付けると消えるので、付けないでください。
  念のため退避しておくと安全です）

`git clean` は、実行前に `git clean -fdn`（削除せず、対象を表示するだけ）で、消えるものを確認してください。

```bash
# 完全なシステムリセット
git stash  # 未保存の変更を退避
git reset --hard HEAD
git clean -fd

# 仮想環境完全再作成 (uv が pyproject.toml/uv.lock から復元)
rm -rf .venv
uv sync

# システム再起動（GPU問題の場合）
sudo reboot
```

## 📞 サポートが必要な場合

### 情報収集

問題を報告する前に以下の情報を収集してください：

```bash
# システム情報
uname -a
python3 --version
uv pip list | grep -E "(torch|transformers|qwen)"

# GPU情報（該当する場合）
nvidia-smi
nvcc --version

# エラーログ
tail -50 logs/transcription.log

# 設定情報（gdrive.url などURL・フォルダIDは伏せて共有する）
cat config/config.yaml
```

### 報告先

プロジェクトの課題管理（Issue / チケット）に、上記の情報と、次の形式で報告してください。

### 効果的な報告方法

**良い報告例:**
```
タイトル: CUDA out of memory エラー（RTX 4080、15分音声）

環境:
- OS: Ubuntu 20.04
- GPU: RTX 4080 16GB
- Python: 3.12
- torch: 2.11.0+cu130

再現手順:
1. ./tc "15min_audio.wav" --language ja
2. GPU メモリ使用量が100%に到達
3. CUDA out of memory エラー

エラーログ:
```
torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB
```

期待される動作:
正常に文字起こしが完了すること

試行した解決策:
- --device cpu で動作確認済み
- 別のモデル（--model openai/whisper-large-v3）も試行済み
```

---

このトラブルシューティングガイドで解決しない問題は、上記の情報を添えて報告してください。
