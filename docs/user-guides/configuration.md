# 設定ガイド ⚙️

transcribe_audioシステムの設定管理に関する包括的なガイドです。

## 📋 目次

- [設定ファイル概要](#設定ファイル概要)
- [config.yaml詳細](#configyaml詳細)
- [環境変数](#環境変数)
- [実行時パラメータ](#実行時パラメータ)
- [最適化設定](#最適化設定)
- [トラブルシューティング](#トラブルシューティング)

## 設定ファイル概要

transcribe_audioは以下の階層で設定を管理します：

1. **config/config.yaml** - メイン設定ファイル
2. **環境変数** - 機密情報・実行時設定
3. **コマンドライン引数** - 実行時オーバーライド
4. **pyproject.toml** - 開発・品質管理設定

## config.yaml詳細

### 基本構造

```yaml
# config/config.yaml
gdrive:          # Google Drive API設定
whisper:         # Whisper音声認識設定
speaker_diarization:  # 話者分離設定
logging:         # ログ設定
```

### Google Drive設定

```yaml
gdrive:
  credentials_file: credentials.json      # Google Drive認証ファイル
  token_file: token.pickle               # 認証トークンファイル
  url: "https://www.youtube.com/watch?v=QxnWrMasELQ"  # デフォルトURL
  chunk_size: 100                        # ダウンロードチャンクサイズ(MB)
  
  # 追加オプション（省略可能）
  timeout: 300                           # タイムアウト時間（秒）
  retry_count: 3                         # リトライ回数
  upload_folder_id: null                 # アップロード先フォルダID
```

### 音声認識設定

```yaml
whisper:
  # 基本設定
  model: Qwen/Qwen3-ASR-1.7B  # デフォルトモデル（最高精度・2026年ベンチマークトップ）
  language: ja                           # デフォルト言語
  chunk_size: 100                        # 音声分割サイズ（秒）
  device: cuda                           # 推論デバイス (cuda/cpu/auto)
  
  # 生成パラメータ
  beam_size: 5                           # ビームサーチサイズ
  best_of: 3                            # 候補数
  temperature: 0.1                       # 生成温度
  context_file: "config/context_hints.txt"  # 固有名詞・専門用語の認識ヒントファイル（下記参照）
  
  # 言語別モデル設定
  language_models:
    ja:                                  # 日本語
      default: Qwen/Qwen3-ASR-1.7B
      alternatives:
        - kotoba-tech/kotoba-whisper-v2.2
        - openai/whisper-large-v3
    en:                                  # 英語
      default: openai/whisper-large-v3
      alternatives:
        - Qwen/Qwen3-ASR-1.7B
        - large-v3
        - medium
        - small
  
  # モデル履歴（デバッグ用）
  model_history:
    current: Qwen/Qwen3-ASR-1.7B
    previous:
      - model: whisper-large-v3
        commit: c065e48
        description: "Whisper v3修正時"
  
  # 利用可能モデルの詳細情報
  available_models:
    tiny:
      description: "最小モデル（高速、低精度）"
      size: "39MB"
      speed: "fast"
      accuracy: "low"
    base:
      description: "基本モデル（バランス型）"
      size: "74MB"
      speed: "medium"
      accuracy: "medium"
    small:
      description: "小モデル（推奨）"
      size: "244MB"
      speed: "medium"
      accuracy: "good"
    medium:
      description: "中モデル（高精度）"
      size: "769MB"
      speed: "slow"
      accuracy: "high"
    large-v3:
      description: "大モデル（最高精度）"
      size: "1550MB"
      speed: "slow"
      accuracy: "highest"
    kotoba-tech/kotoba-whisper-v2.2:
      description: "日本語特化モデル（Whisperエンジン）"
      size: "1550MB"
      speed: "medium"
      accuracy: "high"
      language: "ja"
    openai/whisper-large-v3:
      description: "OpenAI公式大モデル"
      size: "1550MB"
      speed: "slow"
      accuracy: "highest"
    Qwen/Qwen3-ASR-1.7B:
      description: "Qwen3-ASR (最高精度・2026年ベンチマークトップ)"
      size: "1700MB"
      speed: "medium"
      accuracy: "highest"
      language: "ja"
      engine: "qwen3-asr"
```

#### `context_file`（固有名詞・専門用語のヒント）

`./tc`（`Qwen/Qwen3-ASR-*`系モデル使用時のみ有効。WhisperTranscriptionEngineは本設定を使用しない）実行時に、
人名・製品名・専門用語など誤変換しやすい語を専用ファイルで渡すことで、認識精度を改善できます。

**使い方**:

```bash
# 1. サンプルをコピーして実ファイルを作成する
cp config/context_hints.txt.sample config/context_hints.txt

# 2. 誤変換されやすい語を1行に1つずつ記載する
```

`config/context_hints.txt` の書式:

```
# '#'で始まる行と空行はコメント・無視される
田中太郎
GAZOO Racing
スーパーGT
```

記載した語彙はすべて連結され、Qwen3-ASRへの認識ヒント文字列として渡されます。
`config/context_hints.txt` は `.gitignore`（`*.txt`）により既定でGit管理対象外です
（固有名詞・個人情報を誤ってコミットしないため）。`context_file` のパスは
`whisper.context_file` で変更できます。

ファイルが存在しない場合・内容が空（コメントのみ含む）の場合は、従来どおり
ヒントなしで動作します（後方互換）。

### 話者分離設定

```yaml
speaker_diarization:
  enable: false                          # 話者分離機能のデフォルト有効/無効
  model: "pyannote/speaker-diarization-3.1"  # 話者分離モデル
  min_speakers: null                     # 最小話者数（自動検出）
  max_speakers: null                     # 最大話者数（自動検出）
  device: "auto"                         # デバイス設定 (auto/cuda/cpu)
  
  # 出力設定
  output_format:
    show_speaker_labels: true            # 話者ラベル表示
    speaker_label_format: "話者{num}"    # 話者ラベル形式
    include_confidence: false            # 信頼度表示
    merge_short_segments: true           # 短い区間をマージ
    min_segment_duration: 0.5            # 最小区間長（秒）
  
  # 高度設定（省略可能）
  clustering:
    method: "spectral"                   # クラスタリング手法
    threshold: 0.5                       # クラスタリング閾値
  preprocessing:
    normalize_audio: true                # 音声正規化
    remove_silence: true                 # 無音区間除去
```

### ログ設定

```yaml
logging:
  level: INFO                            # ログレベル (DEBUG/INFO/WARNING/ERROR)
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: logs/transcribe.log              # ログファイルパス
  max_size: 10485760                     # 最大ログサイズ（バイト）
  backup_count: 5                        # バックアップファイル数
  
  # コンソール出力設定
  console:
    enabled: true                        # コンソール出力有効化
    level: INFO                          # コンソール出力レベル
    colored: true                        # カラー出力
```

## 環境変数

### 必須環境変数

```bash
# HuggingFace認証（話者分離機能使用時必須）
export HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Google Drive認証（省略可能、credentials.jsonがある場合）
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

### オプション環境変数

```bash
# CUDA設定
export CUDA_VISIBLE_DEVICES=0           # 使用するGPU ID
export CUDA_DEVICE_ORDER=PCI_BUS_ID     # GPU順序

# PyTorch設定
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128  # メモリ分割設定

# HuggingFace設定
export HF_HOME=/custom/cache/path       # HuggingFaceキャッシュディレクトリ
export TRANSFORMERS_CACHE=/custom/transformers/cache

# ログ設定
export TRANSCRIBE_LOG_LEVEL=DEBUG       # ログレベルオーバーライド
export TRANSCRIBE_LOG_FILE=/custom/log/path.log  # ログファイルパス

# パフォーマンス設定
export TRANSCRIBE_MAX_WORKERS=4         # 最大ワーカー数
export TRANSCRIBE_CHUNK_SIZE=300        # デフォルトチャンクサイズ
```

### .env ファイル使用

```bash
# プロジェクトルートに .env ファイル作成
cat > .env << EOF
HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
CUDA_VISIBLE_DEVICES=0
TRANSCRIBE_LOG_LEVEL=INFO
EOF

# 自動読み込み（python-dotenv は依存関係に含まれる）
# uv sync でインストール済み。追加で入れる場合は:
uv pip install python-dotenv
```

## 実行時パラメータ

### exec.sh / exec_local.sh パラメータ

```bash
# 基本パラメータ
./tc --language ja                 # 言語設定
./tc --device cuda                 # デバイス設定
./tc --verbose                     # 詳細ログ出力

# 話者分離パラメータ
./tc --enable-diarization          # 話者分離有効化
./tc --max-speakers 3              # 最大話者数指定

# 出力設定
./tc --output-format txt           # 出力形式 (txt/srt/vtt/json)
./tc --output-dir ./output         # 出力ディレクトリ

# パフォーマンス設定
./tc --chunk-size 300              # チャンクサイズ
./tc --batch-size 8                # バッチサイズ
./tc --no-cache                    # キャッシュ無効化
```

### Python API パラメータ

```python
from transcriber import WhisperTranscriber, TranscriptionConfig

# 設定オブジェクトでの指定
config = TranscriptionConfig(
    model="Qwen/Qwen3-ASR-1.7B",
    language="ja",
    device="cuda",
    chunk_size=300,
    temperature=0.1,
    beam_size=5,
    
    # パフォーマンス設定
    max_cache_size=5,
    enable_async=True,
    progress_bar=True,
    
    # RTX 4080最適化
    optimal_batch_size=8,
    memory_efficiency=True,
    enable_multi_stream=True
)

transcriber = WhisperTranscriber(config)
```

## 最適化設定

### GPU最適化設定

```yaml
# config.yaml に追加
gpu_optimization:
  # RTX 4080向け設定
  rtx_4080:
    batch_size: 8
    memory_pool_size: 12                 # GB
    concurrent_streams: 4
    enable_tensor_sharing: true
    
  # 汎用GPU設定
  generic:
    batch_size: 4
    memory_pool_size: 8
    concurrent_streams: 2
    
  # メモリ節約設定
  low_memory:
    batch_size: 2
    memory_pool_size: 4
    concurrent_streams: 1
    enable_gradient_checkpointing: true
```

### CPU最適化設定

```yaml
cpu_optimization:
  # 高性能CPU設定
  high_performance:
    num_threads: 8
    batch_size: 2
    enable_mkldnn: true
    
  # 低リソース設定
  low_resource:
    num_threads: 2
    batch_size: 1
    enable_mkldnn: false
```

### モデルキャッシュ設定

```yaml
model_cache:
  enabled: true
  max_size: 5                            # 最大キャッシュ数
  cache_dir: ~/.cache/transcribe_audio   # キャッシュディレクトリ
  cleanup_on_exit: false                 # 終了時クリーンアップ
  compression: true                      # キャッシュ圧縮
```

## 設定の読み込み・管理

### AppConfig クラス使用

```python
from config import AppConfig

# 設定読み込み
config = AppConfig.load_from_yaml("config/config.yaml")

# 階層指定での取得
model_name = AppConfig.get('whisper', 'model')
log_level = AppConfig.get('logging', 'level', default='INFO')

# 環境変数での上書き
# TRANSCRIBE_WHISPER_MODEL=custom-model python script.py
```

### カスタム設定ファイル

```python
# カスタム設定ファイルの使用
custom_config = AppConfig.load_from_yaml("custom_config.yaml")

# 実行時での設定変更
config = TranscriptionConfig.from_dict({
    'model': 'openai/whisper-large-v3',
    'language': 'en',
    'device': 'cpu'
})
```

### 設定の検証

```python
from transcriber import TranscriptionConfig
from exceptions import ConfigurationError

try:
    config = TranscriptionConfig(
        model="invalid-model",
        device="invalid-device"
    )
    config.validate()  # 設定の妥当性検証
    
except ConfigurationError as e:
    print(f"設定エラー: {e}")
```

## プロファイル別設定

### 環境別設定ファイル

```bash
# 開発環境
config/config.dev.yaml

# 本番環境
config/config.prod.yaml

# テスト環境
config/config.test.yaml
```

```python
import os

# 環境に応じた設定ファイル選択
env = os.getenv('TRANSCRIBE_ENV', 'dev')
config_file = f"config/config.{env}.yaml"
config = AppConfig.load_from_yaml(config_file)
```

### デプロイ設定例

```yaml
# config/config.prod.yaml
whisper:
  model: Qwen/Qwen3-ASR-1.7B
  device: cuda
  chunk_size: 300
  
speaker_diarization:
  enable: true
  max_speakers: 5
  
logging:
  level: WARNING
  file: /var/log/transcribe_audio/prod.log
  
performance:
  enable_monitoring: true
  metrics_endpoint: "http://monitoring.example.com"
```

## トラブルシューティング

### よくある設定問題

**Q: HuggingFaceトークンエラー**
```bash
# トークン確認
echo $HUGGINGFACE_TOKEN

# 権限確認
# https://huggingface.co/pyannote/speaker-diarization-3.1 でAgree

# .envファイル使用
echo "HUGGINGFACE_TOKEN=hf_xxx" > .env
```

**Q: CUDA out of memory**
```yaml
# config.yaml で調整
whisper:
  chunk_size: 60        # 小さくする
  
gpu_optimization:
  rtx_4080:
    batch_size: 2       # 小さくする
    memory_pool_size: 6 # 小さくする
```

**Q: モデルダウンロードエラー**
```bash
# キャッシュクリア
rm -rf ~/.cache/huggingface
rm -rf ~/.cache/transcribe_audio

# プロキシ設定
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

**Q: 設定ファイルが読み込まれない**
```python
# 設定ファイルパス確認
import os
print(os.path.abspath("config/config.yaml"))

# 権限確認
ls -la config/config.yaml

# YAML構文チェック (uv 経由)
uv run python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"
```

### 設定デバッグ

```python
# 現在の設定を確認
from config import AppConfig
import json

config = AppConfig.load_from_yaml()
print(json.dumps(config, indent=2, ensure_ascii=False))

# 環境変数確認
import os
for key, value in os.environ.items():
    if 'TRANSCRIBE' in key or 'HUGGINGFACE' in key:
        print(f"{key}: {value}")
```

### 設定のバックアップ・復元

```bash
# 設定バックアップ
cp config/config.yaml config/config.yaml.backup.$(date +%Y%m%d)

# デフォルト設定復元
git checkout config/config.yaml

# 設定の差分確認
diff config/config.yaml config/config.yaml.backup.*
```

---

## 📞 サポート

- **設定に関する質問**: [GitHub Discussions](https://github.com/yourusername/transcribe_audio/discussions)
- **設定エラー報告**: [GitHub Issues](https://github.com/yourusername/transcribe_audio/issues)
- **設定例の提供**: プルリクエストでの貢献歓迎

設定に関する最新情報は [GitHub Repository](https://github.com/yourusername/transcribe_audio) をご確認ください。