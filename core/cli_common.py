"""
Shared helpers for CLI entry points.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import UnifiedConfig
from core.utils import (
    detect_input_type,
    extract_gdrive_file_id,
    is_google_drive_url,
    resolve_device,
)


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


def upload_text_to_gdrive_sibling(file_path: Path, original_audio_source: str) -> Optional[str]:
    """
    Upload a local text file to the same Google Drive folder as original audio source.
    Returns web URL when successful, otherwise None.
    """
    from handlers.gdrive import GDriveClient

    original_audio_id = extract_gdrive_file_id(original_audio_source)
    if not original_audio_id:
        return None

    client = GDriveClient()
    parent_id = client.get_parent_folder_id(original_audio_id)
    uploaded_file_id = client.upload_file(
        str(file_path),
        file_path.name,
        parent_id=parent_id,
    )
    return client.get_file_url(uploaded_file_id)
