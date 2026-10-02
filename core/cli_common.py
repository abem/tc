"""
Shared helpers for CLI entry points.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.utils import (
    detect_input_type,
    extract_gdrive_file_id,
    resolve_device,
)

__all__ = [
    "update_whisper_config",
    "build_output_file",
    "upload_text_to_gdrive_sibling",
    # core.utils からの再エクスポート（webui.py / tc / core/cli_workflow.py が
    # core.cli_common 経由で import している公開名）
    "detect_input_type",
    "resolve_device",
]


def update_whisper_config(base_config: Dict[str, Any], **overrides: Optional[str]) -> Dict[str, Any]:
    """Apply CLI overrides to whisper configuration dict."""
    merged = dict(base_config)
    whisper = dict(merged.get("whisper", {}))

    for key, value in overrides.items():
        if value is not None:
            whisper[key] = value

    merged["whisper"] = whisper
    return merged


def build_output_file(output_dir: Path) -> Path:
    """Build a timestamped output file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{timestamp}_transcription.txt"


def upload_text_to_gdrive_sibling(file_path: Path, original_audio_source: str, override_folder_id: Optional[str] = None) -> Optional[str]:
    """
    Upload a local text file to the same Google Drive folder as original audio source.
    If override_folder_id is provided, use that instead of the sibling folder.
    Returns web URL when successful, otherwise None.
    """
    from handlers.gdrive import GDriveClient

    original_audio_id = extract_gdrive_file_id(original_audio_source)
    if not original_audio_id:
        return None

    client = GDriveClient()
    # 優先順位: override_folder_id > 元ファイルの親フォルダ
    parent_id = override_folder_id if override_folder_id else client.get_parent_folder_id(original_audio_id)
    uploaded_file_id = client.upload_file(
        str(file_path),
        file_path.name,
        parent_id=parent_id,
    )
    return client.get_file_url(uploaded_file_id)
