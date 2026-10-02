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
Git
CUDA Toolkit (GPU使用時)
```

### 2. プロジェクトクローン・環境構築
```bash
# リポジトリクローン
git clone https://github.com/yourusername/transcribe_audio.git
cd transcribe_audio

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
├── config/
│   └── config.yaml            # 設定ファイル
├── core/                      # コア機能(統一アーキテクチャ)
│   ├── config.py              # TranscriptionConfig/SystemConfig/UnifiedConfig
│   ├── logging.py             # 統一ロガー
│   ├── transcription_interface.py  # UnifiedTranscriber・Qwen3ASREngine・WhisperTranscriptionEngine
│   ├── nemotron_engine.py     # NemotronSubprocessEngine(Nemotron系モデル用)
│   ├── model_manager.py       # モデルキャッシュ管理
│   ├── cli_common.py          # CLI共通ヘルパー
│   ├── cli_workflow.py        # 入力解決(resolve_input_audio)・アップロードフロー
│   ├── webui_workflow.py      # WebUI(webui.py)用ワークフロー
│   └── utils.py               # URL検出(YouTube/X/GDrive)・デバイス解決・context_hints読込
├── handlers/                  # 外部サービスハンドラー
│   ├── gdrive.py              # GDriveClient
│   └── youtube.py             # YouTubeClient(yt-dlp経由。YouTube/X両対応)
├── tests/                     # テストファイル
├── output/                    # 出力ファイル
├── logs/                      # ログファイル
├── .env                       # 環境変数
└── credentials.json           # Google Drive認証
```

### エンジン自動選択の仕組み(旧patterns/の代替)

`patterns/` のFactory/Strategyパターンは削除され、エンジン選択はモデル名の
パターンマッチのみで行われるシンプルな実装に置き換わっている:

```python
# core/transcription_interface.py (UnifiedTranscriber.__init__)
from core.nemotron_engine import is_nemotron_model, NemotronSubprocessEngine
if is_nemotron_model(transcription_config.model):
    self.transcription_engine = NemotronSubprocessEngine(transcription_config)
elif Qwen3ASREngine.is_qwen3_model(transcription_config.model):
    self.transcription_engine = Qwen3ASREngine(transcription_config)
else:
    self.transcription_engine = WhisperTranscriptionEngine(transcription_config)
```

言語(`whisper.language`)は `Qwen3ASREngine.transcribe()` 内の `lang_map` で `Qwen3-ASR` の
言語指定へ変換されるのみで、モデル切替とは無関係(詳細は `docs/user-guides/language_support_guide.md`)。

### テスト・品質管理
```
tests/
├── conftest.py
├── fixtures/
├── test_core_*.py             # core/ 配下(config・logging・utils・transcription_interface・cli_workflow・nemotron・webui_workflow)
├── test_handlers_*.py         # handlers/(gdrive・youtube)
├── test_tc_*.py               # tc CLI(main フロー・結果保存)
├── test_transcribe_loader.py  # transcribe.py ローダー
├── test_webui_*.py            # webui.py
├── test_scripts_*.py          # scripts/ 配下
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
├── system-docs/                # 時点スナップショット(system_overview_2025.md等)
├── developer-guides/
├── historical-records/         # 過去の経緯・是正記録
├── feature/
├── kaizen/
└── obsolete/

scripts/
├── gpu_monitor.py              # GPU監視
├── simple_gpu_monitor.sh       # GPU監視(簡易版)
├── e2e_local.sh                # E2Eテスト(ローカル実行)
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

`core/transcription_interface.py` の `TranscriptionEngine(ABC)` を
`Qwen3ASREngine`・`WhisperTranscriptionEngine` が実装する、素朴な継承ベースの
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

専用のFactoryクラスは無く、`UnifiedTranscriber.__init__`(前掲「エンジン自動選択の
仕組み」参照)がモデル名を見て `if/elif/else` で直接インスタンス化する。

### Command Pattern / Observer Pattern

`AudioProcessingPipeline`・`CommandInvoker`・`setup_standard_monitoring` 等は
削除済みで、現在の実装に対応物は無い。進捗表示は `progress_callback`
（`tc`）や `Console.print`（`transcribe.py`）を直接呼ぶ単純なコールバック方式。

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
> 前提にしていた。現在の実装(core/transcription_interface.py)に即して是正した。

### 1. 新しいTranscriptionEngine追加

```python
# core/transcription_interface.py に追加

class MyCustomEngine(TranscriptionEngine):
    def get_engine_name(self) -> str:
        return "my-custom-engine"

    def transcribe(self, audio_path: str, **kwargs) -> TranscriptionResult:
        ...

# UnifiedTranscriber.__init__ のモデル名判定にも分岐を追加する
# (現状は is_nemotron_model() / Qwen3ASREngine.is_qwen3_model() の if/elif/else)
```

### 2. 新しい言語サポート追加

言語ごとに専用のトランスクライバーを作るのではなく、`whisper.language` の値を
`Qwen3ASREngine.lang_map`(`core/transcription_interface.py`)に追加するだけでよい:

```python
lang_map = {"ja": "Japanese", "en": "English", "zh": "Chinese"}  # 追加例
```

WhisperTranscriptionEngine 側は `config.language` をそのまま渡すため変換不要
（対応言語はモデル自体の対応範囲に依存する）。

### 3. 進捗表示・ログのカスタマイズ

専用のObserver登録機構は無い。`tc` は `transcribe_audio()` 内で
`progress_callback` を直接渡し、`transcribe.py` は `rich.console.Console.print`
を直接呼ぶ単純なコールバック方式。カスタムしたい場合はこの呼び出し箇所を
直接編集する。

## 🔧 設定カスタマイズ

### config/config.yaml編集
```yaml
whisper:
  model: "your-custom-model"    # 使用するモデル(モデル名でエンジンが自動選択される)
  language: "ja"
  device: "cuda"
  context_file: "config/context_hints.txt"  # 固有名詞・専門用語のヒント(Qwen3-ASR用)
```

> `whisper.language_models` セクションは現在dead code(どこからも参照されない)。
> 削除はしていないが、ここに項目を追加しても動作には影響しない。

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