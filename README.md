# 音声文字起こしシステム（tc） 🎙️

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![UV Package Manager](https://img.shields.io/badge/package--manager-uv-orange.svg)](https://github.com/astral-sh/uv)
[![Qwen3-ASR](https://img.shields.io/badge/model-Qwen3--ASR--1.7B-green.svg)](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ 概要

**シンプルで高精度な日本語音声文字起こしツール**

- **🏆 最高精度** - Qwen3-ASR-1.7Bによる2026年ベンチマークトップクラスの日本語文字起こし（デフォルト）
- **⚡ ワンコマンド実行** - `./tc`だけでconfig.yamlから設定を自動読み込み、仮想環境も自動構築
- **🎛️ 3つの文字起こしエンジン** - Qwen3-ASR（既定）・Whisper・Nemotron をモデル名で自動切替
- **☁️ 入力はローカル・Google Drive・YouTube・X（旧Twitter）** - Google Drive / YouTube の音声は結果を自動アップロード
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
  device: cuda  # または cpu、auto
```

### 4. 実行

```bash
# シンプル実行（推奨）
./tc

# 完了！結果は output/ フォルダ（output/YYYYMMDD_HHMMSS_transcription.txt）に保存されます。
# 入力が Google Drive / YouTube の場合は Google Drive にもアップロードされます
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

# YouTube / X（旧Twitter）の動画URLを処理
./tc <動画のURL>
```

> X の動画URLは `https://x.com/<ユーザー>/status/<数字>`（`twitter.com` も可）の形式です。
> 結果の Google Drive へのアップロードは、入力が Google Drive / YouTube の場合だけ行われます
> （X とローカルファイルは `output/` への保存のみ）。

### オプション

```bash
# アップロードをスキップ
./tc --no-upload

# 出力ディレクトリを指定
./tc --output-dir results

# モデルを変更（従来のWhisperエンジンに切り替え）
./tc --model kotoba-tech/kotoba-whisper-v2.2

# 言語を指定（config.yaml の whisper.language を上書き）
./tc --language ja

# デバイスを指定（cuda / cpu / auto）
./tc --device cpu

# アップロード先の Google Drive フォルダIDを指定
./tc --folder-id <フォルダID>

# 設定読み込み・入力解決までで終了（文字起こしはしない。起動確認用）
./tc --dry-run

# ヘルプ表示
./tc --help
```

Rich 画面で対話的に選びたい場合は `./transcribe`（`transcribe.py` を起動するシェルスクリプト）を使います。
指定できるのは、入力（位置引数）、`--profile`（`-p`、プロファイル番号。`1` 日本語（高速）・`3` English・
`5` 日本語（最高精度・Qwen3-ASR）・`6` カスタム設定）、`--language`（`-l`、`ja` / `en`）、`--folder-id` です。

### WebUI（Streamlitプロトタイプ）

CLI（`./tc`）に加えて、ブラウザから操作できるWebUI（Streamlitプロトタイプ）も利用できます。

**起動方法**:

```bash
uv run streamlit run webui.py --server.headless true --server.port 8501
```

systemdによる常駐化・自動起動を含む内部構成の詳細は
[`docs/system-docs/webui_architecture.md`](docs/system-docs/webui_architecture.md) を参照してください。

**機能概要**:

- **文字起こしタブ**: YouTube / Google DriveのURL入力（X の動画URLも入力できます）、またはローカルファイルの
  アップロードから文字起こしを実行できます。モデル（Qwen3-ASR・kotoba-whisper・whisper-large-v3・Nemotron）・
  デバイス・言語の選択、タイムスタンプ付与（ForcedAligner使用、Nemotron では選べません）、
  認識ヒント（固有名詞・専門用語のヒント指定）に対応しています。
- **ジョブキュー**: 複数の入力を投入すると、現在の処理完了後に自動で次の処理を開始します
  （同時並列実行は行わず、逐次処理のみ対応）。待機件数・処理中の対象・完了済み一覧をUI上で
  確認できます。
- **履歴タブ**: 過去の変換履歴（`output/history.db`、SQLite）を日付で絞り込み、キーワード（3文字以上）で
  検索して閲覧できます。古い履歴の一括削除もできます。

## 🔧 設定

### config/config.yaml

```yaml
gdrive:
  url: "処理対象のGoogle Drive URL"      # ./tc を引数なしで実行したときの入力
  upload_folder_id: "アップロード先フォルダID"  # 省略時は元ファイルと同じフォルダ（--folder-id で上書き可）

whisper:
  model: Qwen/Qwen3-ASR-1.7B   # デフォルト: 最高精度（2026年ベンチマークトップ）
  language: null                # 既定は自動判定（ja/en等を指定すると強制）
  device: cuda                  # cuda / cpu / auto
  context_file: "config/context_hints.txt"  # 認識ヒント（Qwen3-ASR用、任意）
  include_timestamps: false     # true で行頭に [MM:SS] を付与（Qwen3-ASR専用、後述）
```

- `whisper.model` は `whisper:` の下にありますが、Qwen3-ASR・Nemotron を含む全モデル共通の設定です。
  モデル名で使うエンジンが決まります（「サポートモデル」参照）。
- `whisper.context_file`: 1行1語彙、`#` 始まりはコメントです。書式は `config/context_hints.txt.sample` を
  参照してください。ファイルが無い・空の場合はヒントなしで動作します。
  認識ヒントを使うのは Qwen3-ASR だけです（Whisper・Nemotron は無視します）。
  音声が長くてチャンク分割される場合、ヒントは最初のチャンクにだけ適用されます。
- `whisper.include_timestamps`: Qwen3-ASR 専用のオプトイン機能です。詳細は
  [`docs/feature/timestamp_feature.md`](docs/feature/timestamp_feature.md) を参照してください。

### 環境変数と .env ファイル

`tc` は起動時にプロジェクト直下の `.env` があれば読み込みます（`python-dotenv`）。
現行のコードが必須とする環境変数はありません。

## 🏗️ アーキテクチャ

### プロジェクト構造

```
tc/
├── tc                          # メインCLIコマンド
├── transcribe                  # transcribe.py を起動するシェルスクリプト
├── transcribe.py               # Rich UI対話型CLI
├── webui.py                    # WebUI（Streamlit）
├── suppress_warnings.py        # 警告抑制
├── config/
│   ├── config.yaml            # 設定ファイル
│   └── context_hints.txt.sample  # 認識ヒントの書式サンプル
├── core/                      # コア機能
│   ├── config.py              # 統一設定管理
│   ├── logging.py             # 統一ロガー
│   ├── transcription_interface.py  # 文字起こしエンジン（Qwen3-ASR / Whisper）と UnifiedTranscriber
│   ├── nemotron_engine.py     # Nemotron エンジン（隔離venvのサブプロセス）
│   ├── model_manager.py       # モデルキャッシュ管理（Whisper用）
│   ├── cli_common.py          # CLI共通ヘルパー
│   ├── cli_workflow.py        # 入力解決・アップロード・変換履歴
│   ├── webui_workflow.py      # WebUIのジョブキュー
│   └── utils.py               # URL検出・デバイス解決
├── handlers/                  # 外部サービスハンドラー
│   ├── gdrive.py              # Google Drive クライアント
│   ├── gdrive_auth.py         # Google Drive の OAuth 認証（get_drive_service）
│   └── youtube.py             # YouTube / X 音声抽出（yt-dlp）
├── scripts/                   # 補助スクリプト（E2E、Nemotron 用 venv 構築など）
├── tests/                     # テストファイル
├── output/                    # 出力ファイル（履歴DB output/history.db を含む）
├── logs/                      # ログファイル
├── venv-nemotron/             # Nemotron 専用の仮想環境（任意、後述）
├── .env                       # 環境変数（任意）
└── credentials.json           # Google Drive認証
```

### 主要機能

1. **統一設定管理** (`core/config.py`)
   - YAML設定の読み込み
   - 環境変数との統合
   - デフォルト値の管理

2. **文字起こしエンジン** (`core/transcription_interface.py`)
   - Qwen3-ASR / Whisper / Nemotron の3エンジン（モデル名で自動切替。Nemotron は `core/nemotron_engine.py`）
   - 音声前処理
   - Qwen3-ASR は長音声を5分単位でチャンク分割して処理（Nemotron は350秒を超えるとストリーミング推論で処理）
   - Qwen3-ASR は文節改行フォーマット

3. **Google Drive連携** (`handlers/gdrive.py`)
   - ファイルダウンロード
   - 結果アップロード
   - 権限管理

4. **YouTube / X 音声抽出** (`handlers/youtube.py`)
   - YouTube・X の動画から音声抽出（yt-dlp）
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

### Nemotron（専用の仮想環境が必要）
- **nvidia/nemotron-3.5-asr-streaming-0.6b**
  - `./tc --model nvidia/nemotron-3.5-asr-streaming-0.6b` で使えます
  - 本体の `.venv`（`qwen-asr` が `transformers<5` を要求）とは依存関係が両立しないため、
    専用の仮想環境 `venv-nemotron/` のPythonをサブプロセスとして起動して推論します
  - 事前に `./scripts/setup_nemotron_venv.sh` で `venv-nemotron/` を作成してください
    （`venv-nemotron/` が既にある場合は何もしません）。未作成のまま実行すると、
    未構築を知らせるエラーで停止します
  - 認識ヒントとタイムスタンプ付与には対応していません。出力は1つのテキストです
  - 実際に読み込まれるモデルは `scripts/nemotron_infer.py` に固定されており、
    モデル名は `nemotron` を含むかどうかでエンジンを選ぶためだけに使われます

> モデル名に `nemotron` を含む場合は NemotronSubprocessEngine、`qwen3-asr`（または `qwen3_asr`）を含む場合は
> Qwen3ASREngine、それ以外は WhisperTranscriptionEngine が自動選択されます。
> 既定のモデルは `config/config.yaml` の `whisper.model` です（現在 `Qwen/Qwen3-ASR-1.7B`）。

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
> Qwen3-ASR でも `whisper.include_timestamps: true`（`tc` が読みます）にすると、各行の行頭に
> `[MM:SS]` が付きます（[タイムスタンプ機能](docs/feature/timestamp_feature.md)）。
> Nemotron の出力はタイムスタンプなしの1つのテキストです。

ファイル名は `output/YYYYMMDD_HHMMSS_transcription.txt` です（`--output-dir` で出力先を変更できます）。

### 変換履歴（メタデータ）

`tc`・`transcribe.py`・WebUI は、変換のたびに `output/history.db`（SQLite）へ次の項目を記録します
（記録に失敗しても文字起こし自体は失敗として扱いません）。
- 処理日時・入力の種別と元のURL/パス・タイトル
- 使用モデル・デバイス・言語
- 文字数・音声長・処理時間
- チャンク失敗数・反復検出数
- タイムスタンプ付与・認識ヒント使用の有無
- 結果テキスト・出力ファイルのパス・Google Drive の URL

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

#### 5. ModuleNotFoundError: No module named 'googleapiclient'
```bash
# 依存関係を再同期(pyproject.toml/uv.lockが情報源)
uv sync
```

#### 6. Nemotron を指定したのに「Nemotron隔離venvが未構築です」で止まる
```bash
# 専用の仮想環境 venv-nemotron/ を作成
./scripts/setup_nemotron_venv.sh
```

### ログ確認

```bash
# 詳細ログの確認
tail -f logs/transcription.log

# エラーログの検索
grep -i error logs/transcription.log
```

## 🧪 開発・デバッグ

### テスト

```bash
uv run pytest
```

### E2Eテスト

#### ローカルE2E（推奨）

ドライラン（依存最小で入口確認）:
```bash
./scripts/e2e_local.sh
```

フル実行（モデルがキャッシュ済みの場合）:
```bash
E2E_MODE=full ./scripts/e2e_local.sh
```

#### pytestでドライラン確認

```bash
uv run pytest tests/test_e2e_dry_run.py -v
```

このテストは `tc --dry-run` を使い、ローカルの音声ファイルのみで、GPU/ネットワークを一切使用せずに
ランチャー起動確認（設定読み込み・入力解決）を行います。

### 依存関係管理

```bash
# パッケージの追加（pyproject.toml と uv.lock が更新される）
uv add <パッケージ名>

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
  - `OAUTHLIB_INSECURE_TRANSPORT`環境変数の設定（現在は再認証に入るときだけ設定）
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
