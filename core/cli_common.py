"""
Shared helpers for CLI entry points.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import UnifiedConfig

YOUTUBE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch|youtu\.be/)"
)
GDRIVE_URL_PATTERN = re.compile(r"^https://drive\.google\.com/")
GDRIVE_FILE_ID_PATTERN = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
GDRIVE_OPEN_ID_PATTERN = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


def detect_input_type(source: str) -> Dict[str, str]:
    """Detect whether source is YouTube URL, Google Drive URL, or local file."""
    if YOUTUBE_URL_PATTERN.match(source):
        return {"type": "youtube", "source": source}
    if GDRIVE_URL_PATTERN.match(source):
        return {"type": "gdrive", "source": source}
    if Path(source).exists():
        return {"type": "local", "source": source}
    return {"type": "unknown", "source": source}


def is_google_drive_url(source: str) -> bool:
    """Return True when source is a Google Drive URL."""
    return bool(GDRIVE_URL_PATTERN.match(source))


def extract_gdrive_file_id(source: str) -> str:
    """Extract Google Drive file ID from URL, or return input as-is when already ID."""
    direct_match = GDRIVE_FILE_ID_PATTERN.search(source)
    if direct_match:
        return direct_match.group(1)
    open_match = GDRIVE_OPEN_ID_PATTERN.search(source)
    if open_match:
        return open_match.group(1)
    return source


def resolve_device(device: str) -> str:
    """Resolve auto device selection to cuda/cpu."""
    if device != "auto":
        return device

    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def select_model(language: str, override_model: Optional[str] = None) -> str:
    """Select model using config defaults and language fallback."""
    if override_model:
        return override_model

    language_models = UnifiedConfig.get("whisper", "language_models", default={})
    language_config = language_models.get(language, {})
    selected = language_config.get("default")
    if selected:
        return selected

    return "openai/whisper-large-v3" if language == "en" else "kotoba-tech/kotoba-whisper-v2.2"


def update_whisper_config(base_config: Dict[str, Any], **overrides: Optional[str]) -> Dict[str, Any]:
    """Apply CLI overrides to whisper configuration dict."""
    merged = dict(base_config)
    whisper = dict(merged.get("whisper", {}))

    for key, value in overrides.items():
        if value is not None:
            whisper[key] = value

    merged["whisper"] = whisper
    return merged


def build_output_file(output_dir: Path, diarization_enabled: bool = False) -> Path:
    """Build a timestamped output file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_with_speakers" if diarization_enabled else ""
    return output_dir / f"{timestamp}_transcription{suffix}.txt"
