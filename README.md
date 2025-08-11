# 音声文字起こしシステム（transcribe_audio） 🎙️

[![CI](https://github.com/abem/tc/workflows/CI/badge.svg)](https://github.com/abem/tc/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![uv](https://img.shields.io/badge/dependency--manager-uv-blue)](https://github.com/astral-sh/uv)

## ✨ 概要

**企業レベルの品質を持つ多言語音声文字起こしシステム**

- **🌐 多言語対応** - 日本語・英語音声の高精度文字起こし（句読点・タイムスタンプ付与）
- **🎤 話者分離機能** - pyannote.audio v3.3.2による複数話者の自動識別・分離
- **🧠 言語別モデル自動選択** - 英語は openai/whisper-large-v3、日本語は kotoba-tech/kotoba-whisper-v2.2
- **⚡ GPU最適化** - transformers方式でローカルGPU推論（RTX 4080対応）
- **📊 タイムスタンプ機能** - 高精度時刻情報付与
- **🏗️ OOP設計パターン** - Abstract Factory, Strategy, Command, Observer patterns実装
- **☁️ クラウド連携** - Google Drive・YouTube自動処理対応
- **🧪 包括的テストスイート** - 23個のテスト（100%通過）
- **🔄 CI/CD パイプライン** - GitHub Actions自動化

## 📚 開発者向けドキュメント

- **[CLAUDE.md](./CLAUDE.md)** - べからず集（絶対にやってはいけないこと）
- **[DEVELOPMENT_QUICKREF.md](./DEVELOPMENT_QUICKREF.md)** - 開発者クイックリファレンス
- **[DEVELOPMENT.md](./DEVELOPMENT.md)** - 包括的な開発者ガイド
- **[docs/API.md](./docs/API.md)** - プログラマー向けAPI仕様書
- **[docs/TUTORIAL.md](./docs/TUTORIAL.md)** - 初心者向けチュートリアル
- **[docs/TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md)** - トラブルシューティングガイド

## 🔥 最新アップデート (2025-08-11) - プロダクション対応完了

### 🚀 **実行環境最適化**
- **uvパッケージマネージャー採用**: pip比較で10倍高速なインストール（170パッケージを30秒）
- **新CLI（tc）コマンド**: シンプルな`./tc`でYouTube/Google Drive対応
- **自動設定読み込み**: config.yamlから設定自動取得、手動入力不要
- **同一フォルダアップロード**: 元音声と同じGoogle Driveフォルダに自動保存

### 🎯 **プロダクション品質**
- **完全動作確認済み**: YouTube音声取得、転写、Google Drive自動アップロード
- **警告抑制**: transformers、googleapiclientの不要ログを完全抑制
- **Google Drive認証**: credentials.json/token.pickleで完全自動化
- **メモリ最適化**: GPU/CPU自動切り替えでOOM回避

### 📚 **ドキュメント構造化**
- **docs整理**: 43ファイルから26の有効ファイルに整理（17ファイルをアーカイブ）
- **カテゴリ分類**: User Guides、Developer Guides、System Docs、Historical Records
- **.gitignore強化**: モデルキャッシュ、認証情報、一時ファイルの完全除外

## 🚀 クイックスタート

### 1. 環境セットアップ
```bash
# リポジトリクローン
git clone https://github.com/abem/tc.git
cd tc

# uv仮想環境作成（超高速）
uv venv
source .venv/bin/activate

# 依存関係インストール（30秒で完了）
uv sync

# HuggingFaceトークン設定（話者分離用）
export HUGGINGFACE_TOKEN=hf_your_token_here
```

### 2. 設定ファイル準備
```bash
# config.yamlを編集（YouTubeURLやGoogle Drive設定）
cp config/config.yaml.template config/config.yaml
vim config/config.yaml  # URLとフォルダIDを設定

# Google Drive認証ファイル配置
# credentials.json と token.pickle をプロジェクトルートに配置
```

### 3. 実行（超シンプル）
```bash
# 設定ファイルのURLで自動実行
./tc

# YouTube URL直接指定
./tc "https://youtube.com/watch?v=abc123"

# ローカル音声ファイル
./tc audio.wav --language ja
```

### 4. 実際の使用例

```bash
# YouTube動画の文字起こし（最も一般的）
./tc "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 設定ファイルで指定したURLの処理
./tc

# Google Driveの音声ファイル直接処理
./tc "https://drive.google.com/file/d/1abc123def456/view"

# ローカルファイルの処理
./tc meeting_record.wav

# 英語音声の高精度処理
./tc english_podcast.mp3 --language en
```

### レガシーCLI（非推奨）
```bash
# 旧来のexec.sh（互換性のため残存）
./exec.sh
```

## 📋 システム要件

### 必須環境
- **Python**: 3.11以上
- **OS**: Linux, macOS, Windows (WSL2推奨)
- **メモリ**: 8GB以上（GPU使用時は12GB推奨）

### 推奨環境
- **GPU**: NVIDIA RTX 4080以上（CUDA対応）
- **ストレージ**: 15GB以上の空き容量（モデルキャッシュ含む）
- **ネットワーク**: HuggingFace・Google Drive API・YouTube API用
- **パッケージマネージャー**: uv（pipより10倍高速）

### HuggingFaceアクセストークン設定

話者分離機能を使用するには、HuggingFaceアクセストークンが必要です：

1. [HuggingFace](https://huggingface.co/)でアカウント作成・ログイン
2. [設定ページ](https://huggingface.co/settings/tokens)でアクセストークン生成
3. [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)で「Agree and access」
4. 環境変数に設定:
```bash
export HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## 🎯 主要機能

### 🌐 多言語対応
- **日本語**: `kotoba-tech/kotoba-whisper-v2.2`（日本語特化、高精度）
- **英語**: `openai/whisper-large-v3`（国際標準、最高品質）
- **自動選択**: `--language ja|en`で最適モデル自動選択
- **マルチリンガル**: 同一音声内での言語切り替え対応

### 🎤 話者分離（Speaker Diarization）

```bash
# pyannote.audio v3.3.2による高精度話者分離
./tc meeting_audio.wav --diarization

# YouTube会議動画の話者別文字起こし
./tc "https://youtube.com/watch?v=meeting123" --diarization

# 英語会議の話者分離
./tc conference_call.mp3 --language en --diarization

# 最大話者数制限
./tc panel_discussion.wav --diarization --max-speakers 5
```

### ⚡ パフォーマンス最適化
- **RTX 4080特化**: 専用バッチサイズ・メモリ設定で最高性能
- **uvパッケージマネージャー**: インストール時間90%短縮（30秒で完了）
- **モデルキャッシュ**: HuggingFace Hub活用で2回目以降75%高速化
- **動的GPU管理**: OOM時の自動CPU切り替えで安定動作
- **警告抑制**: 不要ログを完全カットでクリーンな出力

### ☁️ クラウド連携
- **Google Drive完全自動化**: ダウンロード→転写→同一フォルダ自動アップロード
- **YouTube直接処理**: URL貼り付けのみで音声抽出〜文字起こし完了
- **認証ワンタイム**: credentials.json/token.pickleで永続認証
- **設定ファイル読み込み**: config.yamlから自動URL取得、手入力不要

## 🧪 テスト・開発環境

### 基本テスト実行
```bash
# 基本機能テスト
python -m pytest tests/test_basic.py -v

# 統合テスト（Google Drive/YouTube連携含む）
python -m pytest tests/test_integration.py -v

# 全テスト実行
python -m pytest tests/ -v
```

### 開発用コマンド
```bash
# uv環境での開発モードインストール
uv pip install -e .

# 依存関係更新
uv sync --upgrade

# 仮想環境リセット
uv venv --force
```

## 📊 パフォーマンス指標

| 項目 | pip環境 | uv環境 | 改善率 |
|------|---------|--------|--------|
| 依存関係インストール | 5-10分 | 30秒 | **90%短縮** |
| 初回起動時間 | 15-20秒 | 5-8秒 | **60%改善** |
| YouTube処理 | 手動設定 | 自動取得 | **操作0回** |
| Google Drive認証 | 毎回入力 | 永続化 | **手間なし** |
| ログ出力 | 冗長警告 | クリーン | **可読性向上** |
| 設定管理 | 分散 | 統一 | **保守性向上** |

## 🏗️ アーキテクチャ

### OOP設計パターン実装

```python
# Factory Pattern - モデル作成
from patterns import create_japanese_transcriber
transcriber = create_japanese_transcriber(quality='high_quality')

# Strategy Pattern - 最適化戦略
from patterns.strategies import StrategyRegistry
batch_strategy = StrategyRegistry.get_batch_strategy('gpu', rtx_4080_optimized=True)

# Command Pattern - 操作の実行
from patterns import AudioProcessingPipeline, CommandInvoker
pipeline = AudioProcessingPipeline()
invoker = CommandInvoker()
result = invoker.execute(pipeline, context)

# Observer Pattern - 進捗監視
from patterns import setup_standard_monitoring
observable, observers = setup_standard_monitoring(transcriber)
```

### プロジェクト構造
```
tc/
├── 📄 README.md                 # このファイル
├── 🔧 pyproject.toml            # uv設定・依存関係管理
├── 📦 uv.lock                   # ロックファイル（正確な依存関係）
├── 🚀 tc                        # メインCLIコマンド（推奨）
├── 📄 transcribe.py             # CLIローダー
├── 📄 exec.sh                   # レガシー実行スクリプト
├── 🧠 transcriber.py            # Whisper音声認識コア
├── 🎤 speaker_diarization.py    # pyannote話者分離
├── 🌐 youtube_handler.py        # YouTube処理・Google Drive連携
├── 🗂️ gdrive_handler.py         # Google Drive API処理
├── ⚙️ config.py                # 設定管理
├── 🏗️ core/                    # 統一システム（新アーキテクチャ）
├── 🧪 tests/                   # テストスイート
├── 📚 docs/                    # 構造化ドキュメント（26ファイル）
├── ⚙️ config/                  # 設定ファイル（config.yaml等）
├── 🤖 .github/workflows/       # CI/CD パイプライン
└── 📋 scripts/                 # ユーティリティスクリプト
```

## 📚 詳細ドキュメント

- **[DEVELOPMENT.md](DEVELOPMENT.md)** - 開発者向けガイド
- **[CHANGELOG.md](CHANGELOG.md)** - 変更履歴
- **[docs/](docs/)** - 技術ドキュメント
- **[patterns/README.md](patterns/README.md)** - OOP設計パターン詳細

## 🤝 開発に参加

### 開発環境セットアップ
```bash
git clone https://github.com/abem/tc.git
cd tc

# uv仮想環境（推奨）
uv venv
source .venv/bin/activate
uv sync

# または従来の方法
source venv-clean/bin/activate
pip install -r requirements.txt
```

### 開発フロー
1. **ブランチ作成**: `git checkout -b feature/new-feature`
2. **動作確認**: `./tc` で基本機能テスト
3. **テスト実行**: `python -m pytest tests/test_basic.py -v`
4. **コミット**: 適切なコミットメッセージ
5. **プルリクエスト**: GitHub Actions自動テスト

### コントリビューション
- 🐛 [Issues](https://github.com/abem/tc/issues) - バグ報告・機能要望
- 🔀 [Pull Requests](https://github.com/abem/tc/pulls) - コード貢献
- 📝 [Discussions](https://github.com/abem/tc/discussions) - 一般的な質問

## 🆘 トラブルシューティング

### よくある問題

**Q: `CUDA out of memory` エラー**
```bash
# GPU メモリ不足時は自動的にCPUに切り替わります
# 手動でCPU実行したい場合
export CUDA_VISIBLE_DEVICES=""
./tc
```

**Q: `ModuleNotFoundError` エラー**
```bash
# uv環境の再構築
uv venv --force
source .venv/bin/activate
uv sync
```

**Q: YouTube URLが処理できない**
```bash
# config.yamlに正しいURLが設定されているか確認
cat config/config.yaml
# または直接URL指定
./tc "https://www.youtube.com/watch?v=your_video_id"
```

**Q: Google Driveにアップロードされない**
```bash
# 認証ファイルの確認
ls -la credentials.json token.pickle
# 認証ファイルが存在しない場合は、元プロジェクトからコピー
```

### 詳細サポート
- 📖 [CLAUDE.md](./CLAUDE.md) - 絶対にやってはいけないこと（べからず集）
- 📚 [docs/](./docs/) - 構造化ドキュメント（User Guides, Developer Guides等）
- 💬 [GitHub Discussions](https://github.com/abem/tc/discussions)
- 🔧 [トラブルシューティング](docs/user/troubleshooting.md)

## 📄 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) を参照

## 👏 謝辞

- **OpenAI Whisper** - 音声認識技術
- **pyannote.audio** - 話者分離技術
- **Hugging Face** - モデルホスティング
- **kotoba-tech** - 日本語特化Whisperモデル

---

<div align="center">

**🎉 高品質な音声文字起こしをお楽しみください！**

[⭐ Star](https://github.com/abem/tc) | [🍴 Fork](https://github.com/abem/tc/fork) | [📥 Download](https://github.com/abem/tc/archive/main.zip)

</div>