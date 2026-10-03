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
  モデル名で次の3つのエンジンから1つを選びます（判定は `core/engine_factory.py` の `create_engine`）。
  - `NemotronSubprocessEngine`（`core/nemotron_engine.py`）: モデル名に `nemotron` を含む場合
  - `Qwen3ASREngine`（`core/qwen3_engine.py`）: モデル名に `qwen3-asr`（または `qwen3_asr`）を含む場合
  - `WhisperTranscriptionEngine`（`core/whisper_engine.py`）: それ以外
- **UnifiedConfig / TranscriptionConfig / SystemConfig**（`core/config.py`）: 設定管理
- **GDriveClient / YouTubeClient**（`handlers/`）: Google Drive の入出力と、YouTube・X の音声抽出
- **core/cli_workflow.py**: 入力の解決・保存・アップロード・変換履歴の記録・一時音声の削除（`tc`・`transcribe.py`・WebUI 共通。集約点は `finalize_transcription`）
- **core/progress.py**: 進捗通知（`ProgressMessage`）
- **core/housekeeping.py / core/history.py / core/engine_factory.py**: 期限切れの整理、変換履歴 DB、エンジン選択
- **core/webui_workflow.py**: WebUI（`webui.py`）のジョブキューと進捗の反映

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
  ファサードが開始時（`"Starting transcription..."`）と完了時（`"Transcription completed"`）に呼びます。
  途中経過はエンジンが `core.progress.ProgressMessage`（`str` のサブクラス。`fraction` は 0.0〜1.0）で通知します
  （[進捗通知](#進捗通知coreprogress) 参照）: Whisper は 30 秒チャンクごと、Qwen3-ASR は 300 秒を超えて分割処理するときチャンクごと。
  Nemotron と 300 秒以下の Qwen3-ASR は途中経過がありません
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

辞書に変換したいときは `dataclasses.asdict(result)` を使います（`to_dict()` はありません）。

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
`gdrive.scopes`（省略時は Drive 全体のスコープ。`handlers/gdrive_auth.py` が読む）・`whisper.model`・`whisper.language`・`whisper.device`・`whisper.context_file`・`whisper.include_timestamps`）は
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
  認識できない入力は `ValueError`、`ensure_yt_dlp=True` で yt-dlp が見つからないと `YtDlpNotFoundError`
  （`ValueError` のサブクラス）になります。`on_status` は `str` を受け取る関数で、ダウンロードの進捗は
  `ProgressMessage`（率つき）で届きます
- `InputResolution`: `source_type`・`original_source`・`local_audio_path`・`is_temp_file`・`metadata`・`youtube_handler`
  を持つデータクラスです。`needs_cleanup`（プロパティ）は、yt-dlp 由来（youtube / twitter）と Google Drive 由来の音声で真になります。
  **Google Drive の入力は `is_temp_file=False` で返りますが、実体は一時ファイルなので、`is_temp_file` ではなく
  `needs_cleanup` で判断します**。ローカルファイル入力は削除対象ではありません
- `cleanup_input_audio(resolution: InputResolution) -> Optional[str]`: `needs_cleanup` のとき一時音声を削除します。
  成功・失敗・中断のどの経路でも呼べます。削除に失敗しても例外は出さず、警告文を返します（正常・対象外・既に無いときは `None`）
- `save_transcription_text(result, output_dir: Path) -> Path` / `format_transcript_text(result) -> str`:
  結果を `output_dir` へ保存／保存用の文字列にします。`[MM:SS] ` 付きになるのは
  `result.metadata["timestamps_included"]` が真で segments があるときだけです
- `upload_transcription_result(*, source_type, original_source, output_file, metadata=None, folder_id=None) -> Optional[str]`:
  結果を Google Drive へアップロードし URL を返します。対象は `youtube` と `gdrive` だけで、X（twitter）などそれ以外は `None` を返します
- `record_transcription_history(*, result, resolution, output_file, settings, gdrive_url=None, db_path=...) -> None`:
  変換履歴を SQLite（既定は `output/history.db`、`DEFAULT_HISTORY_DB_PATH`）へ記録します
- `finalize_transcription(*, result, resolution, output_dir, settings, upload=True, folder_id=None, raise_upload_errors=False, on_saved=None, on_uploading=None) -> FinalizeOutcome`:
  保存 → アップロード → 履歴 → 一時音声の削除を行う集約点です。保存・アップロードが例外で失敗しても一時音声は削除します。
  アップロード失敗は既定で `outcome.upload_error` に入れて続行します（`raise_upload_errors=True` なら例外を伝播）。
  履歴の失敗は常に `outcome.history_error` に入れて続行します。`settings` は dict、または履歴記録の直前に評価する引数なしの関数です。
  文字起こし自体が失敗したときは呼び出し側が `cleanup_input_audio` を呼びます
- `FinalizeOutcome`: `output_file`・`gdrive_url`・`upload_attempted`・`upload_error`・`history_error`・`cleanup_warning`

### core.utils（補助関数）

- `sanitize_upload_filename(name: object, default: str = "upload") -> str`: アップロード名を無害化します（最大 200 文字）。
  WebUI は `output/uploads/<一意>/<サニタイズ済み名>` に保存します（同名でも上書きしません）
- `one_line(value: object, limit: int = 200) -> str`: ログ・ラベルを 1 行にします（エラー文は 1000 文字まで）
- `get_audio_duration(audio_path: str, fallback_sec: float = 600.0) -> float`: 音声の長さ（秒）。取得できないときは `fallback_sec`

### 進捗通知（core.progress）

進捗コールバックは `Callable[[str], None]` です。率を持つ通知は `ProgressMessage(text, fraction=None)`
（`str` のサブクラス。`fraction` は 0.0〜1.0 に丸められ、`None` は率が不明）で渡るので、文字列だけを受け取る
コールバックにもそのまま使えます。

- `emit_progress(callback, text: str, fraction: Optional[float] = None) -> None`: 通知します。コールバックの例外は握りつぶし、本処理を止めません
- `throttled(printer, steps: int = 10)`: CLI 用。率つきの通知は `1/steps` 進むごとに 1 回だけ `printer` へ渡します
- `parse_ytdlp_progress(line: str) -> Optional[tuple[float, Optional[str]]]`: yt-dlp の進捗行から（進捗率, ETA）を取り出します

### 整理・履歴・エンジン選択

- `core.housekeeping.cleanup_old_entries(directory: Path, max_age_days: float, *, protected_paths=(), now=None) -> List[str]`:
  `directory` 直下で更新から `max_age_days` 日を過ぎた項目を削除し、削除した名前を返します。
  WebUI は `output/uploads` を 7 日、`output/queue_downloads` を 1 日で、新しい投入のたびに呼びます
  （処理待ち・処理中のジョブのファイルとシンボリックリンクは `protected_paths` で守ります）
- `core.history`: `connect_history(db_path) -> sqlite3.Connection`、
  `search_history(conn, date_from=None, date_to=None, keyword="") -> list[sqlite3.Row]`、
  `count_history_before(conn, cutoff_date) -> int`、`delete_history_before(conn, cutoff_date) -> int`
- `core.engine_factory.create_engine(config: TranscriptionConfig) -> TranscriptionEngine`: モデル名でエンジンを選びます
  （`UnifiedTranscriber` が呼びます）

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

`GDriveClient()` は引数なしで呼びます。コンストラクタは `credentials_path` を受け取りますが、属性に保存されるだけで
**認証には使われません**。Drive のサービスは最初に必要になった時点で `get_drive_service()` が初期化し、
その既定値（カレントディレクトリの `credentials.json` / `token.pickle`）を使います。主なメソッド:

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

- `download_audio(url: str, output_path: Optional[str] = None, progress_callback=None) -> Tuple[str, Dict]`:
  YouTube / X 以外の URL は `ValueError`、メタデータが取れないと `RuntimeError`、yt-dlp の出力が 300 秒途絶えると
  `TimeoutError`、音声の抽出に失敗すると `RuntimeError`、出力ファイルが無いと `FileNotFoundError` になります。
  `progress_callback` にはダウンロードの進捗が `ProgressMessage`（率つき）で届きます。
  `metadata` は `title`・`video_id`・`duration`・`url`・`channel`・`upload_date`・`description`
- `extract_video_info(url: str) -> Dict`
- `is_youtube_url(url: str) -> bool` / `is_supported_url(url: str) -> bool`（YouTube または X）
- `cleanup_temp_file(file_path: str)`

yt-dlp まわりの関数（`handlers/youtube.py`）:

- `find_yt_dlp() -> Optional[str]`: PATH → 現在の Python と同じ `bin/` → カレントの `.venv/bin/yt-dlp` の順に探します
- `check_yt_dlp_installed() -> bool`: `find_yt_dlp()` が見つかるか
- `YtDlpNotFoundError(ValueError)`: yt-dlp が見つからない。自動 pip install はせず `uv sync` を案内します
- タイムアウト: `--socket-timeout 30`、メタデータ取得（`extract_video_info`）は 60 秒、`download_audio` は出力が 300 秒途絶えると中断

Google Drive の認証（`handlers/gdrive_auth.py`）:
`get_drive_service(credentials_path: str = "credentials.json", token_path: str = "token.pickle") -> Any`。
スコープは設定の `gdrive.scopes`（省略時は Drive 全体）です。

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

この例が捕捉できるのは、音声が 300 秒以下の Qwen3-ASR、または Whisper の場合です。
Qwen3-ASR は 300 秒を超える音声をチャンクに分割し、**チャンクごとの例外を捕捉して `metadata["failed_chunks"]` に計上する**ため、
長い音声では OOM が呼び出し側へ伝播しません。その場合は、戻り値の `result.metadata["failed_chunks"]` が 0 かを確認してください。

```python
import torch

from core.config import TranscriptionConfig
from core.transcription_interface import UnifiedTranscriber


def safe_transcription(audio_path: str, model: str, fallback_device: str = "cpu"):
    """GPUで失敗した場合にCPUで再試行する"""
    try:
        config = TranscriptionConfig(model=model, device="cuda")
        result = UnifiedTranscriber(config).transcribe(audio_path)
        if (result.metadata or {}).get("failed_chunks"):
            # 長い音声ではチャンク単位で失敗が握りつぶされる。必要なら CPU で再試行する
            print(f"失敗したチャンクがあります: {result.metadata['failed_chunks']}")
        return result
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
from core.logging import get_logger, setup_logging, UnifiedLogger, PerformanceLogger

logger = get_logger(__name__)
```

`core` パッケージはインポートしただけではログを設定しません。エントリポイント（`tc`、`transcribe.py`、`webui.py`）が
起動時に `core.logging.setup_logging() -> None` を呼ぶと、INFO レベルのログがコンソールと `logs/transcription.log`
（pytest 実行中は `logs/transcription_test.log`）へ出力されるように構成されます。
出力先などを変える場合は `UnifiedLogger.configure(log_level, log_file, enable_console, enable_file, log_format)` を使います。
`PerformanceLogger(name)` は処理時間の計測（`start_timing` / `end_timing`）とメトリクス記録（`log_metric`）に使います。

## WebUI向けモジュール

`webui.py`（Streamlit）が使う `core/webui_workflow.py` の主な要素です。

- `start_transcription_job(transcriber: UnifiedTranscriber, audio_path: str, **kwargs) -> TranscriptionJob`:
  文字起こしを別スレッドで実行し、進捗を `progress_queue` で共有します。完了すると `result`（成功）または
  `error`（失敗）が設定され、`done` が `True` になります
- `drain_progress(job) -> List[str]`: 溜まった進捗メッセージを取り出します
- `apply_progress(item: QueueItem, message: str) -> bool`: 率つきメッセージ（`ProgressMessage`）なら項目の
  `progress`（0.0〜1.0）と `progress_text` に反映して `True`、通常のメッセージは `False`（呼び出し側がログへ追記）
- `format_elapsed(seconds: float) -> str`: 経過・残り時間を `m:ss`（1 時間以上は `h:mm:ss`）にします
- `estimate_remaining(elapsed: float, fraction: Optional[float]) -> Optional[float]`: 残り時間（秒）。
  進捗率が不明、または 3% 未満では `None`（進捗バーは Nemotron と短い音声では経過時間のみになります）
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

from core.cli_workflow import cleanup_input_audio, resolve_input_audio
from core.config import TranscriptionConfig
from core.transcription_interface import UnifiedTranscriber

# YouTube / X / Google Drive の URL、またはローカルパスを音声ファイルに解決
resolution = resolve_input_audio("https://youtube.com/watch?v=...", Path("output"))

config = TranscriptionConfig(model="Qwen/Qwen3-ASR-1.7B", language=None)
result = UnifiedTranscriber(config).transcribe(resolution.local_audio_path)
print(result.text)

# 一時ファイルの削除（yt-dlp 由来と Google Drive 由来の音声。ローカル入力は削除されない）
warning = cleanup_input_audio(resolution)   # 削除に失敗したときだけ警告文が返る
if warning:
    print(warning)
```

結果の保存・アップロード・履歴までまとめて行うときは `finalize_transcription` を使います（一時音声の削除も含みます）。

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

# yt-dlp が作った一時音声を削除
yt_client.cleanup_temp_file(audio_path)
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
