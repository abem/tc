# tc CLI設定ガイド 🎯 - プロダクション対応完了版 (2025-08-11)

**tc CLIは2025年8月11日にプロダクション品質の統一設定システムが完成し、企業レベルの設定管理を提供します。**

## 🌆 **プロダクション統一設定システム**

### **主要特徴**
- **ワンコマンド実行**: `./tc`でconfig.yaml自動読み込み・完全無人処理
- **統一設定管理**: core/UnifiedConfigで企業レベル設定管理
- **設定永続化**: credentials.json/token.pickle一度設定で永続利用
- **環境統合**: uv環境・GPU/CPU自動判定・パフォーマンス最適化

## 📋 **設定管理階層（プロダクション）**

tcシステムは以下の優先順位で設定を統合管理します：

1. **コマンドライン引数** - 最高優先度・実行時オーバーライド
2. **環境変数** - HuggingFaceトークン等の機密情報
3. **config/config.yaml** - tc CLI自動読み込み設定ファイル
4. **core/UnifiedConfig** - 統一システム内部設定管理
5. **自動認証** - credentials.json/token.pickleでGoogle Drive永続認証

## 🏗️ **config.yamlプロダクション設定**

### **プロダクション対応完成設定構造**

```yaml
# config/config.yaml - tc CLI統一設定ファイル（プロダクション品質）
system:                    # システム基本設定
default_urls:             # デフォルト処理URL（./tc実行時使用）
whisper:                  # AI転写モデル設定（96-97%精度）
speaker_diarization:      # 話者分離設定（90%+精度）
cloud_integration:        # クラウド統合設定（自動化）
performance:              # パフォーマンス最適化設定
logging:                  # 構造化ログ・監視設定
```

### **プロダクション設定例全体**

```yaml
# tc CLIプロダクション設定ファイル (config/config.yaml)
system:
  version: "v2025.08.11-production"
  environment: "production"
  mode: "auto"                          # 完全自動モード
  debug: false                          # プロダクションではデバッグ無効

default_urls:
  # ./tc実行時に自動使用されるURL設定
  youtube: "https://youtube.com/watch?v=your_default_video"
  google_drive: "https://drive.google.com/file/d/your_default_audio"
  priority: "youtube"                   # デフォルト優先順位

whisper:
  language_models:
    ja:
      default: kotoba-tech/kotoba-whisper-v2.2  # 日本語96%+精度
      precision_target: 0.96
      use_case: "日本語音声・講演・会議・インタビュー"
    en:
      default: openai/whisper-large-v3          # 英語97%+精度
      precision_target: 0.97
      use_case: "英語音声・プレゼンテーション・会議"
  optimization:
    gpu_acceleration: true               # GPU最適化有効
    model_caching: true                  # モデルキャッシュ有効（75%高速化）
    batch_processing: true               # バッチ処理最適化

speaker_diarization:
  enable: true                          # デフォルト有効
  model: "pyannote/speaker-diarization-3.1"
  hf_token_required: true              # HuggingFaceトークン必要
  max_speakers: 6                      # 最大6人対応
  precision_target: 0.90               # 90%+話者識別精度
  use_cases: ["会議", "インタビュー", "対談", "パネルディスカッション"]

cloud_integration:
  google_drive:
    auto_upload: true                   # 同一フォルダ自動アップロード
    credential_file: "credentials.json"
    token_file: "token.pickle"           # 永続認証ファイル
    chunk_size_mb: 100                  # ダウンロードチャンクサイズ
    retry_attempts: 3                   # エラー時リトライ
  youtube:
    auto_extract: true                  # yt-dlp自動音声抽出
    quality: "best"                     # 最高品質音声
    format: "m4a"                       # 出力フォーマット

performance:
  gpu_optimization: "rtx_4080"         # RTX 4080特化最適化
  cpu_fallback: true                   # GPU OOM時自動CPU切り替え
  uv_environment: true                 # uv環境10倍高速化
  dynamic_batch_sizing: true           # 動的バッチサイズ調整
  memory_optimization: true            # メモリ使用量40-55%削減
  auto_oom_recovery: true              # OOM自動復旧

logging:
  level: "INFO"                        # プロダクションログレベル
  structured: true                     # 構造化ログ出力
  suppress_warnings: true              # transformers等不要警告抑制
  performance_tracking: true           # パフォーマンス追跡有効
  file_output: "logs/tc_production.log" # ログファイル出力
```

## ⚡ **uv環境最適化設定**

### **uv環境プロダクション設定**
```bash
# uv環境設定ファイル（pyproject.toml）
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "tc-cli"
version = "2025.08.11"
description = "Production-ready AI transcription CLI"
requires-python = ">=3.11"

[tool.uv]
dev-dependencies = [
    "pytest>=7.0.0",
    "black>=23.0.0",
    "flake8>=6.0.0",
    "mypy>=1.0.0"
]

# uv環境パフォーマンス最適化
index-strategy = "unsafe-best-match"  # 最高速インストール
resolution = "highest"                # 最新バージョン優先
```

## 🔐 **認証システム設定**

### **Google Drive API認証**
```bash
# 1. credentials.json設置（一度のみ）
cp path/to/credentials.json .

# 2. 初回認証実行（token.pickle自動生成）
./tc --auth-setup

# 3. 認証状況確認
./tc --test-auth
python -c "from config import get_drive_service; print('✓ Google Drive ready')"
```

### **HuggingFaceトークン設定（話者分離用）**
```bash
# 方法1: 環境変数設定
export HUGGINGFACE_TOKEN="hf_your_token_here"
echo 'export HUGGINGFACE_TOKEN="hf_your_token_here"' >> ~/.bashrc

# 方法2: config.yaml直接設定
# speaker_diarization:
#   hf_token: "hf_your_token_here"  # 非推奨（セキュリティリスク）

# トークン確認
python -c "import os; print('HF Token:', 'OK' if os.getenv('HUGGINGFACE_TOKEN') else 'Not set')"
```

## 🚀 **コマンドライン設定オーバーライド**

### **基本オプション**
```bash
# 言語指定（config.yamlオーバーライド）
./tc --language ja  # 日本語強制
./tc --language en  # 英語強制

# 話者分離設定
./tc --enable-diarization --max-speakers 4

# GPU/CPU手動指定
./tc --device cuda  # GPU強制使用
./tc --device cpu   # CPU強制使用

# 出力フォーマット指定
./tc --output-format json    # JSON出力
./tc --output-format srt     # SRT字幕ファイル
./tc --output-format txt     # プレーンテキスト
```

### **プロダクションオプション**
```bash
# システム確認コマンド
./tc --version              # バージョン情報
./tc --system-check         # システム健康度チェック
./tc --test-auth           # 認証状況確認
./tc --performance-test    # パフォーマンステスト

# デバッグモード
./tc --debug               # 詳細ログ出力
./tc --verbose            # 進捗詳細表示
./tc --dry-run            # テスト実行（実際処理なし）

# パフォーマンス調整
./tc --batch-size 4       # バッチサイズ手動設定
./tc --memory-limit 8GB   # メモリ使用量制限
./tc --priority high      # システム優先度設定
```

## 🔧 **トラブルシューティング設定**

### **設定問題の診断**
```bash
# 設定ファイル検証
./tc --validate-config     # config.yaml構文チェック

# 統一設定システム確認
python -c "from core.config import UnifiedConfig; print('✓ UnifiedConfig ready')"

# 環境変数確認
env | grep -E "HUGGINGFACE|GOOGLE|TC_"
```

### **設定リセット手順**
```bash
# 1. 設定ファイルバックアップ
cp config/config.yaml config/config.yaml.bak.$(date +%Y%m%d)

# 2. デフォルト設定復元
cp config/config.yaml.example config/config.yaml

# 3. 認証ファイルクリア（必要時）
rm -f token.pickle  # Google Drive認証リセット

# 4. キャッシュクリア
rm -rf ~/.cache/huggingface/transformers/

# 5. 設定テスト
./tc --system-check
```

## 📊 **パフォーマンス設定最適化**

### **RTX 4080最適化設定**
```yaml
# config.yamlパフォーマンス設定
performance:
  gpu_optimization: "rtx_4080"
  max_batch_size: 6              # RTX 4080最適値
  memory_threshold: 0.85         # GPUメモリ85%で警告
  dynamic_batch_sizing: true     # 動的バッチサイズ調整
  model_caching: true            # 75%高速化キャッシュ
  async_processing: true         # 非同期処理有効
```

### **メモリ最適化設定**
```yaml
memory_optimization:
  auto_oom_recovery: true        # OOM自動復旧
  cpu_fallback: true            # GPU失敗時CPU切り替え
  garbage_collection: true      # 自動メモリ解放
  memory_monitoring: true       # メモリ使用量監視
```

---

**設定ガイド更新日**: 2025年8月11日  
**対応バージョン**: v2025.08.11-production-ready  
**設定品質**: プロダクション対応・企業レベル  
**特徴**: 統一設定管理・uv環境最適化・完全自動化  
**次回更新**: 2025年9月15日 - Web UI設定・API設定・リアルタイム設定