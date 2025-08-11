# トラブルシューティングガイド 🛠️

音声文字起こしシステム（tc）で発生する可能性のある問題と解決方法を網羅的にまとめました。

## 🚀 tc CLI 固有のトラブルシューティング

**推奨実行方法**: `./tc` コマンド  
**環境**: uvパッケージマネージャー推奨

## 📋 目次

- [環境・インストール関連](#環境インストール関連)
- [GPU・CUDA関連](#gpucuda関連)
- [音声処理関連](#音声処理関連)
- [話者分離関連](#話者分離関連)
- [YouTube・Google Drive関連](#youtubegoogle-drive関連)
- [文字起こし品質関連](#文字起こし品質関連)
- [設定・認証関連](#設定認証関連)
- [パフォーマンス関連](#パフォーマンス関連)
- [ログ・デバッグ関連](#ログデバッグ関連)

## 🔧 環境・インストール関連

### エラー: `ModuleNotFoundError: No module named 'torch'`

**原因:** PyTorchがインストールされていないまたはuv環境が正しく設定されていない

**解決策（uv環境推奨）:**
```bash
# uv環境の再構築
uv venv --force
source .venv/bin/activate
uv sync

# 確認
python3 -c "import torch; print('PyTorch version:', torch.__version__)"
```

**代替解決策（pip環境）:**
```bash
# 仮想環境が有効化されているか確認
source venv-clean/bin/activate

# PyTorchのインストール
pip install torch torchvision torchaudio
```

**確認方法:**
```bash
python3 -c "import torch; print('PyTorch version:', torch.__version__)"
python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

### エラー: `ModuleNotFoundError: No module named 'transformers'`

**原因:** Transformersライブラリがインストールされていない

**解決策:**
```bash
pip install transformers>=4.35.0

# 特定バージョンが必要な場合
pip install transformers==4.35.0
```

### エラー: `Python version 3.x.x is not supported`

**原因:** Python のバージョンが古い

**解決策:**
```bash
# Pythonバージョン確認
python3 --version

# Python 3.11以上が必要
# Ubuntu/Debian の場合
sudo apt update
sudo apt install python3.11 python3.11-venv

# 新しい仮想環境作成
python3.11 -m venv venv-clean
source venv-clean/bin/activate
```

### エラー: `./tc: Permission denied`

**原因:** tcコマンドに実行権限がない

**解決策:**
```bash
# tcコマンドに実行権限を付与
chmod +x tc
chmod +x transcribe.py

# 確認
ls -la tc

# テスト実行
./tc --help
```

### エラー: `source .venv/bin/activate` または `source venv-clean/bin/activate` が失敗

**原因:** 仮想環境が削除または作成されていない

**解決策（uv環境推奨）:**
```bash
# uv仮想環境の再作成
uv venv --force
source .venv/bin/activate
uv sync

# HuggingFaceトークンの設定
export HUGGINGFACE_TOKEN=hf_your_token_here
```

**代替解決策（pip環境）:**
```bash
# 仮想環境の再作成
python3 -m venv venv-clean
source venv-clean/bin/activate

# 依存関係の再インストール
pip install -r requirements.txt
```

## ⚡ GPU・CUDA関連

### エラー: `CUDA out of memory`

**原因:** GPU メモリ不足

**解決策1: 自動CPUフォールバック（tc CLIは自動対応）**
```bash
# tc CLIは自動的にCPUに切り替わります
./tc "audio.wav"

# 手動でCPU指定したい場合
export CUDA_VISIBLE_DEVICES=""
./tc "audio.wav"
```

**解決策2: バッチサイズを減らす**
```yaml
# config/config.yaml
whisper:
  chunk_length: 15  # デフォルト30から減らす
  batch_size: 1     # バッチサイズを最小に
```

**解決策3: GPU メモリ確認・クリア**
```bash
# GPU使用状況確認
nvidia-smi

# 他のGPUプロセスを終了
sudo fuser -v /dev/nvidia*
sudo kill -9 <process_id>

# Pythonプロセス再起動
```

**解決策4: 動的メモリ管理**
```python
# config設定で動的メモリプール有効化
enable_dynamic_memory_pool: true
memory_efficiency: true
```

### エラー: `CUDA device not found`

**原因:** CUDA ドライバーまたはPyTorchのCUDA版がインストールされていない

**解決策:**
```bash
# CUDA確認
nvidia-smi
nvcc --version

# PyTorchのCUDAサポート確認
python3 -c "import torch; print('CUDA available:', torch.cuda.is_available())"

# CUDA版PyTorchの再インストール
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### エラー: `RuntimeError: No CUDA GPUs are available`

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

### エラー: `torch.cuda.OutOfMemoryError` (継続的に発生)

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

### エラー: `File not found or unsupported format`

**原因:** 音声ファイルが存在しない、または非対応形式

**解決策:**
```bash
# ファイル存在確認
ls -la audio.wav

# ファイル形式確認
file audio.wav

# 対応形式への変換
ffmpeg -i audio.mp3 audio.wav
ffmpeg -i audio.m4a audio.wav
ffmpeg -i audio.ogg audio.wav
```

**対応形式:**
- ✅ WAV, MP3, MP4, M4A, FLAC, OGG
- ❌ WMA, RA, AMR（要変換）

### エラー: `Audio file is too long`

**原因:** 音声ファイルが長すぎる

**解決策:**
```bash
# ファイル長確認
ffprobe -i audio.wav -show_format -v quiet | grep duration

# 分割処理（30分単位）
ffmpeg -i long_audio.wav -t 1800 -c copy part1.wav
ffmpeg -i long_audio.wav -ss 1800 -t 1800 -c copy part2.wav

# 各部分を個別処理
./exec_local.sh part1.wav --language ja
./exec_local.sh part2.wav --language ja
```

### エラー: `Unable to load audio file`

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

### エラー: `Sample rate not supported`

**原因:** 非対応のサンプリングレート

**解決策:**
```bash
# サンプリングレート確認
ffprobe -v quiet -select_streams a:0 -show_entries stream=sample_rate audio.wav

# 16kHzに変換（推奨）
ffmpeg -i audio.wav -ar 16000 audio_16khz.wav

# 変換後処理
./exec_local.sh audio_16khz.wav --language ja
```

## 🎤 話者分離関連

### エラー: `Cannot access model pyannote/speaker-diarization-3.1`

**原因:** HuggingFace トークンまたはモデルアクセス許可の問題

**解決策:**
```bash
# トークン確認
echo $HUGGINGFACE_TOKEN

# トークン再設定
export HUGGINGFACE_TOKEN=hf_your_new_token

# モデルアクセス許可確認
# https://huggingface.co/pyannote/speaker-diarization-3.1 で「Agree and access」

# pyannote再インストール
pip uninstall pyannote.audio
pip install pyannote.audio
```

### エラー: `ModuleNotFoundError: No module named 'pyannote'`

**原因:** pyannote.audioがインストールされていない

**解決策:**
```bash
# pyannote.audio インストール
pip install pyannote.audio

# 依存関係も含めてインストール
pip install pyannote.audio[audio]

# トークン設定
export HUGGINGFACE_TOKEN=hf_your_token
```

### エラー: `Speaker diarization failed`

**原因:** 音声品質が低い、またはパラメータが不適切

**解決策:**
```bash
# 音声品質向上
ffmpeg -i noisy_audio.wav -af "highpass=f=200,lowpass=f=8000" clean_audio.wav

# 話者数パラメータ調整
./tc --enable-diarization --max-speakers 2 "audio.wav"  # 少なめに設定

# 話者分離無しで試行
./tc "audio.wav"  # 基本転写のみ
```

### エラー: `Too many speakers detected`

**原因:** 雑音や音楽が話者として誤認識されている

**解決策:**
```bash
# 話者数制限を厳しく
./tc --enable-diarization --max-speakers 2 "audio.wav"

# 音声フィルタリング
ffmpeg -i audio.wav -af "highpass=f=300,lowpass=f=3400" voice_only.wav

# 無音区間除去
ffmpeg -i audio.wav -af silenceremove=start_periods=1:start_silence=0.1:start_threshold=-30dB audio_trimmed.wav
```

## 📺 YouTube・Google Drive関連

### エラー: `Unable to extract audio from YouTube URL`

**原因:** YouTube URL の形式、プライベート動画、または地域制限

**解決策:**
```bash
# URL形式確認
echo "https://www.youtube.com/watch?v=VIDEO_ID"  # 正しい形式

# URLテスト
curl -I "https://www.youtube.com/watch?v=VIDEO_ID"

# 手動ダウンロード（デバッグ用）
youtube-dl --extract-audio --audio-format wav "YouTube_URL"

# yt-dlp を使用（推奨）
pip install yt-dlp
yt-dlp --extract-audio --audio-format wav "YouTube_URL"
```

### エラー: `Google Drive authentication failed`

**原因:** 認証ファイルまたは権限の問題

**解決策:**
```bash
# credentials.json確認
ls -la credentials.json

# 認証ファイル権限確認
chmod 600 credentials.json

# 環境変数設定
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/credentials.json"

# Google Drive API有効化確認
# https://console.cloud.google.com/apis/library/drive.googleapis.com
```

### エラー: `Google Drive quota exceeded`

**原因:** API使用量制限に達している

**解決策:**
```bash
# 少し待ってから再実行
sleep 300  # 5分待機
./tc "drive_url"

# 別のGoogle アカウント使用
# 新しいcredentials.jsonを取得

# ローカルファイルで先に処理
# Drive URLから手動ダウンロード → ローカル処理
```

### エラー: `YouTube video is private or unavailable`

**原因:** プライベート動画または削除された動画

**解決策:**
```bash
# 動画の公開状態確認
# ブラウザでURLにアクセスして確認

# 公開動画のURLで再試行
./tc "https://www.youtube.com/watch?v=public_video_id"

# 別の動画でテスト
./tc "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --language en  # テスト用
```

## 📝 文字起こし品質関連

### 問題: 文字起こし結果が短すぎる

**原因:** モデルパラメータまたは音声品質の問題

**解決策:**
```bash
# 詳細ログで確認
./tc --verbose "audio.wav"

# 異なるモデルでテスト
./tc --language ja "audio.wav"  # 日本語特化モデル
./tc --language en "audio.wav"  # 英語モデル

# チャンクサイズ調整
# config/config.yaml で chunk_length: 15 に変更
```

**設定例:**
```yaml
# config/config.yaml
whisper:
  chunk_length: 15        # 短いチャンクでより詳細に
  max_new_tokens: 400     # トークン数制限
  temperature: 0.0        # 決定的な出力
```

### 問題: 句読点がない

**原因:** モデルまたは言語設定の問題

**解決策:**
```bash
# 日本語特化モデル使用
./tc --language ja "audio.wav"

# forced_decoder_ids確認（日本語の場合）
# システムが自動的に句読点モードを選択
```

### 問題: 専門用語が正しく認識されない

**原因:** 音声が不明瞭、または専門用語に対応していない

**解決策:**
```bash
# 音声品質向上
ffmpeg -i audio.wav -af "loudnorm,highpass=f=200" enhanced_audio.wav

# より大きなモデル使用
# config.yamlで model: "large-v3" に変更

# 前後の文脈から修正（手動）
```

### 問題: タイムスタンプがずれている

**原因:** 音声ファイルの前処理または設定の問題

**解決策:**
```bash
# 音声ファイル確認
ffprobe -show_format -show_streams audio.wav

# 無音除去なしで処理
ffmpeg -i audio.wav -c copy no_processing.wav
./exec_local.sh no_processing.wav

# チャンクサイズ調整
# config.yamlで chunk_length: 30 に設定
```

## ⚙️ 設定・認証関連

### エラー: `Configuration file not found`

**原因:** config.yaml が存在しない

**解決策:**
```bash
# 設定ファイル確認
ls -la config/config.yaml

# サンプル設定から復元
cp config/config.yaml.example config/config.yaml

# デフォルト設定生成
cat > config/config.yaml << 'EOF'
whisper:
  model: "large-v3"
  language: "ja"
  device: "auto"
  chunk_length: 30

speaker_diarization:
  enable: false
  model: "pyannote/speaker-diarization-3.1"
  max_speakers: 4

logging:
  level: "INFO"
  dir: "logs"
EOF
```

### エラー: `Invalid configuration format`

**原因:** YAML形式エラー

**解決策:**
```bash
# YAML構文チェック
python3 -c "import yaml; yaml.safe_load(open('config/config.yaml'))"

# インデント確認（スペース2個）
cat -A config/config.yaml

# 設定ファイル修復
# エラー行をエディタで修正
nano config/config.yaml
```

### エラー: `Environment variable not set`

**原因:** 必要な環境変数が設定されていない

**解決策:**
```bash
# 環境変数確認
env | grep HUGGINGFACE
env | grep GOOGLE

# 環境変数設定
export HUGGINGFACE_TOKEN=hf_your_token
export GOOGLE_APPLICATION_CREDENTIALS=credentials.json

# .envファイル作成（自動読み込み）
cat > .env << 'EOF'
HUGGINGFACE_TOKEN=hf_your_token_here
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
EOF
```

## 🚀 パフォーマンス関連

### 問題: 処理が遅い

**原因:** デバイス設定、モデル、または音声ファイルサイズ

**解決策:**
```bash
# GPU使用確認
./tc --device cuda "audio.wav"

# GPU監視
./tc --gpu-monitor "audio.wav"

# より小さなモデル使用
# config.yamlで model: "base" または "small"

# 音声ファイル圧縮
ffmpeg -i large_audio.wav -ar 16000 -ac 1 compressed_audio.wav
```

### 問題: メモリ使用量が多い

**原因:** 大きなモデルまたは長い音声ファイル

**解決策:**
```bash
# メモリ効率化設定
# config.yamlに追加:
memory_efficiency: true
max_cache_size: 2

# チャンクサイズ削減
chunk_length: 15

# スワップ領域確認
free -h
swapon --show
```

### 問題: GPU使用率が低い

**原因:** バッチサイズが小さい、またはI/Oボトルネック

**解決策:**
```bash
# バッチサイズ調整
# config.yamlで:
optimal_batch_size: 8  # GPU能力に応じて調整

# SSD使用（可能な場合）
# 音声ファイルをSSDに配置

# GPU監視
watch -n 1 nvidia-smi
```

## 📊 ログ・デバッグ関連

### 問題: ログが出力されない

**原因:** ログ設定またはディレクトリの問題

**解決策:**
```bash
# ログディレクトリ作成
mkdir -p logs

# ログディレクトリ権限確認
ls -la logs/
chmod 755 logs/

# 詳細ログで実行
./tc --verbose "audio.wav"

# ログレベル設定確認
# config.yamlで level: "DEBUG"
```

### 問題: デバッグ情報が欲しい

**解決策:**
```bash
# 最大詳細ログ
./tc --verbose --gpu-monitor "audio.wav"

# Python レベルデバッグ
PYTHONPATH=$(pwd) python3 -v main_cli.py "audio.wav"

# ログファイル確認
tail -f logs/transcribe_*.log

# システムログ確認
dmesg | tail
journalctl -u service_name -f
```

### 問題: エラーメッセージが不明確

**解決策:**
```bash
# Python トレースバック表示
PYTHONPATH=$(pwd) python3 main_cli.py "audio.wav" 2>&1 | tee debug.log

# ステップバイステップ実行
python3 -c "
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
# 仮想環境リセット
deactivate
rm -rf venv-clean/
python3 -m venv venv-clean
source venv-clean/bin/activate
pip install -r requirements-minimal.txt

# 設定リセット
git checkout config/config.yaml

# 環境変数再設定
export HUGGINGFACE_TOKEN=hf_your_token
```

**重大な問題の場合:**
```bash
# 完全なシステムリセット
git stash  # 未保存の変更を退避
git reset --hard HEAD
git clean -fd

# 仮想環境完全再作成
rm -rf venv-clean/
python3 -m venv venv-clean
source venv-clean/bin/activate
pip install --upgrade pip
pip install -r requirements-minimal.txt

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
pip list | grep -E "(torch|transformers|pyannote)"

# GPU情報（該当する場合）
nvidia-smi
nvcc --version

# エラーログ
cat logs/transcribe_*.log | tail -50

# 設定情報
cat config/config.yaml
```

### 報告先

1. **GitHub Issues**: https://github.com/yourusername/transcribe_audio/issues
2. **GitHub Discussions**: 一般的な質問
3. **緊急度の高い問題**: Issue に `urgent` ラベル

### 効果的な報告方法

**良い報告例:**
```
タイトル: CUDA out of memory エラー（RTX 4080、15分音声）

環境:
- OS: Ubuntu 20.04
- GPU: RTX 4080 16GB
- Python: 3.11.5
- torch: 2.1.0+cu118

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
- chunk_length: 15 に変更も試行済み
```

---

このトラブルシューティングガイドで解決しない問題がありましたら、お気軽にGitHub Issuesまでご報告ください。継続的にガイドを更新し、より良いサポートを提供いたします。