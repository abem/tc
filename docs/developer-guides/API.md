# API仕様書 📖

音声文字起こしシステム（transcribe_audio）のプログラマー向けAPI仕様書です。

## 📋 目次

- [概要](#概要)
- [メインクラス](#メインクラス)
- [設定システム](#設定システム)
- [音声処理](#音声処理)
- [話者分離](#話者分離)
- [ファイルハンドリング](#ファイルハンドリング)
- [エラーハンドリング](#エラーハンドリング)
- [使用例](#使用例)

## 概要

このシステムは以下の主要コンポーネントで構成されています：

- **UnifiedTranscriber**: 統一された音声転写インターフェース
- **WhisperTranscriber**: Whisperモデルベースの音声認識
- **SpeakerDiarizer**: 話者分離機能
- **UnifiedConfig**: 統一設定管理システム

## メインクラス

### UnifiedTranscriber

統一された音声転写インターフェース。全ての音声処理を統括します。

```python
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig

# 基本的な使用法
config = TranscriptionConfig(
    model="large-v3",
    language="ja",
    device="cuda"
)

transcriber = UnifiedTranscriber(config)
result = transcriber.transcribe("audio.wav")
```

#### メソッド

##### `transcribe(audio_path: str, **kwargs) -> Dict[str, Any]`

音声ファイルを文字起こしします。

**パラメータ:**
- `audio_path` (str): 音声ファイルのパス
- `**kwargs`: 追加オプション
  - `language` (str): 言語コード ('ja', 'en')
  - `enable_diarization` (bool): 話者分離有効化
  - `max_speakers` (int): 最大話者数

**戻り値:**
```python
{
    "text": str,           # 文字起こしテキスト
    "segments": List[Dict], # セグメント情報
    "speakers": List[Dict], # 話者情報（話者分離時）
    "metadata": Dict        # メタデータ
}
```

**例:**
```python
result = transcriber.transcribe(
    "audio.wav",
    language="ja",
    enable_diarization=True,
    max_speakers=3
)

print(result["text"])
for segment in result["segments"]:
    print(f"[{segment['start']:.2f}s] {segment['text']}")
```

### WhisperTranscriber（廃止済み）

**注意**: `WhisperTranscriber`は削除されました。代わりに`UnifiedTranscriber`を使用してください。

```python
# 旧（廃止）
# from transcriber import WhisperTranscriber

# 新（推奨）
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig

config = TranscriptionConfig(
    model="kotoba-tech/kotoba-whisper-v2.2",
    language="ja",
    device="cuda"
)

transcriber = UnifiedTranscriber(config)
```

#### メソッド

##### `load_model() -> None`

Whisperモデルをロードします。

```python
transcriber.load_model()
```

##### `transcribe_audio(audio_path: str) -> str`

音声ファイルを文字起こしします。

**パラメータ:**
- `audio_path` (str): 音声ファイルのパス

**戻り値:**
- `str`: 文字起こしされたテキスト

### SpeakerDiarizer

話者分離機能を提供します。

```python
from speaker_diarization import SpeakerDiarizer
from core.config import DiarizationConfig

config = DiarizationConfig(
    model="pyannote/speaker-diarization-3.1",
    max_speakers=4
)

diarizer = SpeakerDiarizer(config)
```

#### メソッド

##### `diarize(audio_path: str, max_speakers: Optional[int] = None) -> List[Dict]`

音声ファイルの話者分離を実行します。

**パラメータ:**
- `audio_path` (str): 音声ファイルのパス
- `max_speakers` (int, optional): 最大話者数

**戻り値:**
```python
[
    {
        "start": float,     # 開始時刻（秒）
        "end": float,       # 終了時刻（秒）
        "speaker": str      # 話者ID（例: "SPEAKER_00"）
    },
    ...
]
```

##### `combine_with_transcription(transcription_segments: List[Dict], speaker_segments: List[Dict]) -> List[Dict]`

転写結果と話者分離結果を統合します。

## 設定システム

### UnifiedConfig

統一設定管理システム。YAML設定ファイルを読み込み、全システムの設定を管理します。

```python
from core.config import UnifiedConfig

# 設定ファイルの読み込み
UnifiedConfig.load("config/config.yaml")

# 設定値の取得
whisper_model = UnifiedConfig.get("whisper", "model")
device = UnifiedConfig.get("whisper", "device", default="cpu")
```

#### メソッド

##### `load(config_path: str = "config/config.yaml") -> None`

設定ファイルを読み込みます。

##### `get(section: str, key: str, default: Any = None) -> Any`

設定値を取得します。

### TranscriptionConfig

音声転写設定のデータクラス。

```python
from core.config import TranscriptionConfig

config = TranscriptionConfig(
    model="large-v3",
    language="ja",
    device="cuda",
    chunk_length=30,
    max_new_tokens=400
)
```

#### 属性

- `model` (str): 使用するWhisperモデル
- `language` (str): 言語コード
- `device` (str): 推論デバイス
- `chunk_length` (int): チャンク長（秒）
- `max_new_tokens` (int): 最大生成トークン数

### DiarizationConfig

話者分離設定のデータクラス。

```python
from core.config import DiarizationConfig

config = DiarizationConfig(
    model="pyannote/speaker-diarization-3.1",
    max_speakers=4,
    min_speakers=1
)
```

## 音声処理

### ファイル形式サポート

- **入力形式**: WAV, MP3, MP4, M4A, FLAC, OGG
- **出力形式**: TXT, JSON, SRT（計画中）

### 音声前処理

```python
import soundfile as sf
import numpy as np

# 音声ファイルの読み込み
audio, sample_rate = sf.read("audio.wav")

# リサンプリング（必要に応じて）
if sample_rate != 16000:
    import librosa
    audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
```

### チャンク処理

長時間音声は自動的にチャンクに分割されます：

```python
# 設定でチャンク長を指定
config = TranscriptionConfig(
    chunk_length=30,  # 30秒チャンク
    overlap=2         # 2秒オーバーラップ
)
```

## ファイルハンドリング

### Google Drive連携

```python
from handlers import GDriveClient

client = GDriveClient()

# ファイルのダウンロード
client.download_file("file_id", "output_path")

# 結果のアップロード
file_id = client.upload_file("result.txt", "result.txt", "parent_folder_id")

# URLの取得
url = client.get_file_url(file_id)
```

### YouTube連携

```python
from handlers import YouTubeClient

client = YouTubeClient()

# 音声の抽出
audio_path, metadata = client.download_audio("https://youtube.com/watch?v=...")
```

## エラーハンドリング

### 例外クラス（handlers）

```python
from handlers import DriveError, UploadError, DownloadError

try:
    client = GDriveClient()
    client.download_file(file_id, output_path)
except DownloadError as e:
    print(f"ダウンロードエラー: {e}")
except UploadError as e:
    print(f"アップロードエラー: {e}")
except DriveError as e:
    print(f"Google Driveエラー: {e}")
```

**注意**: 以前の`exceptions`モジュールは削除されました。ハンドラー関連のエラーは`handlers`モジュールの例外クラスを使用してください。

### エラー処理パターン（handlers）

```python
from handlers import GDriveClient, DriveError, UploadError, DownloadError

try:
    client = GDriveClient()
    client.download_file(file_id, output_path)
except DownloadError as e:
    print(f"ダウンロードエラー: {e}")
except DriveError as e:
    print(f"Google Driveエラー: {e}")
```

```python
def safe_transcription(audio_path: str, fallback_device: str = "cpu"):
    """安全な音声転写（フォールバック付き）"""
    try:
        # GPU処理を試行
        config = TranscriptionConfig(device="cuda")
        transcriber = UnifiedTranscriber(config)
        return transcriber.transcribe(audio_path)
    except torch.cuda.OutOfMemoryError:
        # GPU メモリ不足時はCPUにフォールバック
        config = TranscriptionConfig(device=fallback_device)
        transcriber = UnifiedTranscriber(config)
        return transcriber.transcribe(audio_path)
```

## 使用例

### 基本的な文字起こし

```python
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig, UnifiedConfig

# 設定の読み込み
UnifiedConfig.load()

# 基本設定
config = TranscriptionConfig(
    model="large-v3",
    language="ja",
    device="cuda"
)

# 転写実行
transcriber = UnifiedTranscriber(config)
result = transcriber.transcribe("audio.wav")

print("転写結果:")
print(result["text"])
```

### 話者分離付き文字起こし

```python
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig, DiarizationConfig

# 話者分離を含む設定
transcription_config = TranscriptionConfig(
    model="kotoba-tech/kotoba-whisper-v2.2",
    language="ja",
    device="cuda"
)

diarization_config = DiarizationConfig(
    model="pyannote/speaker-diarization-3.1",
    max_speakers=3
)

# 実行
transcriber = UnifiedTranscriber(transcription_config)
result = transcriber.transcribe(
    "meeting.wav",
    enable_diarization=True,
    diarization_config=diarization_config
)

# 話者別表示
for segment in result["segments"]:
    speaker = segment.get("speaker", "Unknown")
    start_time = segment["start"]
    text = segment["text"]
    print(f"[{start_time:.1f}s] {speaker}: {text}")
```

### YouTube動画の処理

```python
from handlers import YouTubeClient, GDriveClient
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig

# YouTube音声抽出
yt_client = YouTubeClient()
audio_path, metadata = yt_client.download_audio("https://youtube.com/watch?v=...")

# 文字起こし
config = TranscriptionConfig(language="ja")
transcriber = UnifiedTranscriber(config)
result = transcriber.transcribe(audio_path)

# Google Driveにアップロード
gdrive_client = GDriveClient()
upload_result = gdrive_client.upload_youtube_transcription(
    "result.txt",
    metadata
)

print(f"処理完了: {upload_result['file_url']}")
```

### バッチ処理

```python
from pathlib import Path
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig

def batch_transcribe(audio_dir: str, output_dir: str):
    """ディレクトリ内の全音声ファイルを一括処理"""
    
    config = TranscriptionConfig(language="ja", device="cuda")
    transcriber = UnifiedTranscriber(config)
    
    audio_files = Path(audio_dir).glob("*.wav")
    
    for audio_file in audio_files:
        try:
            result = transcriber.transcribe(str(audio_file))
            
            # 結果保存
            output_file = Path(output_dir) / f"{audio_file.stem}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result["text"])
                
            print(f"完了: {audio_file.name}")
            
        except Exception as e:
            print(f"エラー {audio_file.name}: {e}")

# 実行
batch_transcribe("input_audio/", "output_text/")
```

### カスタム設定での高度な使用

```python
from core.config import TranscriptionConfig, DiarizationConfig, SystemConfig
from core.transcription_interface import UnifiedTranscriber

# 高度な設定
transcription_config = TranscriptionConfig(
    model="kotoba-tech/kotoba-whisper-v2.2",
    language="ja",
    device="cuda",
    chunk_length=30,
    max_new_tokens=400,
    temperature=0.0,
    do_sample=False
)

diarization_config = DiarizationConfig(
    model="pyannote/speaker-diarization-3.1",
    max_speakers=5,
    min_speakers=1
)

system_config = SystemConfig(
    enable_gpu_optimization=True,
    memory_efficiency=True,
    cache_models=True
)

# 実行
transcriber = UnifiedTranscriber(
    transcription_config, 
    system_config=system_config
)

result = transcriber.transcribe(
    "complex_meeting.wav",
    enable_diarization=True,
    diarization_config=diarization_config,
    output_format="detailed"  # 詳細情報付き出力
)

# 詳細結果の活用
print(f"処理時間: {result['metadata']['processing_time']:.2f}秒")
print(f"検出話者数: {len(result['speakers'])}人")
print(f"総セグメント数: {len(result['segments'])}個")
```

## パフォーマンス最適化

### GPU最適化

```python
# RTX 4080向け最適化
config = TranscriptionConfig(
    device="cuda",
    optimal_batch_size=8,
    enable_multi_stream=True,
    enable_dynamic_memory_pool=True
)
```

### メモリ効率化

```python
# メモリ使用量削減
config = TranscriptionConfig(
    max_cache_size=3,
    memory_efficiency=True,
    enable_tensor_sharing=True
)
```

### 非同期処理

```python
import asyncio
from core.transcription_interface import AsyncUnifiedTranscriber

async def async_transcribe_multiple(audio_files: List[str]):
    """複数ファイルの非同期処理"""
    transcriber = AsyncUnifiedTranscriber()
    
    tasks = [
        transcriber.transcribe_async(audio_file) 
        for audio_file in audio_files
    ]
    
    results = await asyncio.gather(*tasks)
    return results

# 実行
audio_files = ["audio1.wav", "audio2.wav", "audio3.wav"]
results = asyncio.run(async_transcribe_multiple(audio_files))
```

---

## 📞 サポート

- **GitHub Issues**: [transcribe_audio/issues](https://github.com/yourusername/transcribe_audio/issues)
- **API仕様に関する質問**: GitHub Discussions
- **バグ報告**: Issue template使用

このAPI仕様書は継続的に更新されます。最新版は常にGitHubリポジトリで確認してください。