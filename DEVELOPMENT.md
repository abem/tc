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

# HuggingFaceトークン設定（日本語転写・話者分離用）
export HUGGINGFACE_TOKEN=hf_your_token_here
```

### 3. エディタ設定推奨

**VS Code設定例** (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "./.venv/bin/python",
  "python.formatting.provider": "black",
  "python.linting.flake8Enabled": true,
  "python.linting.mypyEnabled": true,
  "editor.formatOnSave": true,
  "python.sortImports.args": ["--profile", "black"]
}
```

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
│   ├── config.py              # TranscriptionConfig/DiarizationConfig/UnifiedConfig
│   ├── logging.py             # 統一ロガー
│   ├── transcription_interface.py  # UnifiedTranscriber・Qwen3ASREngine・WhisperTranscriptionEngine
│   ├── model_manager.py       # モデルキャッシュ管理
│   ├── cli_common.py          # CLI共通ヘルパー
│   ├── cli_workflow.py        # 入力解決(resolve_input_audio)・アップロードフロー
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
if Qwen3ASREngine.is_qwen3_model(transcription_config.model):
    self.transcription_engine = Qwen3ASREngine(transcription_config)
else:
    self.transcription_engine = WhisperTranscriptionEngine(transcription_config)
```

言語(`whisper.language`)は `Qwen3ASREngine.lang_map` で `Qwen3-ASR` の言語指定へ
変換されるのみで、モデル切替とは無関係(詳細は `docs/user-guides/language_support_guide.md`)。

### テスト・品質管理
```
tests/
├── test_core_config.py
├── test_core_logging.py
├── test_core_utils.py
├── test_e2e_dry_run.py
├── test_handlers_gdrive.py
└── test_handlers_youtube.py

.github/workflows/
├── ci.yml.disabled            # CI/CDパイプライン(現在無効化)
├── minimal-test.yml
├── pre-commit.yml             # プリコミット品質チェック
└── simple-test.yml

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
├── pre_check.sh                # 品質チェックスクリプト
├── gpu_monitor.py              # GPU監視
├── simple_gpu_monitor.sh       # GPU監視(簡易版)
├── e2e_local.sh                # E2Eテスト(ローカル実行)
└── cleanup_transcriptions.sh   # 出力クリーンアップ
```

## 🔄 開発フロー

### 1. 新機能開発
```bash
# ブランチ作成
git checkout -b feature/new-awesome-feature

# 開発作業
# ... コーディング ...

# 品質チェック実行
./scripts/pre_check.sh

# テスト実行
uv run pytest tests/ -v

# コミット
git add .
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
uv run pytest tests/test_basic.py -v

# コミット
git commit -m "fix: resolve issue #123 with audio processing"
```

### 3. プルリクエスト作成
1. GitHub上でPRを作成
2. CI/CDの自動チェック待機
3. コードレビュー対応
4. マージ

## 🔍 コード品質管理

### 自動フォーマッット
```bash
# コード整形
black .

# インポート整理
isort .

# 品質チェック
flake8 .

# 型チェック
mypy .
```

### 設定ファイル（pyproject.toml）
```toml
[tool.black]
line-length = 120
target-version = ['py311']

[tool.isort]
profile = "black"
line_length = 120

[tool.flake8]
max-line-length = 120
extend-ignore = ["E203", "W503"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
disallow_untyped_defs = true
```

### 事前チェックスクリプト
```bash
# 包括的品質チェック
./scripts/pre_check.sh

# 実行内容:
# 1. テスト実行
# 2. ドキュメント整合性チェック  
# 3. コーディング規約チェック
# 4. Git操作チェック
# 5. CI設定チェック
```

## 🧪 テスト実行

### 基本テスト
```bash
# 全テスト実行 (uv 経由)
uv run pytest tests/ -v

# カバレッジ付きテスト
uv run pytest tests/ --cov=. --cov-report=html

# 特定テストのみ
uv run pytest tests/test_basic.py::test_basic_imports -v

# 並列実行（高速化）
uv run pytest tests/ -n auto
```

### テストカテゴリ

**基本機能テスト** (`tests/test_basic.py`):
- モジュールインポート
- 設定クラス初期化
- 例外階層確認
- デバイス検出

**統合テスト** (`tests/test_integration.py`):
- プロジェクト構造確認
- スクリプト実行権限
- GitHub Actions設定
- ドキュメント構造

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
仕組み」参照)がモデル名を見て `if/else` で直接インスタンス化する。

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

# 特定モジュールのログ制御
logger = logging.getLogger('transcriber')
logger.setLevel(logging.DEBUG)
```

### 詳細実行
```bash
# 詳細ログ付き実行
./tc --verbose

# CPU使用でのデバッグ（GPU問題回避）
./tc --device cpu --verbose

# 小さなチャンクでのテスト
./tc --verbose # config.yamlでchunk_size調整
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

### GPU最適化
```python
# core/config.py の TranscriptionConfig
config = TranscriptionConfig(
    device='cuda',
    optimal_batch_size=8,  # RTX 4080向け
    enable_multi_stream=True,
    enable_dynamic_memory_pool=True
)
```

### メモリ管理
```python
# メモリ効率化設定
config = TranscriptionConfig(
    max_cache_size=3,
    memory_efficiency=True,
    enable_tensor_sharing=True
)
```

### 非同期処理
```python
# 非同期処理有効化
config = TranscriptionConfig(
    enable_async=True,
    max_concurrent_streams=4
)
```

### プロファイリング
```bash
# パフォーマンス測定 (tc ランチャーは uv run 経由)
uv run python -m cProfile -o profile.stats tc

# メモリ使用量監視
uv run python -m memory_profiler tc
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
# (現状は Qwen3ASREngine.is_qwen3_model() の if/else のみ)
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

speaker_diarization:
  enable: true
  model: "pyannote/speaker-diarization-3.1"
  max_speakers: 5  # デフォルト話者数変更(transcribe.py 経由でのみ有効。tc は話者分離非対応)
```

> `whisper.language_models` セクションは現在dead code(どこからも参照されない)。
> 削除はしていないが、ここに項目を追加しても動作には影響しない。

## 📚 APIドキュメント生成

### docstring形式
```python
def transcribe_audio(self, audio_path: str, **kwargs) -> Dict[str, Any]:
    """
    音声ファイルを文字起こしする
    
    Args:
        audio_path (str): 音声ファイルのパス
        **kwargs: 追加オプション
            - language (str): 言語コード ('ja', 'en')
            - enable_diarization (bool): 話者分離有効化
            - max_speakers (int): 最大話者数
    
    Returns:
        Dict[str, Any]: 文字起こし結果
            - text (str): 文字起こしテキスト
            - segments (List): セグメント情報
            - speakers (List): 話者情報（話者分離時）
    
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
# .venv を作り直して依存関係を再インストール (uv 管理)
rm -rf .venv
uv sync
```

**Q: テストが失敗する**
```bash
# キャッシュクリア
rm -rf .pytest_cache/ __pycache__/

# 依存関係チェック
pip check

# 個別テスト実行
uv run pytest tests/test_basic.py::test_basic_imports -v -s
```

**Q: GPU out of memory**
```bash
# メモリ確認
nvidia-smi

# CPU実行に切り替え
export CUDA_VISIBLE_DEVICES=""
./tc --device cpu
```

**Q: HuggingFace認証エラー**
```bash
# トークン確認
echo $HUGGINGFACE_TOKEN

# 権限確認（pyannote modelアクセス）
# https://huggingface.co/pyannote/speaker-diarization-3.1
```

### デバッグのベストプラクティス

1. **段階的デバッグ**: 小さな入力から始める
2. **ログ活用**: `--verbose`オプション使用
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