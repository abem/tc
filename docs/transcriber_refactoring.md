# Transcriberクラスの責務分割計画

## 1. 現状の問題点
- 単一のクラスで以下の責務を全て担っている
  - 音声ファイルの処理
  - 文字起こし処理
  - ファイル入出力
  - エラーハンドリング
  - ログ出力
  - 一時ファイル管理

## 2. 分割後のクラス構成

### 2.1 AudioProcessor
```python
class AudioProcessor:
    """音声ファイルの処理を担当するクラス"""
    
    def __init__(self, chunk_size: int = 300):
        self.chunk_size = chunk_size
    
    def split_audio(self, audio_path: str) -> List[str]:
        """音声ファイルを分割"""
        pass
    
    def validate_audio(self, audio_path: str) -> bool:
        """音声ファイルの検証"""
        pass
    
    def get_audio_info(self, audio_path: str) -> Dict:
        """音声ファイルの情報取得"""
        pass
```

### 2.2 TranscriptionManager
```python
class TranscriptionManager:
    """文字起こし処理を担当するクラス"""
    
    def __init__(self, model_name: str = "large-v3"):
        self.model = self._load_model(model_name)
    
    def transcribe(self, audio_path: str) -> str:
        """音声を文字起こし"""
        pass
    
    def _load_model(self, model_name: str):
        """Whisperモデルの読み込み"""
        pass
    
    def _optimize_gpu(self):
        """GPU最適化"""
        pass
```

### 2.3 FileHandler
```python
class FileHandler:
    """ファイル操作を担当するクラス"""
    
    def __init__(self, temp_dir: str = "/tmp/transcribe_audio"):
        self.temp_dir = temp_dir
    
    def save_transcription(self, text: str, output_path: str):
        """文字起こし結果の保存"""
        pass
    
    def cleanup_temp_files(self):
        """一時ファイルの削除"""
        pass
    
    def create_temp_dir(self):
        """一時ディレクトリの作成"""
        pass
```

### 2.4 Logger
```python
class Logger:
    """ログ出力を担当するクラス"""
    
    @staticmethod
    def setup_logger():
        """ロガーの設定"""
        pass
    
    @staticmethod
    def log_progress(message: str, level: str = "INFO"):
        """進捗ログの出力"""
        pass
    
    @staticmethod
    def log_error(error: Exception):
        """エラーログの出力"""
        pass
```

## 3. 移行手順

### 3.1 準備フェーズ
1. 新しいクラスファイルの作成
   - `audio_processor.py`
   - `transcription_manager.py`
   - `file_handler.py`
   - `logger.py`

2. 既存の`Transcriber`クラスの分析
   - 各メソッドの責務を特定
   - 依存関係の整理
   - テストケースの確認

### 3.2 実装フェーズ
1. 各クラスの基本実装
   - インターフェースの定義
   - 基本的なメソッドの実装
   - エラーハンドリングの実装

2. テストの実装
   - 単体テストの作成
   - 統合テストの作成
   - エッジケースのテスト

### 3.3 移行フェーズ
1. 段階的な移行
   - 各機能を1つずつ新しいクラスに移行
   - 動作確認
   - テストの実行

2. 既存コードの更新
   - `Transcriber`クラスの更新
   - 依存関係の更新
   - エラーハンドリングの更新

### 3.4 検証フェーズ
1. 機能テスト
   - 各機能の動作確認
   - パフォーマンスの確認
   - エラー処理の確認

2. 統合テスト
   - 全体の動作確認
   - エッジケースの確認
   - パフォーマンスの確認

## 4. 期待される効果
- コードの可読性向上
- テストの容易化
- 機能の拡張性向上
- バグの早期発見
- メンテナンス性の向上

## 5. リスクと対策
- 既存機能への影響
  - 対策：段階的な移行
  - 対策：十分なテスト
- パフォーマンスへの影響
  - 対策：プロファイリング
  - 対策：最適化
- 互換性の問題
  - 対策：後方互換性の維持
  - 対策：移行期間の設定 