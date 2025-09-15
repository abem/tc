# 音声文字起こしシステム（tc） 🎙️

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![UV Package Manager](https://img.shields.io/badge/package--manager-uv-orange.svg)](https://github.com/astral-sh/uv)
[![Whisper](https://img.shields.io/badge/model-kotoba--whisper--v2.2-green.svg)](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.2)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ 概要

**シンプルで高精度な日本語音声文字起こしツール**

- **🇯🇵 日本語特化** - kotoba-tech/kotoba-whisper-v2.2による高精度日本語文字起こし
- **⚡ ワンコマンド実行** - `./tc`だけでconfig.yamlから設定を自動読み込み
- **☁️ Google Drive連携** - 音声ファイルの自動ダウンロード・結果アップロード
- **🔧 uv パッケージ管理** - 最新のPython依存関係管理ツール使用
- **🎯 シンプル設計** - 複雑な設定不要、すぐに使える

## 🚀 クイックスタート

### 1. 必要な準備

```bash
# uvのインストール（未インストールの場合）
curl -LsSf https://astral.sh/uv/install.sh | sh

# プロジェクトのクローン
git clone <repository-url>
cd tc

# Hugging Faceトークンの設定
echo "HUGGINGFACE_TOKEN=hf_your_token_here" > .env

# Google Drive認証ファイルの配置
# Google Cloud Consoleからcredentials.jsonを取得して配置
```

### 2. 設定ファイル編集

`config/config.yaml`を編集して処理対象URLを設定：

```yaml
gdrive:
  url: "https://drive.google.com/file/d/your_file_id/view"

whisper:
  model: kotoba-tech/kotoba-whisper-v2.2
  language: ja
  device: cuda  # または cpu
```

### 3. 実行

```bash
# シンプル実行（推奨）
./tc

# 完了！結果はoutput/フォルダとGoogle Driveに保存されます
```

## 💻 使用方法

### 基本実行

```bash
# config.yamlの設定で自動実行
./tc

# 別のファイルを指定
./tc https://drive.google.com/file/d/another_file_id/view

# ローカルファイルを処理
./tc audio.mp3
```

### オプション

```bash
# アップロードをスキップ
./tc --no-upload

# 出力ディレクトリを指定
./tc --output-dir results

# モデルを変更
./tc --model openai/whisper-large-v3

# デバイスを指定
./tc --device cpu

# ヘルプ表示
./tc --help
```

## 🔧 設定

### config/config.yaml

```yaml
gdrive:
  credentials_file: credentials.json
  token_file: token.pickle
  url: "処理対象のGoogle Drive URL"
  chunk_size: 100

whisper:
  model: kotoba-tech/kotoba-whisper-v2.2
  language: ja
  device: cuda
  beam_size: 5
  best_of: 3
  temperature: 0.1

  # 言語別モデル設定
  language_models:
    ja:
      default: kotoba-tech/kotoba-whisper-v2.2
      alternatives:
        - drewschaub/whisper-large-v3-japanese-4k-steps
        - openai/whisper-large-v3
    en:
      default: openai/whisper-large-v3
      alternatives:
        - large-v3
        - medium

speaker_diarization:
  enable: false
  model: "pyannote/speaker-diarization-3.1"

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: logs/transcribe.log
```

### .env ファイル

```bash
# Hugging Face認証トークン
HUGGINGFACE_TOKEN=hf_your_token_here
```

## 🏗️ アーキテクチャ

### プロジェクト構造

```
tc/
├── tc                          # メインCLIコマンド
├── config/
│   └── config.yaml            # 設定ファイル
├── core/                      # コア機能
│   ├── config.py              # 統一設定管理
│   └── transcription_interface.py  # 文字起こしエンジン
├── output/                    # 出力ファイル
├── logs/                      # ログファイル
├── .env                       # 環境変数
└── credentials.json           # Google Drive認証
```

### 主要機能

1. **統一設定管理** (`core/config.py`)
   - YAML設定の読み込み
   - 環境変数との統合
   - デフォルト値の管理

2. **文字起こしエンジン** (`core/transcription_interface.py`)
   - Whisperモデルの管理
   - 音声前処理
   - チャンク分割処理
   - タイムスタンプ付与

3. **Google Drive連携** (`gdrive_handler.py`)
   - ファイルダウンロード
   - 結果アップロード
   - 権限管理

4. **CLIインターフェース** (`tc`)
   - 引数解析
   - 設定読み込み
   - 進捗表示
   - エラーハンドリング

## 🎯 サポートモデル

### 日本語特化モデル
- **kotoba-tech/kotoba-whisper-v2.2** (推奨)
- drewschaub/whisper-large-v3-japanese-4k-steps

### 多言語モデル
- openai/whisper-large-v3
- openai/whisper-large-v2
- openai/whisper-medium
- openai/whisper-small

## 📊 出力形式

### 文字起こし結果

```
[00:00] やっぱりここから3秒
[00:30] ハミルトンはセクター1最速これは速いですねここまでセクター2秒ぐらい返りますが
[01:00] 1004秒
[01:30] ごめん
...
```

### メタデータ
- 処理時間
- 使用モデル
- 言語設定
- 文字数統計
- デバイス情報

## 🔍 トラブルシューティング

### よくある問題

#### 1. CUDA out of memory
```bash
# CPUモードで実行
./tc --device cpu
```

#### 2. Google Drive認証エラー
```bash
# credentials.jsonの確認
ls -la credentials.json

# 権限の確認
# Google Cloud Consoleでスコープを確認
```

#### 3. Hugging Face認証エラー
```bash
# トークンの確認
cat .env

# 形式の確認（HUGGINGFACE_TOKEN=hf_xxx）
```

### ログ確認

```bash
# 詳細ログの確認
tail -f logs/transcribe.log

# エラーログの検索
grep -i error logs/transcribe.log
```

## 🧪 開発・デバッグ

### デバッグツール

```bash
# Hugging Faceトークンテスト
uv run python test_hf_token.py

# kotoba-whisperモデル詳細確認
uv run python debug_kotoba.py
```

### 依存関係管理

```bash
# パッケージの追加
uv pip install package_name

# 依存関係の同期
uv sync

# 要件ファイルの更新
uv pip freeze > requirements.txt
```

## 📝 ライセンス

MIT License

## 🤝 コントリビューション

1. このリポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📞 サポート

- Issues: [GitHub Issues](../../issues)
- ドキュメント: `docs/` フォルダ内の各種ガイド
- 設定ガイド: `CLAUDE.md` (べからず集)

## 🔄 更新履歴

### v2025.09.16 - シンプル化リリース
- ✅ `./tc`ワンコマンド実行を実現
- ✅ config.yamlから全設定を自動読み込み
- ✅ .env自動読み込み機能追加
- ✅ UI/UX大幅改善（絵文字・進捗表示）
- ✅ kotoba-whisper-v2.2日本語特化モデル採用
- ✅ Google Drive自動アップロード
- ✅ uv パッケージマネージャー対応

### v2025.07.29 - 統一システム
- 🔧 コア機能の統一化
- 📊 パフォーマンス監視機能
- 🧪 包括的テストスイート
- 📚 ドキュメント整備

---

**🎙️ 簡単・高精度・日本語対応の音声文字起こしツール `tc`**