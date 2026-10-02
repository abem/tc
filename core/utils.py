"""
Core utility functions and constants.
Centralized location for shared patterns and helpers.
"""

import re
from pathlib import Path
from typing import Dict, Optional

# URL Patterns
YOUTUBE_URL_PATTERNS = [
    r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
    r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
    r'(?:https?://)?youtu\.be/[\w-]+',
    r'(?:https?://)?(?:www\.)?youtube\.com/v/[\w-]+',
    r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
]

GDRIVE_URL_PATTERN = re.compile(r"^https://drive\.google\.com/")
GDRIVE_FILE_ID_PATTERN = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
GDRIVE_OPEN_ID_PATTERN = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")

TWITTER_URL_PATTERNS = [
    r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/\d+',
]


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube URL."""
    for pattern in YOUTUBE_URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False


def is_twitter_url(url: str) -> bool:
    """Check if URL is an X(旧Twitter) status(動画投稿)URL."""
    for pattern in TWITTER_URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False


def is_google_drive_url(url: str) -> bool:
    """Check if URL is a Google Drive URL."""
    return bool(GDRIVE_URL_PATTERN.match(url))


def extract_gdrive_file_id(source: str) -> Optional[str]:
    """Extract Google Drive file ID from URL."""
    direct_match = GDRIVE_FILE_ID_PATTERN.search(source)
    if direct_match:
        return direct_match.group(1)
    open_match = GDRIVE_OPEN_ID_PATTERN.search(source)
    if open_match:
        return open_match.group(1)
    return None


def detect_input_type(source: str) -> Dict[str, str]:
    """Detect whether source is YouTube URL, X(Twitter) URL, Google Drive URL, or local file."""
    if is_youtube_url(source):
        return {"type": "youtube", "source": source}
    if is_twitter_url(source):
        return {"type": "twitter", "source": source}
    if is_google_drive_url(source):
        return {"type": "gdrive", "source": source}
    if Path(source).exists():
        return {"type": "local", "source": source}
    return {"type": "unknown", "source": source}


def load_context_hints(file_path: str) -> str:
    """固有名詞・専門用語のヒントファイルを読み込み、ASRのcontext文字列へ変換する。

    書式: 1行1語彙。空行と'#'始まりの行(コメント)は無視する。
    残った行を', '(カンマ+半角スペース)で結合して1本の文字列にする。

    ファイルが存在しない・内容が空(コメントのみ含む)の場合は""を返す
    (context未設定時と同じ後方互換動作にするため)。
    """
    path = Path(file_path)
    if not path.exists():
        return ""

    hints = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return ", ".join(hints)


def resolve_device(device: str) -> str:
    """Resolve auto device selection to cuda/cpu."""
    if device != "auto":
        return device

    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


DEFAULT_AUDIO_DURATION_SEC = 600.0  # 長さを取得できないときの既定値(10 分)


def get_audio_duration(audio_path: str, fallback_sec: float = DEFAULT_AUDIO_DURATION_SEC) -> float:
    """音声ファイルの長さ(秒)を返す。

    soundfile でヘッダから読み、失敗したら librosa(audioread 経由で mp4/m4a 等も扱える)、
    それも失敗したら `fallback_sec` を返す。例外は呼び出し元へ出さない。
    """
    try:
        import soundfile as sf

        return float(sf.info(audio_path).duration)
    except Exception:
        pass
    try:
        import librosa

        return float(librosa.get_duration(path=audio_path))
    except Exception:
        return fallback_sec


MAX_UPLOAD_FILENAME_LENGTH = 200
DEFAULT_UPLOAD_FILENAME = "upload"


def sanitize_upload_filename(name: object, default: str = DEFAULT_UPLOAD_FILENAME) -> str:
    """アップロードされたファイル名を、区切り文字を含まない単一のファイル名にする。

    クライアントが送るファイル名(Streamlitの`UploadedFile.name`はそのまま通す)に`../`や
    `/`・`\\`が含まれていても、保存先ディレクトリの外へ書き込めないようにする。ディレクトリ部分は
    捨て、末尾の要素だけを使う。制御文字(NUL・改行を含む)は除く。空・`.`・`..`になる場合は
    `default`を返す。長すぎる名前は拡張子を残して切り詰める。
    """
    if not isinstance(name, str):
        return default
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ord(ch) >= 32 and ord(ch) != 127).strip()
    if base in ("", ".", ".."):
        return default
    if len(base) > MAX_UPLOAD_FILENAME_LENGTH:
        stem, dot, ext = base.rpartition(".")
        if dot and 0 < len(ext) <= 20:
            base = stem[: MAX_UPLOAD_FILENAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            base = base[:MAX_UPLOAD_FILENAME_LENGTH]
    return base


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def one_line(value: object, limit: int = 200) -> str:
    """ログや一覧表示に出すための、1 行の文字列にする。

    クライアント由来の文字列(アップロード名・URL)に改行や制御文字が含まれていると、ログに偽の行を
    紛れ込ませたり、端末の制御シーケンスを送り込んだりできる。制御文字は`\\n`・`\\x1b`のように
    見える形のエスケープにし(情報は残す)、`limit`文字を超える分は`…`で切り詰める。
    """
    text = _CONTROL_CHARS_RE.sub(lambda m: m.group().encode("unicode_escape").decode("ascii"), str(value))
    if len(text) > limit:
        text = text[: max(limit - 1, 0)] + "…"
    return text
