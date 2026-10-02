# チュートリアル 🎥

音声文字起こしシステムの初心者向けステップバイステップガイドです。

## 📋 目次

- [事前準備](#事前準備)
- [基本的な使い方](#基本的な使い方)
- [YouTube・X動画の処理](#youtubex動画の処理)
- [Google Drive連携](#google-drive連携)
- [WebUIで使う](#webuiで使う)
- [設定のカスタマイズ](#設定のカスタマイズ)
- [トラブルシューティング](#トラブルシューティング)

## 🚀 事前準備

### ステップ1: システム要件確認

**必要な環境:**
```
✅ Python 3.12以上
✅ 8GB以上のRAM（推奨: 12GB）
✅ 10GB以上のストレージ空き容量
✅ NVIDIA GPU（推奨: RTX 4080以上）
```

**環境確認コマンド:**
```bash
# Python バージョン確認
python3 --version

# GPU確認（NVIDIA GPU使用時）
nvidia-smi

# メモリ確認
free -h
```

### ステップ2: リポジトリクローン

```bash
# GitHubからクローン
git clone <repository-url>
cd tc
```

### ステップ3: 仮想環境セットアップ

このプロジェクトは [uv](https://docs.astral.sh/uv/) で依存関係を管理しています。
pyproject.toml / uv.lock が情報源です。

```bash
# 依存関係インストール（.venv を自動作成）
# dev group(pytest 等)と Qwen3-ASR エンジンもデフォルトで含まれるため、素の uv sync で揃う
uv sync
```

### ステップ4: Nemotronを使う場合の準備（任意）

既定のモデル（Qwen3-ASR）と Whisper 系モデルは、ステップ3だけで使えます。
Nemotron（`nvidia/nemotron-3.5-asr-streaming-0.6b`）を使う場合だけ、専用の仮想環境 `venv-nemotron/` が必要です。

```bash
# Nemotron用の隔離環境を作る（既に venv-nemotron/ がある場合は何もしない）
./scripts/setup_nemotron_venv.sh
```

### ステップ5: 基本動作確認

```bash
# ヘルプ表示（動作確認）
./tc --help
```

**📸 期待される画面:**
```
usage: tc [-h] [--output-dir OUTPUT_DIR] [--no-upload] [--model MODEL]
          [--language LANGUAGE] [--device {cuda,cpu,auto}]
          [--folder-id FOLDER_ID] [--dry-run]
          [input]

音声文字起こしツール - YouTube URL・Google Drive URLまたはローカルファイルを文字起こし

positional arguments:
  input                 YouTube URL・Google Drive
                        URLまたはローカルファイルパス（省略時はconfig.yamlのURLを使用）

options:
  -h, --help            show this help message and exit
  --output-dir OUTPUT_DIR
                        出力ディレクトリ（デフォルト: output）
  --no-upload           Google Driveへのアップロードをスキップ
  --model MODEL         使用するモデル（config.yamlの設定を上書き）
  --language LANGUAGE   言語コード（config.yamlの設定を上書き）
  --device {cuda,cpu,auto}
                        使用するデバイス（config.yamlの設定を上書き）
  --folder-id FOLDER_ID
                        アップロード先Google DriveフォルダID（省略時は元ファイルと同じフォルダ）
  --dry-run             設定読み込み・入力解決までを行い、実際の文字起こしは行わずに終了する（起動確認用）
```

## 🎯 基本的な使い方

### シナリオ1: ローカル音声ファイルの文字起こし

**手順:**

1. **音声ファイルを準備**
```bash
# サンプル音声ファイルをプロジェクトディレクトリに配置
# 例: audio_sample.wav
ls -la *.wav
```

2. **基本的な文字起こし実行**
```bash
# 日本語音声の文字起こし（ローカルファイルは Google Drive にアップロードされない）
./tc audio_sample.wav --language ja
```

3. **実行中の画面表示**（表示内容の例）
```
設定ファイルを読み込みました
文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
文字起こし完了: output/20261002_101530_transcription.txt
```
実行ログは同じ内容が `logs/transcription.log` にも記録されます。

4. **結果の確認**
```bash
# 出力ファイルの確認
ls -la output/
cat output/*_transcription.txt
```

**📸 期待される出力例:**
```
こんにちは、今日は音声文字起こしのテストを行います。この機能を使うことで、音声ファイルを自動的にテキストに変換できます。
```

既定ではテキストのみが出力されます。各行頭に `[MM:SS]` を付けたい場合は、`config/config.yaml` の
`whisper.include_timestamps` を `true` にします（Qwen3-ASR のみ対応。[設定ガイド](configuration.md) を参照）。

### シナリオ2: 英語音声の処理

```bash
# 英語音声の文字起こし
./tc english_audio.wav --language en --device cuda
```

**モデルの選択:**
- 既定は `Qwen/Qwen3-ASR-1.7B`（`config.yaml` の `whisper.model`）。日本語・英語とも同じモデルで処理する
- `--model` で上書きできる: `./tc english_audio.wav --language en --model openai/whisper-large-v3`
- 日本語: `--model kotoba-tech/kotoba-whisper-v2.2` なども指定できる（モデル名で Qwen3-ASR / Whisper /
  Nemotron のエンジンが自動で選ばれる。詳細は [多言語対応ガイド](language_support_guide.md)）

## 📺 YouTube・X動画の処理

### シナリオ3: 動画から音声抽出・文字起こし

**手順:**

1. **動画URLを準備**
```bash
# YouTube の例: https://www.youtube.com/watch?v=example123
# X(旧Twitter)の例: https://x.com/<ユーザー名>/status/<投稿ID>
```

2. **基本的な処理**
```bash
# YouTube動画の文字起こし
./tc "https://www.youtube.com/watch?v=example123" --language ja

# X(旧Twitter)の動画投稿
./tc "https://x.com/<ユーザー名>/status/<投稿ID>" --language ja
```

3. **実行中の画面表示**（表示内容の例）
```
YouTube URLを検出
...（yt-dlp のダウンロード進捗）
文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
文字起こし完了: output/20261002_101530_transcription.txt
```
X の URL では「X(Twitter)動画URLを検出」と表示されます。

4. **処理完了確認**
```bash
# 文字起こし結果
ls -la output/
```
ダウンロードした音声（`<タイトル>_<動画ID>.wav`）は `--output-dir`（既定は `output/`）に一時保存され、
処理が終わると削除されます。

YouTube 動画は、処理後に Google Drive へ自動アップロードされます（`--no-upload` で止められます）。
X の動画はアップロードされず、ローカルにのみ保存されます。

## ☁️ Google Drive連携

### シナリオ4: Google Drive上の音声ファイル処理

**事前準備:**

1. **Google Drive API認証設定**
```bash
# 実行するディレクトリ直下に credentials.json があることを確認
ls -la credentials.json
```
初回は認証URLが表示されます。ブラウザで認証したあと、リダイレクト先の完全なURLを貼り付けると、
`token.pickle` が作成されます（以降は自動で再利用）。

2. **設定ファイルでDrive URLを指定**
```yaml
# config/config.yaml
gdrive:
  url: "https://drive.google.com/file/d/your_file_id/view"
  upload_folder_id: null   # 結果の保存先フォルダID（null なら元ファイルと同じフォルダ）
```

**手順:**

1. **設定ファイル使用の基本実行**
```bash
# config.yamlで設定されたURLを使用
./tc
```

2. **コマンドラインでDrive URL指定**
```bash
# 直接Drive URLを指定
./tc "https://drive.google.com/file/d/1ABC123XYZ/view" --language ja
```

3. **実行中の画面表示**（表示内容の例）
```
Google Drive URLを検出、ダウンロードを開始
文字起こし開始: モデル=Qwen/Qwen3-ASR-1.7B, 言語=ja, デバイス=cuda
文字起こし完了: output/20261002_101530_transcription.txt
アップロード完了: https://drive.google.com/file/d/<結果ファイルID>/view
```

4. **結果の確認**
```bash
# ローカル結果確認
cat output/*_transcription.txt
```
アップロード先は `--folder-id` > `gdrive.upload_folder_id` > 元ファイルと同じフォルダ、の優先順位で決まります。

## 🖥️ WebUIで使う

コマンドラインの代わりに、ブラウザから操作できる WebUI（`webui.py`、Streamlit 製）もあります。

```bash
uv run streamlit run webui.py --server.headless true --server.port 8501
```

起動後、ブラウザで `http://localhost:8501` を開きます。

- 「文字起こし」タブ: YouTube / X / Google Drive の URL を入力するか、ファイルをアップロードして、
  モデル・デバイス・言語を選び「キューに追加」を押す。複数の入力は順番に処理される
- 「履歴」タブ: 過去の文字起こし結果の検索・確認ができる

詳細は [WebUI内部サーバー構成](../system-docs/webui_architecture.md) を参照してください。

## ⚙️ 設定のカスタマイズ

### シナリオ5: 設定ファイルのカスタマイズ

**設定ファイルの編集:**

```bash
# 設定ファイルを開く
nano config/config.yaml
```

**主要設定項目:**

```yaml
# config/config.yaml
whisper:
  model: Qwen/Qwen3-ASR-1.7B     # モデル名（名前でエンジンが自動選択される）
  language: null                 # null=自動判定。ja / en を指定すると強制
  device: cuda                   # cuda / cpu / auto
  context_file: "config/context_hints.txt"  # 固有名詞のヒント（Qwen3-ASR専用）
  include_timestamps: false      # true で各行頭に [MM:SS] を付与（Qwen3-ASR専用）

gdrive:
  url: "your_default_url"        # 入力を省略したときに処理するURL
  upload_folder_id: null         # Google Drive入力の結果のアップロード先フォルダID
```

各項目の詳細は [設定ガイド](configuration.md) を参照してください。

**設定確認:**
```bash
# 設定値の確認 (uv 経由)
uv run python3 -c "from core.config import UnifiedConfig; UnifiedConfig.load(); print(UnifiedConfig.get('whisper'))"
```

### カスタム設定での実行例

```bash
# CPUを強制使用
./tc --device cpu "audio.wav"

# 実行ログをファイルにも保存
./tc "audio.wav" 2>&1 | tee debug.log

# GPU監視(別ターミナルで scripts/gpu_monitor.py を並行実行)
uv run python3 scripts/gpu_monitor.py &
./tc "audio.wav"
```

## 🔧 よく使う操作パターン

### パターン1: バッチ処理

```bash
# 複数ファイルの一括処理
for file in audio_files/*.wav; do
    echo "処理中: $file"
    ./tc "$file" --language ja --no-upload
done
```

### パターン2: モデルを切り替える

```bash
# Whisper系モデルで処理
./tc "audio.wav" --model openai/whisper-large-v3 --language ja
```

### パターン3: GPUが使えない環境で処理する

```bash
# CPUで処理（GPUより時間がかかる）
./tc --device cpu --language ja "audio.wav"
```

## 📊 結果の活用

### 出力ファイル形式

**基本テキスト形式（既定）:** 文字起こし結果のテキストのみ。

**タイムスタンプ付き形式（`whisper.include_timestamps: true`、Qwen3-ASRのみ）:**
```
[MM:SS] 文字起こしテキスト
[MM:SS] 続きのテキスト
```

### 後処理の例

```bash
# 最新の出力ファイルを変数に入れる
latest=$(ls -t output/*_transcription.txt | head -1)

# 文字数カウント
wc -c "$latest"

# 特定キーワード検索
grep -i "重要" "$latest"
```

## 🚨 トラブルシューティング

### よくある問題と解決法

**問題1: GPU out of memory**
```bash
# エラーメッセージ例
CUDA out of memory. Tried to allocate 2.00 GiB

# 解決策: CPUに切り替え
./tc --device cpu "audio.wav"
```

**問題2: Nemotron隔離venvが未構築**
```bash
# エラーメッセージ例
Nemotron隔離venvが未構築です。scripts/setup_nemotron_venv.sh を実行してから再度お試しください。

# 解決策: 隔離環境を作る
./scripts/setup_nemotron_venv.sh
```

**問題3: 音声ファイルが認識されない**
```bash
# エラーメッセージ例
入力を認識できません: audio.wav

# 解決策: パスと拡張子を確認（存在しないパスは「認識できません」になる）
ls -la audio.wav
file audio.wav
# 必要に応じて変換
ffmpeg -i audio.mp3 audio.wav
```

**問題4: YouTube URLが処理できない**
```bash
# エラーメッセージ例
Failed to get video info
Audio extraction failed: ...

# 解決策: URLの確認
echo "https://www.youtube.com/watch?v=VIDEO_ID"
# プライベート動画でないことを確認
```

### デバッグ方法

```bash
# 実行ログをファイルに保存
./tc "audio.wav" 2>&1 | tee debug.log

# ログファイル確認
tail -f logs/transcription.log

# システム状態確認
nvidia-smi  # GPU使用状況
top         # CPU/メモリ使用状況
```

## 🎯 実践的な使用例

### 例1: 会議録音の処理

```bash
# 1時間の会議録音。ローカルファイルはアップロードされず output/ に保存される
./tc meeting_2026-10-02.wav --language ja
```

### 例2: 講演動画の処理

```bash
# YouTubeの講演動画(GPU使用状況を見たい場合は別ターミナルで
# uv run python3 scripts/gpu_monitor.py を並行実行する)
./tc "https://youtube.com/watch?v=lecture123" \
    --language ja \
    --device cuda
```

### 例3: 英語プレゼンテーションの処理

```bash
# 英語のプレゼンテーション音声
./tc presentation_en.wav \
    --language en \
    --device cuda
```

---

## 🎉 チュートリアル完了

おめでとうございます！これで音声文字起こしシステムの基本的な使い方をマスターしました。

### 次のステップ

- **[API仕様書](../developer-guides/API.md)** - プログラマー向け詳細情報
- **[開発者ガイド](../../DEVELOPMENT.md)** - カスタマイズ方法
- **[トラブルシューティング](TROUBLESHOOTING.md)** - 詳細な問題解決

高品質な音声文字起こしをお楽しみください！ 🎙️✨
