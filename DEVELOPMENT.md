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
  "python.defaultInterpreterPath": "./venv-clean/bin/python",
  "python.formatting.provider": "black",
  "python.linting.flake8Enabled": true,
  "python.linting.mypyEnabled": true,
  "editor.formatOnSave": true,
  "python.sortImports.args": ["--profile", "black"]
}
```

## 🏗️ プロジェクト構造

### コアモジュール
```
transcribe_audio/
├── tc                           # メインエントリーポイント(uv run 経由)
├── transcribe.py                # 代替エントリーポイント(uv run 経由)
├── transcriber.py              # 音声認識コア（WhisperTranscriber）
├── speaker_diarization.py      # 話者分離（SpeakerDiarizer）
├── exceptions.py               # 統合例外処理
├── config.py                   # 設定管理
├── logger.py                   # ログ設定
├── utils.py                    # ユーティリティ関数
├── file_utils.py              # ファイル操作
├── gdrive_handler.py          # Google Drive API
├── youtube_handler.py         # YouTube処理
└── youtube_gdrive_handler.py  # YouTube+Drive統合
```

### 設計パターン実装
```
patterns/
├── __init__.py                 # パッケージ初期化
├── factories.py                # Abstract Factory Pattern
├── strategies.py               # Strategy Pattern  
├── commands.py                 # Command Pattern
├── observers.py                # Observer Pattern
├── dependency_injection.py     # Dependency Injection
├── refactored_components.py    # リファクタリングされたコンポーネント
├── utilities.py                # パターン用ユーティリティ
└── README.md                   # パターン詳細ドキュメント
```

### テスト・品質管理
```
tests/
├── test_basic.py               # 基本機能テスト
├── test_integration.py         # 統合テスト
└── test_patterns.py.todo       # パターンテスト（今後実装）

.github/workflows/
├── ci.yml                      # CI/CDパイプライン
└── pre-commit.yml              # プリコミット品質チェック

pyproject.toml                  # プロジェクト設定・品質管理
pytest.ini                     # pytest設定
```

### 設定・ドキュメント
```
config/
└── config.yaml                 # システム設定

docs/
├── current_status_2025_july.md # 現在の状況
├── optimization_features.md    # 最適化機能
└── archive/                    # 古いドキュメント

scripts/
├── pre_check.sh               # 品質チェックスクリプト
└── simple_gpu_monitor.sh      # GPU監視
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
python -m pytest tests/ -v

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
python -m pytest tests/test_basic.py -v

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
# 全テスト実行
python -m pytest tests/ -v

# カバレッジ付きテスト
python -m pytest tests/ --cov=. --cov-report=html

# 特定テストのみ
python -m pytest tests/test_basic.py::test_basic_imports -v

# 並列実行（高速化）
python -m pytest tests/ -n auto
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

### Factory Pattern
```python
# patterns/factories.py
from patterns import create_japanese_transcriber

# 言語固有のトランスクライバー作成
transcriber = create_japanese_transcriber(
    quality='high_quality',
    device='cuda'
)
```

### Strategy Pattern
```python
# patterns/strategies.py
from patterns.strategies import StrategyRegistry

# GPU最適化戦略の取得
batch_strategy = StrategyRegistry.get_batch_strategy(
    'gpu', 
    rtx_4080_optimized=True
)

# タイムスタンプ戦略の切り替え
timestamp_strategy = StrategyRegistry.get_timestamp_strategy(
    'milliseconds'
)
```

### Command Pattern
```python
# patterns/commands.py
from patterns import AudioProcessingPipeline, CommandInvoker

# コマンドパターンでの処理実行
context = AudioProcessingContext(
    input_path='audio.wav',
    language='ja',
    enable_diarization=True
)

pipeline = AudioProcessingPipeline()
invoker = CommandInvoker()
result = invoker.execute(pipeline, context)
```

### Observer Pattern
```python
# patterns/observers.py
from patterns import setup_standard_monitoring

# 進捗監視セットアップ
observable_transcriber, observers = setup_standard_monitoring(transcriber)

# カスタムオブザーバー追加
class CustomObserver:
    def update(self, event_type, data):
        print(f"Event: {event_type}, Data: {data}")

observable_transcriber.add_observer(CustomObserver())
```

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
# transcriber.py
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

### 1. 新しいTranscription戦略追加
```python
# patterns/strategies.py に追加

class NewOptimizationStrategy(BatchSizeStrategy):
    def calculate_batch_size(self, audio_length: int) -> int:
        # 新しい計算ロジック
        return optimized_batch_size

# StrategyRegistryに登録
StrategyRegistry.register_batch_strategy(
    'new_optimization', 
    NewOptimizationStrategy
)
```

### 2. 新しい言語サポート追加
```python
# patterns/factories.py に追加

def create_chinese_transcriber(quality: str = 'balanced'):
    """中国語特化トランスクライバー作成"""
    selector = LanguageAwareModelSelector()
    model = selector.select_model('zh', quality)
    
    config = TranscriptionConfig(
        model=model,
        language='zh'
    )
    return WhisperTranscriber(config)
```

### 3. カスタムObserver実装
```python
# patterns/observers.py に追加

class DatabaseLogger(Observer):
    """データベースログ記録Observer"""
    
    def update(self, event_type: str, data: Dict[str, Any]):
        if event_type == 'transcription_complete':
            self.save_to_database(data)
    
    def save_to_database(self, data):
        # DB保存ロジック
        pass
```

## 🔧 設定カスタマイズ

### config/config.yaml編集
```yaml
whisper:
  model: "your-custom-model"
  language: "ja"
  device: "cuda"
  
  # カスタム言語モデル追加
  language_models:
    zh:  # 中国語追加例
      default: "openai/whisper-large-v3"
      alternatives:
        - "custom-chinese-model"

speaker_diarization:
  enable: true
  model: "pyannote/speaker-diarization-3.1"
  max_speakers: 5  # デフォルト話者数変更

# 新しい設定セクション追加
custom_features:
  enable_experimental: false
  new_algorithm: "v2"
```

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
        AudioProcessingError: 音声処理エラー
        ValidationError: 入力検証エラー
    
    Example:
        >>> transcriber = WhisperTranscriber(config)
        >>> result = transcriber.transcribe_audio(
        ...     'audio.wav', 
        ...     language='ja',
        ...     enable_diarization=True
        ... )
        >>> print(result['text'])
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
python -m pytest tests/test_basic.py::test_basic_imports -v -s
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