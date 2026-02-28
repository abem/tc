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

YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch|youtu\.be/)"
)

GDRIVE_URL_PATTERN = re.compile(r"^https://drive\.google\.com/")
GDRIVE_FILE_ID_PATTERN = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
GDRIVE_OPEN_ID_PATTERN = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube URL."""
    for pattern in YOUTUBE_URL_PATTERNS:
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
    """Detect whether source is YouTube URL, Google Drive URL, or local file."""
    if is_youtube_url(source):
        return {"type": "youtube", "source": source}
    if is_google_drive_url(source):
        return {"type": "gdrive", "source": source}
    if Path(source).exists():
        return {"type": "local", "source": source}
    return {"type": "unknown", "source": source}


def resolve_device(device: str) -> str:
    """Resolve auto device selection to cuda/cpu."""
    if device != "auto":
        return device

    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"
