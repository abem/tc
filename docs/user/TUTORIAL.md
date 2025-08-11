# チュートリアル 🎥

音声文字起こしシステム（tc）の初心者向けステップバイステップガイドです。

## 🚀 新CLI体験（推奨）

**最もシンプルな方法**: `./tc` コマンドで一発実行  
**環境**: uvパッケージマネージャー推奨（pip比較10倍高速）  
**特徴**: YouTube URL → 転写 → Google Drive自動アップロード

## 📋 目次

- [事前準備](#事前準備)
- [基本的な使い方](#基本的な使い方)
- [話者分離機能](#話者分離機能)
- [YouTube動画の処理](#youtube動画の処理)
- [Google Drive連携](#google-drive連携)
- [設定のカスタマイズ](#設定のカスタマイズ)
- [トラブルシューティング](#トラブルシューティング)

## 🚀 事前準備

### ステップ1: システム要件確認

**必要な環境:**
```
✅ Python 3.11以上
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
git clone https://github.com/abem/tc.git
cd tc
```

### ステップ3: 仮想環境セットアップ

**推奨方法（uv環境）:**
```bash
# uv仮想環境作成（超高速）
uv venv

# 仮想環境有効化
source .venv/bin/activate

# 依存関係インストール（30秒で完了）
uv sync
```

**代替方法（従来pip環境）:**
```bash
# 仮想環境作成
python3 -m venv venv-clean

# 仮想環境有効化
source venv-clean/bin/activate

# 依存関係インストール
pip install -r requirements.txt
```

**📸 期待される画面（uv環境）:**
```
Resolved 170 packages in 2.1s
Installed 170 packages in 28.3s
✅ uv環境セットアップ完了（30秒で170パッケージ）
```

### ステップ4: HuggingFaceトークン設定

話者分離機能を使用する場合は必須です。

1. **HuggingFaceアカウント作成**
   - [HuggingFace](https://huggingface.co/)にアクセス
   - 「Sign Up」をクリック
   - メールアドレスとパスワードを入力

2. **アクセストークン生成**
   - ログイン後、右上のプロフィール → Settings
   - 「Access Tokens」をクリック
   - 「New token」で新しいトークンを作成

3. **pyannoteモデルへのアクセス許可**
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)にアクセス
   - 「Agree and access repository」をクリック

4. **環境変数設定**
```bash
# トークンを環境変数に設定
export HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 確認
echo $HUGGINGFACE_TOKEN
```

### ステップ5: 基本動作確認

```bash
# ヘルプ表示（動作確認）
./tc --help
```

**📸 期待される画面:**
```
使用方法: ./tc [オプション] [音声ファイル/URL]

オプション:
  --language, -l           言語設定 (ja: 日本語, en: 英語)
  --enable-diarization     話者分離機能を有効化
  ...
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
# 日本語音声の文字起こし
./exec_local.sh audio_sample.wav --language ja
```

3. **実行中の画面表示**
```
[INFO] 処理を開始します: audio_sample.wav
[INFO] 選択された言語: ja
[INFO] 話者分離機能: false
音声文字起こし: 100%|████████████| 10/10 [00:45<00:00, 4.52s/it]
[INFO] 転写完了: 1,247文字
```

4. **結果の確認**
```bash
# 出力ファイルの確認
ls -la output/
cat output/20250729_*_transcription.txt
```

**📸 期待される出力例:**
```
[00:00] こんにちは、今日は音声文字起こしのテストを行います。
[00:30] この機能を使うことで、音声ファイルを自動的にテキストに変換できます。
[01:00] とても便利な機能ですね。
```

### シナリオ2: 英語音声の処理

```bash
# 英語音声の文字起こし
./exec_local.sh english_audio.wav --language en --device cuda
```

**自動モデル選択:**
- 日本語: `kotoba-tech/kotoba-whisper-v2.2`
- 英語: `openai/whisper-large-v3`

## 🎤 話者分離機能

### シナリオ3: 会議音声の話者分離

**手順:**

1. **複数話者の音声ファイルを準備**
```bash
# 会議録音などの複数話者音声
# 例: meeting.wav
```

2. **話者分離付き文字起こし**
```bash
# 話者分離機能を有効化
./exec_local.sh meeting.wav --language ja --enable-diarization
```

3. **最大話者数を指定**
```bash
# 最大3人の話者を想定
./exec_local.sh meeting.wav --language ja --enable-diarization --max-speakers 3
```

4. **実行中の画面表示**
```
[INFO] 話者分離機能: true
[INFO] 最大話者数: 3
話者分離処理: 100%|████████████| 1/1 [01:30<00:00, 90.45s/it]
音声文字起こし: 100%|████████████| 15/15 [02:15<00:00, 9.03s/it]
話者統合処理: 100%|████████████| 15/15 [00:05<00:00, 2.85it/s]
```

5. **話者別結果の確認**
```bash
cat output/20250729_*_transcription.txt
```

**📸 期待される出力例:**
```
[00:00] SPEAKER_00: おはようございます。今日の会議を始めさせていただきます。
[00:15] SPEAKER_01: よろしくお願いします。まず議題について確認します。
[00:30] SPEAKER_02: 前回の続きから話していきましょう。
[00:45] SPEAKER_00: そうですね。それでは資料を見ながら進めていきます。
```

## 📺 YouTube動画の処理

### シナリオ4: YouTube動画から音声抽出・文字起こし

**手順:**

1. **YouTube URLを準備**
```bash
# 例: https://www.youtube.com/watch?v=example123
```

2. **基本的なYouTube処理**
```bash
# YouTube動画の文字起こし
./tc "https://www.youtube.com/watch?v=example123" --language ja
```

3. **YouTube + 話者分離**
```bash
# 複数話者のYouTube動画処理
./tc "https://www.youtube.com/watch?v=example123" \
    --language ja \
    --enable-diarization \
    --max-speakers 2
```

4. **実行中の画面表示**
```
[INFO] YouTube動画をダウンロード中...
[INFO] 音声抽出中...
[INFO] 文字起こし開始...
YouTube audio extraction: 100%|████████| 1/1 [00:30<00:00, 30.2s/it]
音声文字起こし: 100%|████████████| 25/25 [03:45<00:00, 9.0s/it]
```

5. **処理完了確認**
```bash
# ダウンロードされた音声ファイル
ls -la downloads/
# 文字起こし結果
ls -la output/
```

## ☁️ Google Drive連携

### シナリオ5: Google Drive上の音声ファイル処理

**事前準備:**

1. **Google Drive API認証設定**
```bash
# credentials.jsonが存在することを確認
ls -la credentials.json
```

2. **設定ファイルでDrive URLを指定**
```yaml
# config/config.yaml
gdrive:
  url: "https://drive.google.com/file/d/your_file_id/view"
  output_folder_id: "your_folder_id"
```

**手順:**

1. **設定ファイル使用の基本実行**
```bash
# config.yamlで設定されたGoogle Drive URLを使用
./tc
```

2. **コマンドラインでDrive URL指定**
```bash
# 直接Drive URLを指定
./tc "https://drive.google.com/file/d/1ABC123XYZ/view" --language ja
```

3. **実行中の画面表示**
```
[INFO] Google Driveからダウンロード中...
[INFO] ファイルサイズ: 15.2MB
[INFO] ダウンロード完了: /tmp/audio_file.wav
[INFO] 文字起こし開始...
```

4. **結果のDriveアップロード確認**
```bash
# ローカル結果確認
cat output/20250729_*_transcription.txt

# Google Driveへの自動アップロード完了メッセージ
[INFO] 結果をGoogle Driveにアップロード完了
[INFO] URL: https://drive.google.com/file/d/result_file_id/view
```

## ⚙️ 設定のカスタマイズ

### シナリオ6: 設定ファイルのカスタマイズ

**設定ファイルの編集:**

```bash
# 設定ファイルを開く
nano config/config.yaml
```

**主要設定項目:**

```yaml
# config/config.yaml
whisper:
  model: "large-v3"              # モデル名
  language: "ja"                 # デフォルト言語
  device: "cuda"                 # デバイス設定
  chunk_length: 30               # チャンク長（秒）
  output_format: "txt"           # 出力形式

speaker_diarization:
  enable: false                  # 話者分離のデフォルト設定
  model: "pyannote/speaker-diarization-3.1"
  max_speakers: 4                # デフォルト最大話者数

gdrive:
  url: "your_default_url"        # デフォルトGoogle Drive URL
  output_folder_id: "folder_id"  # 結果アップロード先

logging:
  level: "INFO"                  # ログレベル
  dir: "logs"                    # ログディレクトリ
```

**設定確認:**
```bash
# 設定値の確認
python3 -c "from core.config import UnifiedConfig; UnifiedConfig.load(); print(UnifiedConfig.get('whisper'))"
```

### カスタム設定での実行例

```bash
# CPUを強制使用
./tc --device cpu "audio.wav"

# 詳細ログ表示
./tc --verbose "audio.wav"

# GPU監視付き実行
./tc --gpu-monitor "audio.wav"
```

## 🔧 よく使う操作パターン

### パターン1: バッチ処理

```bash
# 複数ファイルの一括処理
for file in audio_files/*.wav; do
    echo "処理中: $file"
    ./exec_local.sh "$file" --language ja
done
```

### パターン2: 品質重視設定

```bash
# 高品質設定（処理時間長め）
./tc --device cuda --language ja "high_quality_audio.wav"
```

### パターン3: 高速処理設定

```bash
# 高速設定（品質やや劣る）
./tc --device cpu --language ja "quick_process_audio.wav"
```

## 📊 結果の活用

### 出力ファイル形式

**基本テキスト形式:**
```
[MM:SS] 文字起こしテキスト
[MM:SS] 続きのテキスト
```

**話者分離付き形式:**
```
[MM:SS] SPEAKER_00: 最初の話者の発言
[MM:SS] SPEAKER_01: 2番目の話者の発言
```

### 後処理の例

```bash
# 文字数カウント
wc -c output/latest_transcription.txt

# 話者別発言量分析
grep "SPEAKER_00" output/latest_transcription.txt | wc -l
grep "SPEAKER_01" output/latest_transcription.txt | wc -l

# 特定キーワード検索
grep -i "重要" output/latest_transcription.txt
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

**問題2: HuggingFace認証エラー**
```bash
# エラーメッセージ例
Cannot access model pyannote/speaker-diarization-3.1

# 解決策: トークン再設定
export HUGGINGFACE_TOKEN=hf_your_new_token
./tc --enable-diarization "audio.wav"
```

**問題3: 音声ファイルが認識されない**
```bash
# エラーメッセージ例
File not found or unsupported format

# 解決策: ファイル形式確認
file audio.wav
# 必要に応じて変換
ffmpeg -i audio.mp3 audio.wav
```

**問題4: YouTube URLが処理できない**
```bash
# エラーメッセージ例
Unable to extract audio from YouTube URL

# 解決策: URLの確認
echo "https://www.youtube.com/watch?v=VIDEO_ID"
# プライベート動画でないことを確認
```

### デバッグ方法

```bash
# 詳細ログで実行
./tc --verbose "audio.wav"

# ログファイル確認
tail -f logs/transcribe_*.log

# システム状態確認
nvidia-smi  # GPU使用状況
top         # CPU/メモリ使用状況
```

## 🎯 実践的な使用例

### 例1: 会議録音の処理

```bash
# 1時間の会議録音（4人の参加者）
./exec_local.sh meeting_2025-07-29.wav \
    --language ja \
    --enable-diarization \
    --max-speakers 4 \
    --verbose
```

### 例2: 講演動画の処理

```bash
# YouTubeの講演動画
./tc "https://youtube.com/watch?v=lecture123" \
    --language ja \
    --device cuda \
    --gpu-monitor
```

### 例3: 英語プレゼンテーションの処理

```bash
# 英語のプレゼンテーション音声
./exec_local.sh presentation_en.wav \
    --language en \
    --device cuda
```

---

## 🎉 チュートリアル完了

おめでとうございます！これで音声文字起こしシステムの基本的な使い方をマスターしました。

### 次のステップ

1. **[API仕様書](API.md)** - プログラマー向け詳細情報
2. **[開発者ガイド](../DEVELOPMENT.md)** - カスタマイズ方法
3. **[トラブルシューティング](TROUBLESHOOTING.md)** - 詳細な問題解決

### サポート

- 🐛 **バグ報告**: [GitHub Issues](https://github.com/yourusername/transcribe_audio/issues)
- 💬 **質問・相談**: [GitHub Discussions](https://github.com/yourusername/transcribe_audio/discussions)
- 📖 **ドキュメント**: 常に最新版をGitHubで確認

高品質な音声文字起こしをお楽しみください！ 🎙️✨