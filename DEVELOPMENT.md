# 開発者ガイド 🛠️

音声文字起こしシステム（transcribe_audio）の開発に参加するための包括的なガイドです。

## 📋 目次

- [開発環境セットアップ](#-開発環境セットアップ)
- [プロジェクト構造](#-プロジェクト構造)
- [開発フロー](#-開発フロー)
- [コード品質管理](#-コード品質管理)
- [テスト実行](#-テスト実行)
- [OOP設計パターン](#-oop設計パターン)
- [デバッグ方法](#-デバッグ方法)
- [パフォーマンス最適化](#-パフォーマンス最適化)
- [トラブルシューティング](#-トラブルシューティング)

## 🚀 開発環境セットアップ

### 1. 必要なツール
```bash
# システム要件
Python 3.12+
uv (依存関係管理。必須。https://docs.astral.sh/uv/)
Git
CUDA Toolkit (GPU使用時)
```

テストの実行に GPU・ネットワーク・Google Drive 認証は不要です(`CUDA_VISIBLE_DEVICES=""` の状態で
`tests/test_docs_consistency.py` 以外が通ることを 2026-10-04 に確認)。
`.env` は任意です(`tc` が `load_dotenv()` を例外処理付きで呼びます。`.gitignore` 済み)。

### 2. プロジェクトクローン・環境構築
```bash
# リポジトリクローン
git clone https://github.com/abem/tc.git
cd tc

# 依存関係インストール (uv が .venv を自動作成、dev group も含む)
uv sync
```

### 3. エディタ設定推奨

**VS Code設定例** (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "./.venv/bin/python"
}
```

lint は `uv run ruff check .` で実行する(整形ツール・型チェッカーは導入していないため、保存時整形は設定しない)。

## 🏗️ プロジェクト構造

> ⚠️ 本セクションは以前 `patterns/`(Factory/Strategy/Observer等のOOPパターン実装)を
> 前提に書かれていたが、`patterns/` は大規模リファクタリング(コミット b5f20f8)で
> 削除済み。現在の実装(core/・handlers/構成、モデル名パターンマッチによる
> エンジン自動選択)に合わせて是正した。

### コアモジュール
```
tc/
├── tc                          # メインCLIコマンド(uv run 経由)
├── transcribe.py               # インタラクティブ版CLI(uv run 経由)
├── transcribe                  # transcribe.py を起動するシェルラッパー
├── webui.py                    # Streamlit の WebUI(進捗バー・経過時間・履歴)
├── suppress_warnings.py        # 警告抑制(各エントリポイントが import する)
├── config/
│   └── config.yaml            # 設定ファイル
├── core/                      # コア機能(統一アーキテクチャ)
│   ├── config.py              # TranscriptionConfig/SystemConfig/UnifiedConfig
│   ├── logging.py             # 統一ロガー・setup_logging()
│   ├── transcription_interface.py  # UnifiedTranscriber(ファサード。既存の import 名を再 export)
│   ├── engine_factory.py      # create_engine(モデル名でエンジンを選ぶ)
│   ├── transcription_types.py # TranscriptionSegment / TranscriptionResult / TranscriptionEngine
│   ├── qwen3_engine.py        # Qwen3ASREngine(+ qwen3_chunking.py / qwen3_text.py)
│   ├── whisper_engine.py      # WhisperTranscriptionEngine(+ whisper_text.py)
│   ├── nemotron_engine.py     # NemotronSubprocessEngine(Nemotron系モデル用)
│   ├── history.py             # 変換履歴 DB の検索・件数・削除
│   ├── housekeeping.py        # cleanup_old_entries(WebUI の uploads / queue_downloads の期限切れ削除)
│   ├── progress.py            # 進捗通知(ProgressMessage / emit_progress / throttled / parse_ytdlp_progress)
│   ├── model_manager.py       # モデルキャッシュ管理(Whisper 系)
│   ├── cli_common.py          # CLI共通ヘルパー(出力ファイル名など)
│   ├── cli_workflow.py        # 入力解決(resolve_input_audio)・finalize_transcription(保存・アップロード・履歴・一時音声の削除)
│   ├── webui_workflow.py      # WebUI(webui.py)用ワークフロー(ジョブキュー・進捗の反映)
│   └── utils.py               # URL検出(YouTube/X/GDrive)・デバイス解決・context_hints読込・sanitize_upload_filename・one_line
├── handlers/                  # 外部サービスハンドラー
│   ├── gdrive.py              # GDriveClient
│   ├── gdrive_auth.py         # get_drive_service(OAuth 認証)
│   └── youtube.py             # YouTubeClient(yt-dlp経由。YouTube/X両対応)・find_yt_dlp
├── scripts/                   # 運用・検査スクリプト(下記)
├── tests/                     # テストファイル
├── docs/spec/00-project-spec.md  # 利用者に見える挙動の正本
├── output/                    # 出力ファイル(.gitignore)
├── logs/                      # ログファイル(.gitignore)
├── .env                       # 環境変数(任意。.gitignore)
├── credentials.json           # Google Drive認証(.gitignore。コミットしない)
└── token.pickle               # Drive の認可トークン(.gitignore。コミットしない)
```

### 補助関数と集約点

- **`core.cli_workflow.finalize_transcription`**: 保存 → アップロード(youtube / gdrive のみ。X は対象外)→ 履歴 →
  一時音声の削除を行う集約点。`tc`・`transcribe.py`・`webui.py` が共用します。文字起こし自体が失敗したときは、
  呼び出し側が `cleanup_input_audio(resolution)` を呼びます。保存形式は `save_transcription_text` / `format_transcript_text`
  (`timestamps_included` が真で segments があるときだけ `[MM:SS] ` を付ける)
- **`core.utils.sanitize_upload_filename`**: WebUI のアップロード名を無害化(最大 200 文字)。保存先は
  `output/uploads/<一意>/<サニタイズ済み名>`(同名でも上書きしない)
- **`core.utils.one_line`**: ログ・ラベルを 1 行にする(エラー文は 1000 文字まで)
- **`handlers.youtube.find_yt_dlp`**: yt-dlp の探索(PATH → 現在の Python と同じ `bin/` → `.venv/bin/yt-dlp`)。
  見つからなければ `YtDlpNotFoundError`(`ValueError` のサブクラス。自動 pip install はせず `uv sync` を案内)。
  yt-dlp の呼び出しにはタイムアウトがある(`--socket-timeout 30`、メタデータ取得 60 秒、出力が 300 秒途絶えると中断)
- **`core.logging.setup_logging`**: `tc`・`transcribe.py`・`webui.py` の `main()` が呼びます(`core` は import しただけでは
  ログを設定しません。pytest 中は `logs/transcription_test.log`)

保存形式・一時ファイル・yt-dlp の挙動の正本は [docs/spec/00-project-spec.md](docs/spec/00-project-spec.md) です。

### エンジン自動選択の仕組み(旧patterns/の代替)

`patterns/` のFactory/Strategyパターンは削除され、エンジン選択はモデル名の
パターンマッチのみで行われるシンプルな実装に置き換わっている:

```python
# core/engine_factory.py (create_engine。UnifiedTranscriber.__init__ から呼ばれる)
if is_nemotron_model(config.model):
    return NemotronSubprocessEngine(config)
if Qwen3ASREngine.is_qwen3_model(config.model):
    return Qwen3ASREngine(config)
return WhisperTranscriptionEngine(config)
```

言語(`whisper.language`)は `Qwen3ASREngine.transcribe()` 内の `lang_map` で `Qwen3-ASR` の
言語指定へ変換されるのみで、モデル切替とは無関係(詳細は `docs/user-guides/language_support_guide.md`)。

### テスト・品質管理
```
tests/
├── conftest.py
├── fixtures/
├── test_core_*.py             # core/ 配下(config・logging・utils・history・housekeeping・progress・
│                              #   transcription_interface・cli_workflow・cli_finalize・nemotron・webui_workflow・
│                              #   import_no_side_effects ほか)
├── test_handlers_*.py         # handlers/(gdrive・gdrive_auth・youtube・youtube_detection・youtube_download)
├── test_tc_*.py               # tc CLI(main フロー・結果保存)
├── test_cli_unified_behavior.py   # tc / transcribe.py の共通挙動
├── test_transcribe_loader.py  # transcribe.py ローダー
├── test_webui_*.py            # webui.py(進捗表示・アップロード名・履歴の削除・キュー表示など)
├── test_scripts_*.py          # scripts/ 配下(Nemotron 比較)
├── test_release_script.py     # scripts/release_dev_main.sh
├── test_error_logs_one_line.py    # エラーログが 1 行であること
├── test_docs_consistency.py   # 文書の整合検査(リンク先・パス・削除済みモジュール名・仕様書の数値)
└── test_e2e_dry_run.py        # tc --dry-run による起動確認

.github/workflows/
└── ci.yml                     # uv + ruff + pytest(push と pull request で実行)

pyproject.toml                 # プロジェクト設定・依存関係・pytest設定([tool.pytest.ini_options])
uv.lock                        # 依存関係ロックファイル
```

### 設定・ドキュメント
```
config/
└── config.yaml                 # システム設定

docs/
├── user-guides/                # 利用者向けガイド(TUTORIAL/TROUBLESHOOTING/configuration等)
├── spec/                       # 利用者に見える挙動の仕様書(00-project-spec.md が正本)
├── system-docs/                # システム概要・運用手順(system_overview.md、release_operations.md、webui_architecture.md)
├── developer-guides/
├── historical-records/         # 過去の経緯・是正記録
├── feature/
├── figures/                    # 文書の図
├── obsolete/
└── README.md                   # docs の索引

scripts/
├── gpu_monitor.py              # GPU監視
├── simple_gpu_monitor.sh       # GPU監視(簡易版)
├── e2e_local.sh                # E2Eテスト(ローカル実行)
├── release_dev_main.sh         # feature → dev → main の統合・push・WebUI 再起動
├── check_figures.sh            # docs/figures/*.mmd の機械検査と SVG の書き戻し
├── compare_nemotron_baseline.py    # Nemotron回帰ゲート比較
├── nemotron_infer.py           # Nemotron推論(NemotronSubprocessEngine からサブプロセス起動される)
├── setup_nemotron_venv.sh      # Nemotron用の隔離venv構築
└── repro_webui_concurrent_enqueue.py  # WebUI同時投入の再現スクリプト
```

## 🔄 開発フロー

### 1. 新機能開発
```bash
# ブランチ作成
git checkout -b feature/new-awesome-feature

# 開発作業
# ... コーディング ...

# テスト・lint実行
uv run python -m pytest tests -q
uv run ruff check .

# コミット(変更したファイルを指定してステージングする)
git add <変更したファイル>
git commit -m "feat: add awesome new feature"

# プッシュ
git push origin feature/new-awesome-feature
```

### 統合(feature → dev → main)と本番

- 更新の順序は **feature → dev → main**。dev と main を feature から個別に更新してはいけない(`CLAUDE.md`)
- WebUI は systemd のユーザーサービス `tc-webui.service` が `/home/abem/Projects/tc-prod`(**dev をチェックアウト**)で
  `uv run streamlit run webui.py --server.headless true --server.port 8501 --server.fileWatcherType none` を実行しています。
  **dev への統合 = 本番コードの更新**です
- 統合・push・WebUI 再起動は `scripts/release_dev_main.sh` で行います(`--dry-run` で確認だけ、`--no-restart`、`--force-restart`)。
  前提が崩れていれば何も変更せずに止まります。main の更新はユーザーの明示的な指示があるときだけです
- 使い方・止まる条件・復旧の詳細は [docs/system-docs/release_operations.md](docs/system-docs/release_operations.md) を参照

### 2. バグ修正
```bash
# バグ修正ブランチ
git checkout -b fix/issue-123

# 修正作業
# ... バグ修正 ...

# リグレッションテスト
uv run python -m pytest tests -q

# コミット
git commit -m "fix: resolve issue #123 with audio processing"
```

### 3. プルリクエスト作成
1. GitHub上でPRを作成
2. CI/CDの自動チェック待機
3. コードレビュー対応
4. マージ

## 🔍 コード品質管理

### lint（ruff）
```bash
# 品質チェック
uv run ruff check .
```

自動整形ツール(formatter)・インポート整理ツール・型チェッカーは導入していない。
ruff の規則は pyflakes 相当の `F`(未使用 import・未定義名など)のみ。

### 設定ファイル（pyproject.toml）
```toml
[tool.ruff]
target-version = "py312"
extend-exclude = ["backup", "WORK_*"]

[tool.ruff.lint]
select = ["F"]
```

## 🧪 テスト実行

### 基本テスト
```bash
# 全テスト実行 (uv 経由)
uv run python -m pytest tests -q

# カバレッジ付きテスト
uv run python -m pytest tests --cov=core --cov=handlers -q

# 特定テストのみ
uv run python -m pytest tests/test_core_config.py -v
```

### テストカテゴリ

**core/ のテスト** (`tests/test_core_*.py`):
- 設定クラス(`test_core_config.py`)・ロガー(`test_core_logging.py`)・ユーティリティ(`test_core_utils.py`)
- 転写インターフェース・Nemotronエンジン(`test_core_transcription_interface*.py`、`test_core_nemotron_*.py`)
- CLI・WebUIワークフロー(`test_core_cli_workflow_*.py`、`test_core_webui_workflow_*.py`)

**handlers/ のテスト** (`tests/test_handlers_gdrive.py`、`tests/test_handlers_youtube.py`)

**CLI・WebUI のテスト** (`tests/test_tc_*.py`、`tests/test_transcribe_loader.py`、`tests/test_webui_*.py`)

**起動確認テスト** (`tests/test_e2e_dry_run.py`): `tc --dry-run` による起動確認

### テスト作成ガイドライン
```python
import pytest
from unittest.mock import Mock, patch

def test_function_name():
    """テスト内容の説明"""
    # Arrange
    expected_result = "expected"
    
    # Act
    result = function_to_test()
    
    # Assert
    assert result == expected_result

@patch('module.external_dependency')
def test_with_mock(mock_dependency):
    """外部依存をモックするテスト"""
    mock_dependency.return_value = "mocked_value"
    
    result = function_using_dependency()
    
    assert result == "expected_with_mock"
    mock_dependency.assert_called_once()
```

## 🏗️ OOP設計パターン

> ⚠️ 以前ここに記載していたFactory/Strategy/Command/Observerパターン(`patterns/`
> モジュール)は削除済み。現在の実装は以下のシンプルな構成のみ。

### Strategy相当: TranscriptionEngine(抽象基底クラス)

`core/transcription_types.py` の `TranscriptionEngine(ABC)` を
`Qwen3ASREngine`・`WhisperTranscriptionEngine`・`NemotronSubprocessEngine` が実装する、素朴な継承ベースの
Strategyパターン。`patterns/strategies.py` のような専用レジストリ・登録機構は無い。

```python
class TranscriptionEngine(ABC):
    """Abstract base class for all transcription engines."""

    @abstractmethod
    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult: ...

    @abstractmethod
    def get_engine_name(self) -> str: ...
```

### Factory相当: エンジン選択ロジック

専用のFactoryクラスは無く、`core/engine_factory.py` の関数 `create_engine`(前掲「エンジン自動選択の
仕組み」参照。`UnifiedTranscriber.__init__` から呼ばれる)がモデル名を見て `if/elif/else` で直接インスタンス化する。

### Command Pattern / Observer Pattern

`AudioProcessingPipeline`・`CommandInvoker`・`setup_standard_monitoring` 等は
削除済みで、現在の実装に対応物は無い。進捗通知は `core/progress.py` に集約されている
(次節「進捗表示・ログのカスタマイズ」)。

## 🐛 デバッグ方法

### ログレベル設定
```python
import logging

# デバッグログ有効化
logging.basicConfig(level=logging.DEBUG)

# 特定モジュールのログ制御(UnifiedTranscriber は自身のクラス名でロガーを取得する)
logger = logging.getLogger('UnifiedTranscriber')
logger.setLevel(logging.DEBUG)
```

### 実行時の確認
```bash
# 起動確認用(--dry-run: 設定読み込み・入力解決までを行い、実際の文字起こしは行わない)
./tc --dry-run "<入力(URLまたはローカルファイルパス)>"

# CPU使用でのデバッグ（GPU問題回避）
./tc --device cpu

# ログはコンソールと logs/transcription.log に出力される
tail -f logs/transcription.log
```

### GPU監視
```bash
# GPU使用状況監視
./scripts/simple_gpu_monitor.sh

# nvidia-smi監視
watch -n 1 nvidia-smi
```

### Python デバッガー
```python
import pdb

def problematic_function():
    # デバッグポイント設定
    pdb.set_trace()
    
    # 処理継続...
    result = complex_operation()
    return result
```

## ⚡ パフォーマンス最適化

### GPU・メモリ設定

`TranscriptionConfig` が持つのは `model` / `language` / `device` / `context` / `include_timestamps` の
5 項目だけです。バッチサイズ・キャッシュ・非同期処理などの調整用フィールドは、どのエンジンも読まなかったため削除しました。
実行時のデバイスは `device` で選びます。

### プロファイリング
```bash
# パフォーマンス測定 (tc ランチャーは uv run 経由)
uv run python -m cProfile -o profile.stats tc
```

## 🛠️ 新機能開発ガイド

> ⚠️ 以前ここに記載していた例(`patterns/strategies.py`・`patterns/factories.py`・
> `patterns/observers.py`・`BatchSizeStrategy`・`LanguageAwareModelSelector`・
> `WhisperTranscriber`・`Observer`等)はいずれも削除済みモジュール/クラスを
> 前提にしていた。現在の実装(core/transcription_types.py 等)に即して是正した。

### 1. 新しいTranscriptionEngine追加

```python
# core/ に新しいモジュールとして追加し、core/engine_factory.py の create_engine に判定を足す

class MyCustomEngine(TranscriptionEngine):
    def get_engine_name(self) -> str:
        return "my-custom-engine"

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        ...

# core/engine_factory.py の create_engine のモデル名判定にも分岐を追加する
# (現状は is_nemotron_model() / Qwen3ASREngine.is_qwen3_model() の if/elif/else)
```

### 2. 新しい言語サポート追加

言語ごとに専用のトランスクライバーを作るのではなく、`whisper.language` の値を
`transcribe()` 内の `lang_map`(`core/qwen3_engine.py`)に追加するだけでよい:

```python
lang_map = {"ja": "Japanese", "en": "English", "zh": "Chinese"}  # 追加例
```

WhisperTranscriptionEngine 側は `config.language` をそのまま渡すため変換不要
（対応言語はモデル自体の対応範囲に依存する）。

### 3. 進捗表示・ログのカスタマイズ

専用のObserver登録機構は無く、進捗通知は `core/progress.py` に集約されている。コールバックは `Callable[[str], None]` で、
進捗率を持つ通知は `ProgressMessage(text, fraction)`(`str` のサブクラス。`fraction` は 0.0〜1.0、`None` は率が不明)。

- `emit_progress(callback, text, fraction=None)`: 通知する。コールバックの例外で本処理を止めない
- `throttled(printer, steps=10)`: CLI 用。率つきの通知は `1/steps` 進むごとに 1 回だけ `printer` へ渡す
- `parse_ytdlp_progress(line)`: yt-dlp の進捗行から (進捗率, ETA) を取り出す

利用側の違い:

- `tc`: `transcribe(audio_path, progress_callback=lambda message: print(message))` を渡し、入力解決の `on_status` には `throttled(print)`
- `transcribe.py`: 入力解決の `on_status` に `throttled(console.print)` を渡す。`transcribe()` には `progress_callback` を渡さない
- WebUI: `fraction` を進捗バーに使う(ダウンロードの割合、Qwen3-ASR の 300 秒超の分割処理のチャンク進捗、Whisper の 30 秒チャンク進捗)。
  経過・残り時間は `core/webui_workflow.py` の `format_elapsed` / `estimate_remaining`(進捗 3% 未満では残りを出さない)。
  Nemotron と短い音声は経過時間のみ

ログの出力先や形式を変えるときは `core.logging.UnifiedLogger.configure(...)` を使う。

## 🔧 設定カスタマイズ

### config/config.yaml編集
```yaml
whisper:
  model: "your-custom-model"    # 使用するモデル(モデル名でエンジンが自動選択される)
  language: null                # 既定は null(自動判定)。"ja" / "en" などを指定できる
  device: "cuda"
  context_file: "config/context_hints.txt"  # 固有名詞・専門用語のヒント(Qwen3-ASR用)
  include_timestamps: false     # タイムスタンプ付与(Qwen3-ASR のみ。ForcedAligner を追加でロードする)
```

設定の読み込み・既定値は `core/config.py` の `UnifiedConfig` を使う。キーの意味は `docs/user-guides/configuration.md` を参照。

## 📚 APIドキュメント生成

### docstring形式
```python
def transcribe(self, audio_path: str, progress_callback=None, **kwargs) -> TranscriptionResult:
    """
    音声ファイルを文字起こしする
    
    Args:
        audio_path (str): 音声ファイルのパス
        progress_callback: 進捗メッセージを受け取るコールバック(省略可)
        **kwargs: 各エンジンへ渡す追加オプション
    
    Returns:
        TranscriptionResult: 文字起こし結果
            - text (str): 文字起こしテキスト
            - segments (List[TranscriptionSegment]): セグメント情報
            - language / duration / processing_time / model_name
    
    Raises:
        RuntimeError: 音声処理エラー
        ValueError: 入力検証エラー
    
    Example:
        >>> transcriber = UnifiedTranscriber(transcription_config)
        >>> result = transcriber.transcribe('audio.wav')
        >>> print(result.text)
    """
    pass
```

## 🚨 トラブルシューティング

### よくある開発問題

**Q: インポートエラーが発生する**
```bash
# uv.lock のとおりに依存関係をそろえる (.venv は削除しない)
uv sync
# それでも直らない場合は、パッケージを入れ直す
uv sync --reinstall
```

**Q: テストが失敗する**
```bash
# キャッシュクリア
rm -rf .pytest_cache/ __pycache__/

# 依存関係チェック
uv pip check

# 個別テスト実行
uv run python -m pytest tests/test_core_config.py -v -s
```

**Q: GPU out of memory**
```bash
# メモリ確認
nvidia-smi

# CPU実行に切り替え
export CUDA_VISIBLE_DEVICES=""
./tc --device cpu
```

### デバッグのベストプラクティス

1. **段階的デバッグ**: 小さな入力から始める
2. **ログ活用**: `logs/transcription.log` を確認
3. **分離テスト**: 機能別に個別テスト
4. **環境確認**: CUDA, Python, パッケージバージョン
5. **リソース監視**: GPU/CPU/メモリ使用状況

## 🤝 コントリビューション

### プルリクエストガイドライン

1. **明確なタイトル**: 変更内容が分かるタイトル
2. **詳細説明**: 変更理由と影響範囲を記載
3. **テスト追加**: 新機能には対応テストを追加
4. **ドキュメント更新**: 必要に応じてREADME.md等を更新
5. **品質チェック**: CI/CDが通過することを確認

### コミットメッセージ規約
```
feat: 新機能追加
fix: バグ修正
docs: ドキュメント更新
style: フォーマット修正（機能に影響なし）
refactor: リファクタリング
test: テスト追加・修正
chore: その他の変更
```

### レビュープロセス
1. 自動CI/CDチェック
2. コードレビュー
3. テストカバレッジ確認
4. ドキュメント整合性確認
5. マージ

---

## 📞 サポート

- **GitHub Issues**: バグ報告・機能要望
- **GitHub Discussions**: 一般的な質問・議論
- **開発者Discord**: リアルタイム相談（準備中）

開発に参加いただき、ありがとうございます！🎉