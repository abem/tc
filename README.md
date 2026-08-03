# 音声文字起こしシステム（tc） 🎙️

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![UV Package Manager](https://img.shields.io/badge/package--manager-uv-orange.svg)](https://github.com/astral-sh/uv)
[![Qwen3-ASR](https://img.shields.io/badge/model-Qwen3--ASR--1.7B-green.svg)](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ 概要

**シンプルで高精度な日本語音声文字起こしツール**

- **🏆 最高精度** - Qwen3-ASR-1.7Bによる2026年ベンチマークトップクラスの日本語文字起こし（デフォルト）
- **⚡ ワンコマンド実行** - `./tc`だけでconfig.yamlから設定を自動読み込み、仮想環境も自動構築
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

# 依存関係のインストール(pyproject.tomlのdefault-groupsでdev/qwen3含め自動解決)
uv sync

# Hugging Faceトークンの設定
echo "HUGGINGFACE_TOKEN=hf_your_token_here" > .env
```

### 2. Google Drive認証設定

#### credentials.jsonの取得

1. **Google Cloud Consoleにアクセス**
   ```
   https://console.cloud.google.com/
   ```

2. **Google Drive APIを有効化**
   - 「APIとサービス」→「ライブラリ」
   - 「Google Drive API」を検索して有効化

3. **OAuth 2.0クライアントIDの作成**
   - 「APIとサービス」→「認証情報」
   - 「認証情報を作成」→「OAuth クライアント ID」
   - アプリケーションの種類: **「デスクトップアプリ」**
   - 名前を入力（例: "TC Transcription App"）

4. **credentials.jsonをダウンロード**
   - 作成した認証情報の右側にある**ダウンロードアイコン**をクリック
   - ダウンロードしたファイルを `credentials.json` にリネーム
   - プロジェクトルート (`/path/to/tc/`) に配置

5. **OAuth同意画面の設定**
   ```
   https://console.cloud.google.com/apis/credentials/consent
   ```
   - 公開ステータスを「本番環境」に設定
   - または「テストユーザー」に自分のGmailアドレスを追加

#### 初回認証（WSL/Linux環境）

```bash
# 初回実行時に認証URLが表示されます
./tc

# 1. 表示されたURLをブラウザ（Windows側）で開く
# 2. Googleアカウントでログインして権限を許可
# 3. ブラウザがlocalhost:8080にリダイレクトされる
# 4. アドレスバーのURL全体をコピー（例: http://localhost:8080/?code=...）
# 5. ターミナルに戻ってURLを貼り付けてEnter

# 一度認証すると token.pickle が生成され、次回から自動認証されます
```

### 3. 設定ファイル編集

`config/config.yaml`を編集して処理対象URLを設定：

```yaml
gdrive:
  url: "https://drive.google.com/file/d/your_file_id/view"

whisper:
  model: Qwen/Qwen3-ASR-1.7B   # デフォルト（最高精度）
  language: null                # 既定は自動判定（ja/en等を指定すると強制）
  device: cuda  # または cpu
```

### 4. 実行

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

# モデルを変更（従来のWhisperエンジンに切り替え）
./tc --model kotoba-tech/kotoba-whisper-v2.2

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
  model: Qwen/Qwen3-ASR-1.7B   # デフォルト: 最高精度（2026年ベンチマークトップ）
  language: null                # 既定は自動判定（ja/en等を指定すると強制）
  device: cuda
  beam_size: 5
  best_of: 3
  temperature: 0.1

  # 言語別モデル設定(注: このセクションを読むコードは現在どこからも呼ばれていない
  # dead code。実際に使われるモデルは常に上記の whisper.model。詳細は
  # docs/user-guides/language_support_guide.md 参照)
  language_models:
    ja:
      default: Qwen/Qwen3-ASR-1.7B
      alternatives:
        - kotoba-tech/kotoba-whisper-v2.2
        - openai/whisper-large-v3
    en:
      default: openai/whisper-large-v3
      alternatives:
        - Qwen/Qwen3-ASR-1.7B
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
├── transcribe.py               # Rich UI対話型CLI
├── config/
│   └── config.yaml            # 設定ファイル
├── core/                      # コア機能
│   ├── config.py              # 統一設定管理
│   ├── logging.py             # 統一ロガー
│   ├── transcription_interface.py  # 文字起こしエンジン
│   ├── model_manager.py       # モデルキャッシュ管理
│   ├── cli_common.py          # CLI共通ヘルパー
│   ├── cli_workflow.py        # 入力解決・アップロードフロー
│   └── utils.py               # URL検出・デバイス解決
├── handlers/                  # 外部サービスハンドラー
│   ├── gdrive.py              # Google Drive クライアント
│   └── youtube.py             # YouTube音声抽出
├── tests/                     # テストファイル
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
   - Qwen3-ASR / Whisper のデュアルエンジン（モデル名で自動切替）
   - 音声前処理
   - 長音声チャンク分割処理（5分単位）
   - 文節改行フォーマット

3. **Google Drive連携** (`handlers/gdrive.py`)
   - ファイルダウンロード
   - 結果アップロード
   - 権限管理

4. **YouTube音声抽出** (`handlers/youtube.py`)
   - YouTube動画から音声抽出
   - メタデータ取得

5. **CLIインターフェース** (`tc`)
   - 引数解析
   - 設定読み込み
   - 進捗表示
   - エラーハンドリング

## 🎯 サポートモデル

### 🏆 最高精度モデル（デフォルト）
- **Qwen/Qwen3-ASR-1.7B** (推奨・2026年ベンチマーク WER 0.185)
  - 52の言語・方言に対応、長音声のチャンク分割に対応
  - `./tc` でデフォルト動作

### 日本語特化モデル（Whisperエンジン）
- kotoba-tech/kotoba-whisper-v2.2
- drewschaub/whisper-large-v3-japanese-4k-steps

### 多言語モデル（Whisperエンジン）
- openai/whisper-large-v3
- openai/whisper-large-v2
- openai/whisper-medium
- openai/whisper-small

> モデル名に `qwen3-asr` を含む場合は Qwen3ASREngine、
> それ以外は WhisperTranscriptionEngine が自動選択されます。

## 📊 出力形式

### 文字起こし結果（Qwen3-ASR・デフォルト）

文節毎に改行された読みやすいテキスト：

```
こんにちは。
今日は文字起こしのテストをしています。
それでは、
始めましょう。
...
```

> Whisperエンジン（`--model kotoba-tech/kotoba-whisper-v2.2`）を選択した場合は、
> 30秒毎の `[MM:SS]` タイムスタンプ付き形式になります。

### メタデータ
- 処理時間
- 使用モデル
- 言語設定
- 文字数統計
- デバイス情報

## 🔍 トラブルシューティング

### よくある問題

#### 1. Google Drive認証エラー（WSL環境）

**エラー**: `could not locate runnable browser`

**原因**: WSL環境ではブラウザを自動起動できません。

**解決策**: 認証URLを手動でブラウザにコピーしてください。
```bash
# 実行すると認証URLが表示されます
./tc

# 表示されたURLをWindows側のブラウザで開いて認証
# リダイレクトされたURLをターミナルに貼り付け
```

#### 2. OAuth 2.0認証エラー

**エラー**: `Error 400: invalid_request` または `Missing required parameter: redirect_uri`

**原因**: Google Cloud Consoleの設定が不足しています。

**解決策**:
1. OAuth同意画面を「本番環境」に設定
   - https://console.cloud.google.com/apis/credentials/consent
2. または「テストユーザー」に自分のメールアドレスを追加

#### 3. numba初期化エラー

**エラー**: `initialization of _internal failed without raising an exception`

**原因**: `resampy`パッケージの依存関係の問題です。

**解決策**: このエラーはv2025.11.21で修正済み（`librosa`に切り替え）
```bash
# 念のため依存関係を再同期(pyproject.toml/uv.lockが情報源)
uv sync
```

#### 4. CUDA out of memory
```bash
# CPUモードで実行
./tc --device cpu
```

#### 5. Hugging Face認証エラー
```bash
# トークンの確認
cat .env

# 形式の確認（HUGGINGFACE_TOKEN=hf_xxx）
```

#### 6. ModuleNotFoundError: No module named 'googleapiclient'
```bash
# 依存関係を再同期(pyproject.toml/uv.lockが情報源)
uv sync
```

### ログ確認

```bash
# 詳細ログの確認
tail -f logs/transcribe.log

# エラーログの検索
grep -i error logs/transcribe.log
```

## 🧪 開発・デバッグ

## 🧪 E2Eテスト

### ローカルE2E（推奨）

ドライラン（依存最小で入口確認）:
```bash
./scripts/e2e_local.sh
```

フル実行（モデルがキャッシュ済みの場合）:
```bash
E2E_MODE=full ./scripts/e2e_local.sh
```

### pytestでドライラン確認

```bash
uv run pytest tests/test_e2e_dry_run.py -v
```

このテストは `tc` に `--dry-run` オプションを実装したことで復旧済みです。
ローカルの音声ファイルのみを使い、GPU/ネットワークを一切使用せずに
ランチャー起動確認（設定読み込み・入力解決）を行います。

### 依存関係管理

```bash
# パッケージの追加
uv pip install package_name

# 依存関係の同期 (uv が pyproject.toml/uv.lock を情報源とする)
uv sync
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

### v2025.11.21 - WSL環境対応とOAuth認証改善
- 🔧 **WSL環境での認証フロー改善**
  - `OAUTHLIB_INSECURE_TRANSPORT`環境変数の設定
  - 手動認証フロー（localhostリダイレクト対応）
  - WSL環境でのブラウザ起動問題を解決
- 🎯 **音声処理エンジンの安定化**
  - `resampy`から`librosa`への切り替え
  - `numba`初期化エラーを回避
  - 音声リサンプリングのフォールバック機能強化
- 📦 **依存関係の明確化**
  - Google API関連パッケージの追加
  - scipy、librosa、soundfileの明示的インストール
  - インストール手順の詳細化
- 📚 **ドキュメント大幅改善**
  - Google Cloud Console設定手順の追加
  - OAuth 2.0認証の詳細ガイド
  - WSL特有の問題と解決策の追加
  - トラブルシューティングの充実

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
