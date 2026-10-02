# API仕様書 📖

音声文字起こしシステム（tc）のプログラマー向けAPI仕様書です。
ここに書いたクラス・関数・引数は、`core/`・`handlers/` の現行の実装と照合したものです。

## 📋 目次

- [概要](#概要)
- [メインクラス](#メインクラス)
- [設定システム](#設定システム)
- [入力の解決とワークフロー](#入力の解決とワークフロー)
- [ファイルハンドリング](#ファイルハンドリング)
- [エラーハンドリング](#エラーハンドリング)
- [モデル管理とロガー](#モデル管理とロガー)
- [WebUI向けモジュール](#webui向けモジュール)
- [使用例](#使用例)

## 概要

このシステムは以下の主要コンポーネントで構成されています：

- **UnifiedTranscriber**（`core/transcription_interface.py`）: 統一された音声転写インターフェース。
  モデル名で次の3つのエンジンから1つを選びます。
  - `NemotronSubprocessEngine`（`core/nemotron_engine.py`）: モデル名に `nemotron` を含む場合
  - `Qwen3ASREngine`（`core/transcription_interface.py`）: モデル名に `qwen3-asr`（または `qwen3_asr`）を含む場合
  - `WhisperTranscriptionEngine`（`core/transcription_interface.py`）: それ以外
- **UnifiedConfig / TranscriptionConfig / SystemConfig**（`core/config.py`）: 設定管理
- **GDriveClient / YouTubeClient**（`handlers/`）: Google Drive の入出力と、YouTube・X の音声抽出
- **core/cli_workflow.py**: 入力の解決・アップロード・変換履歴の記録（`tc`・`transcribe.py`・WebUI 共通）
- **core/webui_workflow.py**: WebUI（`webui.py`）のジョブキュー

話者分離機能は撤去済みです。`speaker_diarization.py` や `DiarizationConfig` はありません。

## メインクラス

### UnifiedTranscriber

統一された音声転写インターフェース。全ての音声処理を統括します。

```python
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig

config = TranscriptionConfig(
    model="Qwen/Qwen3-ASR-1.7B",
    language="ja",
    device="cuda"
)

transcriber = UnifiedTranscriber(config)
result = transcriber.transcribe("audio.wav")
print(result.text)
```

コンストラクタは `UnifiedTranscriber(transcription_config: TranscriptionConfig)` です。
モデルのロードは初回の `transcribe()` 呼び出し時に各エンジンの内部で遅延実行されるため、
事前の明示的なロードは不要です。

#### メソッド

##### `transcribe(audio_path: str, progress_callback: Optional[Callable] = None, **kwargs) -> TranscriptionResult`

音声ファイルを文字起こしします。

**パラメータ:**
- `audio_path` (str): 音声ファイルのパス
- `progress_callback` (Callable, optional): 進捗メッセージ（文字列）を受け取る関数。
  開始時と完了時に呼ばれます
- `**kwargs`: エンジンへそのまま渡されますが、現行の3エンジンはどれも追加引数を使いません

**戻り値:** `TranscriptionResult`（辞書ではなくデータクラス。属性でアクセスします）

### TranscriptionResult / TranscriptionSegment

`core.transcription_interface` で定義されたデータクラスです。

`TranscriptionResult` の属性:

- `text` (str): 文字起こし全文
- `segments` (List[TranscriptionSegment]): 区間ごとの結果
- `language` (str): 言語
- `duration` (float): 音声の長さ（秒）
- `processing_time` (float): 処理時間（秒）
- `model_name` (str): 使用モデル
- `has_speakers` (bool): 常に `False`（話者分離の撤去後も項目だけ残っています）
- `metadata` (Optional[Dict[str, Any]]): エンジンごとの付加情報（下表）

`to_dict()` で辞書に変換できます（JSON などへの保存用）。

`TranscriptionSegment` の属性: `start` / `end`（秒）、`text`、`speaker`（常に `None`）、
`confidence`、`language`。

エンジンごとの `segments` と `metadata`:

| エンジン | `segments` | `metadata` のキー |
|---|---|---|
| Qwen3-ASR | 通常は全体で1件。`include_timestamps=True` かつ整合に成功した場合は文節ごと | `detected_language`・`chunked`・`failed_chunks`・`repeated_chunks`・`timestamps_included` |
| Whisper | 本文中の `[MM:SS]` を解析した30秒区間 | なし（`None`） |
| Nemotron | 全体で1件 | `engine`・`infer_elapsed_sec`・`load_elapsed_sec`・`chunked`・`chunk_count`・`failed_chunks`・`empty_chunks` |

長い音声は、Qwen3-ASR が300秒（5分）を超えるとチャンクに分割して処理します。Nemotron は350秒を超えると
ストリーミング推論で処理し、失敗した場合は分割方式へフォールバックします。Whisper は常に30秒単位で処理します。

## 設定システム

### UnifiedConfig

統一設定管理システム。YAML設定ファイルを読み込み、設定値を取得します（クラスメソッドで使います）。

```python
from core.config import UnifiedConfig

# 設定ファイルの読み込み
UnifiedConfig.load("config/config.yaml")

# 設定値の取得（キーは複数指定できる）
whisper_model = UnifiedConfig.get("whisper", "model")
device = UnifiedConfig.get("whisper", "device", default="cpu")
```

#### メソッド

##### `load(config_path: str = "config/config.yaml") -> None`

設定ファイルを読み込みます。

##### `get(*keys, default=None) -> Any`

キーを順にたどって設定値を取得します。存在しないキーでは `default` を返します。
`load()` を呼んでいなければ、既定のパスから自動で読み込みます。

設定ファイルのキーのうち、現行のコードが読んで動作に影響するもの（`gdrive.url`・`gdrive.upload_folder_id`・
`whisper.model`・`whisper.language`・`whisper.device`・`whisper.context_file`・`whisper.include_timestamps`）は
[README](../../README.md) の「設定」を参照してください。

### TranscriptionConfig

音声転写設定のデータクラス。エンジンが参照する主なフィールドは次のとおりです。

```python
from core.config import TranscriptionConfig

config = TranscriptionConfig(
    model="Qwen/Qwen3-ASR-1.7B",
    language="ja",
    device="cuda",
    context="固有名詞, 専門用語",
    include_timestamps=False
)
```

#### 属性

- `model` (str): 使用するモデル名（これでエンジンが決まります）。dataclassの既定値は `"large-v3"` なので、
  通常は明示してください
- `language` (Optional[str]): 言語コード。`None` は自動判定。既定は `"ja"`。
  Qwen3-ASR は `ja`・`en` を言語名へ対応付け、それ以外の値は自動判定になります。
  Nemotron は `ja`→`ja-JP`・`en`→`en-US`、それ以外と `None` は `auto` になります
- `device` (str): 推論デバイス（`"cuda"` / `"cpu"`）。既定は CUDA が使えれば `"cuda"`、なければ `"cpu"`
- `context` (str): 認識ヒント（固有名詞・専門用語）。Qwen3-ASR だけが使います。既定は空文字
- `include_timestamps` (bool): タイムスタンプ付与。Qwen3-ASR だけが使います（ForcedAlignerを追加でロードします）。
  既定は `False`

#### クラスメソッド

##### `for_language(language: str, quality: str = "high") -> TranscriptionConfig`

言語に応じた既定モデルを選んだ設定を返します（`ja` は `kotoba-tech/kotoba-whisper-v2.2`、
それ以外は `openai/whisper-large-v3`）。`quality`（`high` / `balanced` / `fast`）は、
現在は結果に影響しません（互換のために受け付ける引数です）。

### SystemConfig

システム全体の設定のデータクラスです。現行のコードが参照するのは `allowed_file_types`
（`.wav`・`.mp3`・`.mp4`・`.m4a`・`.flac`・`.ogg`）だけで、WebUI のファイルアップロードで
受け付ける拡張子に使われています。

## 入力の解決とワークフロー

### core.utils

```python
from core.utils import detect_input_type, is_youtube_url, is_twitter_url, is_google_drive_url
from core.utils import extract_gdrive_file_id, load_context_hints, resolve_device
```

- `detect_input_type(source: str) -> Dict[str, str]`: `{"type": ..., "source": ...}` を返します。
  `type` は `youtube` / `twitter`（X の動画URL）/ `gdrive` / `local`（存在するパス）/ `unknown`
- `is_youtube_url(url)` / `is_twitter_url(url)` / `is_google_drive_url(url)` -> bool
- `extract_gdrive_file_id(source: str) -> Optional[str]`: Google Drive URL からファイルIDを取り出します
- `load_context_hints(file_path: str) -> str`: ヒントファイル（1行1語彙、`#` 始まりはコメント）を
  `", "` 区切りの文字列にします。ファイルが無い・空なら `""`
- `resolve_device(device: str) -> str`: `"auto"` を `"cuda"` / `"cpu"` に解決します

### core.cli_workflow

`tc`・`transcribe.py`・WebUI が共通で使う関数です。

- `resolve_input_audio(source: str, output_dir: Path, *, ensure_yt_dlp: bool = False, on_status=None) -> InputResolution`:
  入力（YouTube・X・Google Drive の URL、またはローカルパス）をローカルの音声ファイルに解決します。
  認識できない入力は `ValueError` になります
- `InputResolution`: `source_type`・`original_source`・`local_audio_path`・`is_temp_file`・`metadata`・`youtube_handler`
  を持つデータクラスです
- `upload_transcription_result(*, source_type, original_source, output_file, metadata=None, folder_id=None) -> Optional[str]`:
  結果を Google Drive へアップロードし URL を返します。対象は `youtube` と `gdrive` だけで、それ以外は `None` を返します
- `record_transcription_history(*, result, resolution, output_file, settings, gdrive_url=None, db_path=...) -> None`:
  変換履歴を SQLite（既定は `output/history.db`、`DEFAULT_HISTORY_DB_PATH`）へ記録します

## ファイルハンドリング

### Google Drive連携

```python
from handlers import GDriveClient

client = GDriveClient()

# ファイルのダウンロード
client.download_file("file_id", "output_path")

# 結果のアップロード（アップロードしたファイルのIDを返す）
file_id = client.upload_file("result.txt", "result.txt", parent_id="parent_folder_id")

# URLの取得
url = client.get_file_url(file_id)
```

`GDriveClient(credentials_path: str = "credentials.json")` です。Drive のサービスは最初に必要になった時点で
初期化されます（認証は `config.py` の `get_drive_service()`）。主なメソッド:

- `download_file(file_id: str, output_path: str) -> None`
- `download(file_id_or_url: str) -> Path`: URL またはファイルIDから一時ファイルへダウンロードします
- `upload_file(file_content, filename: str, parent_id: Optional[str] = None, mimetype: str = "text/plain") -> str`:
  `file_content` はパス（str / Path）または `io.BytesIO`。ファイルIDを返します
- `upload(file_path: Path, parent_id: Optional[str] = None) -> Optional[str]`
- `get_file_url(file_id: str) -> Optional[str]`
- `get_parent_folder_id(file_id: str) -> Optional[str]`
- `find_folder_by_name(folder_name: str, parent_id: Optional[str] = None) -> Optional[str]`
- `create_folder(folder_name: str, parent_id: Optional[str] = None) -> Optional[str]`
- `upload_youtube_transcription(file_path: str, youtube_metadata: Dict[str, Any]) -> Optional[Dict[str, str]]`:
  YouTube の結果を日付フォルダへアップロードし、`file_id`・`file_url`・`file_name`・`folder_id` を返します

### YouTube / X 連携

```python
from handlers import YouTubeClient

client = YouTubeClient()

# 音声の抽出（YouTube または X の動画URL）
audio_path, metadata = client.download_audio("https://youtube.com/watch?v=...")
```

`YouTubeClient(output_dir: Optional[str] = None)`（既定の出力先は一時ディレクトリ）です。音声は yt-dlp で
WAV に抽出します。主なメソッド:

- `download_audio(url: str, output_path: Optional[str] = None) -> Tuple[str, Dict]`:
  YouTube / X 以外の URL は `ValueError` になります。`metadata` は `title`・`video_id`・`duration`・`url`・
  `channel`・`upload_date`・`description`
- `extract_video_info(url: str) -> Dict`
- `is_youtube_url(url: str) -> bool` / `is_supported_url(url: str) -> bool`（YouTube または X）
- `cleanup_temp_file(file_path: str)`

## エラーハンドリング

### 例外クラス（handlers）

```python
from handlers import GDriveClient, DriveError, UploadError, DownloadError

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

`UploadError` と `DownloadError` は `DriveError` のサブクラスです（`DriveError(message, error_code)`）。
`download_file()` は `DownloadError`、`upload_file()` は `UploadError` を送出します。

### GPUメモリ不足時のフォールバック例

```python
import torch

from core.config import TranscriptionConfig
from core.transcription_interface import UnifiedTranscriber


def safe_transcription(audio_path: str, model: str, fallback_device: str = "cpu"):
    """GPUで失敗した場合にCPUで再試行する"""
    try:
        config = TranscriptionConfig(model=model, device="cuda")
        return UnifiedTranscriber(config).transcribe(audio_path)
    except torch.cuda.OutOfMemoryError:
        config = TranscriptionConfig(model=model, device=fallback_device)
        return UnifiedTranscriber(config).transcribe(audio_path)
```

## モデル管理とロガー

### モデルキャッシュ（core.model_manager）

`WhisperTranscriptionEngine` は共有のモデルキャッシュ（`UnifiedModelManager`）を使います。
`Qwen3ASREngine` は `qwen_asr` の API で直接モデルをロードし、このキャッシュを経由しません。

```python
from core.model_manager import get_global_model_manager

manager = get_global_model_manager()          # 共有インスタンス
stats = manager.get_cache_stats()
```

### ロガー（core.logging）

```python
from core.logging import get_logger, UnifiedLogger, PerformanceLogger

logger = get_logger(__name__)
```

`core` パッケージはインポートしただけではログを設定しません。エントリポイント（`tc`、`transcribe.py`、`webui.py`）が
起動時に `core.logging.setup_logging()` を呼ぶと、INFO レベルのログがコンソールと `logs/transcription.log`
（pytest 実行中は `logs/transcription_test.log`）へ出力されるように構成されます。
出力先などを変える場合は `UnifiedLogger.configure(log_level, log_file, enable_console, enable_file, log_format)` を使います。
`PerformanceLogger(name)` は処理時間の計測（`start_timing` / `end_timing`）とメトリクス記録（`log_metric`）に使います。

## WebUI向けモジュール

`webui.py`（Streamlit）が使う `core/webui_workflow.py` の主な要素です。

- `start_transcription_job(transcriber: UnifiedTranscriber, audio_path: str, **kwargs) -> TranscriptionJob`:
  文字起こしを別スレッドで実行し、進捗を `progress_queue` で共有します。完了すると `result`（成功）または
  `error`（失敗）が設定され、`done` が `True` になります
- `drain_progress(job) -> List[str]`: 溜まった進捗メッセージを取り出します
- `TranscriptionJobQueue`: 複数の入力を逐次処理するキュー（同時実行は1件）。項目の状態は
  `QueueItemState`（`RESOLVING`・`QUEUED`・`PROCESSING`・`DONE`・`FAILED`）です
- `segments_to_srt(segments: List[TranscriptionSegment]) -> str`: セグメントを SRT 形式の文字列にします。
  タイムスタンプ付き（`include_timestamps=True`）のQwen3-ASRの結果で意味のある区間が得られます

WebUI の内部構成は [webui_architecture.md](../system-docs/webui_architecture.md) を参照してください。

## 使用例

### 基本的な文字起こし

```python
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig, UnifiedConfig

# 設定の読み込み
UnifiedConfig.load()

# 基本設定
config = TranscriptionConfig(
    model=UnifiedConfig.get("whisper", "model"),
    language=UnifiedConfig.get("whisper", "language"),
    device="cuda"
)

# 転写実行
transcriber = UnifiedTranscriber(config)
result = transcriber.transcribe("audio.wav")

print("転写結果:")
print(result.text)
```

### 入力の解決から文字起こしまで

```python
from pathlib import Path

from core.cli_workflow import resolve_input_audio
from core.config import TranscriptionConfig
from core.transcription_interface import UnifiedTranscriber

# YouTube / X / Google Drive の URL、またはローカルパスを音声ファイルに解決
resolution = resolve_input_audio("https://youtube.com/watch?v=...", Path("output"))

config = TranscriptionConfig(model="Qwen/Qwen3-ASR-1.7B", language=None)
result = UnifiedTranscriber(config).transcribe(resolution.local_audio_path)
print(result.text)

# ダウンロードした一時ファイルの削除
if resolution.is_temp_file and resolution.youtube_handler:
    resolution.youtube_handler.cleanup_temp_file(resolution.local_audio_path)
```

### YouTube動画の処理と Google Drive へのアップロード

```python
from handlers import YouTubeClient, GDriveClient
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig

# YouTube音声抽出
yt_client = YouTubeClient()
audio_path, metadata = yt_client.download_audio("https://youtube.com/watch?v=...")

# 文字起こし
config = TranscriptionConfig(model="Qwen/Qwen3-ASR-1.7B", language="ja")
result = UnifiedTranscriber(config).transcribe(audio_path)

# 結果をテキストファイルに保存
with open("result.txt", "w", encoding="utf-8") as f:
    f.write(result.text)

# Google Driveにアップロード
gdrive_client = GDriveClient()
upload_result = gdrive_client.upload_youtube_transcription("result.txt", metadata)

print(f"処理完了: {upload_result['file_url']}")
```

### バッチ処理

```python
from pathlib import Path
from core.transcription_interface import UnifiedTranscriber
from core.config import TranscriptionConfig

def batch_transcribe(audio_dir: str, output_dir: str):
    """ディレクトリ内の全音声ファイルを一括処理"""

    config = TranscriptionConfig(model="Qwen/Qwen3-ASR-1.7B", language="ja", device="cuda")
    transcriber = UnifiedTranscriber(config)  # モデルは初回呼び出しでロードされ、以降は再利用される

    audio_files = Path(audio_dir).glob("*.wav")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for audio_file in audio_files:
        try:
            result = transcriber.transcribe(str(audio_file))

            # 結果保存
            output_file = Path(output_dir) / f"{audio_file.stem}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result.text)

            print(f"完了: {audio_file.name}")

        except Exception as e:
            print(f"エラー {audio_file.name}: {e}")

# 実行
batch_transcribe("input_audio/", "output_text/")
```

### Nemotron の使用

```python
from core.config import TranscriptionConfig
from core.transcription_interface import UnifiedTranscriber

# 事前に scripts/setup_nemotron_venv.sh で venv-nemotron/ を作成しておく
config = TranscriptionConfig(model="nvidia/nemotron-3.5-asr-streaming-0.6b", language="ja", device="cuda")
result = UnifiedTranscriber(config).transcribe("audio.wav")
print(result.metadata["engine"])  # "nemotron-subprocess"
```

---

## 📞 サポート

- 不具合・質問はリポジトリの Issues で受け付けます
- 変更履歴は `CHANGELOG.md`、開発手順は `CONTRIBUTING.md` と `DEVELOPMENT.md` を参照してください
