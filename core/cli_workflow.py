"""
Shared workflow helpers for CLI entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core.cli_common import detect_input_type, upload_text_to_gdrive_sibling

StatusCallback = Callable[[str], None]


@dataclass
class InputResolution:
    source_type: str
    original_source: str
    local_audio_path: str
    is_temp_file: bool
    metadata: Optional[Dict[str, Any]]
    youtube_handler: Optional[Any]  # YouTubeClient


def resolve_input_audio(
    source: str,
    output_dir: Path,
    *,
    ensure_yt_dlp: bool = False,
    on_status: Optional[StatusCallback] = None,
) -> InputResolution:
    """Resolve input source to a local audio path."""
    detected = detect_input_type(source)
    source_type = detected["type"]

    def status(message: str) -> None:
        if on_status:
            on_status(message)

    if source_type in ("youtube", "twitter"):
        status("YouTube URLを検出" if source_type == "youtube" else "X(Twitter)動画URLを検出")
        from handlers.youtube import YouTubeClient, check_yt_dlp_installed, install_yt_dlp

        if ensure_yt_dlp and not check_yt_dlp_installed():
            status("yt-dlpがインストールされていないためインストールを試行します")
            install_yt_dlp()

        youtube_handler = YouTubeClient(output_dir=str(output_dir))
        local_audio_path, metadata = youtube_handler.download_audio(source)
        return InputResolution(
            source_type=source_type,
            original_source=source,
            local_audio_path=local_audio_path,
            is_temp_file=True,
            metadata=metadata,
            youtube_handler=youtube_handler,
        )

    if source_type == "gdrive":
        status("Google Drive URLを検出、ダウンロードを開始")
        from handlers.gdrive import GDriveClient

        client = GDriveClient()
        local_audio_path = str(client.download(source))
        return InputResolution(
            source_type="gdrive",
            original_source=source,
            local_audio_path=local_audio_path,
            is_temp_file=False,
            metadata=None,
            youtube_handler=None,
        )

    if source_type == "local":
        return InputResolution(
            source_type="local",
            original_source=source,
            local_audio_path=detected["source"],
            is_temp_file=False,
            metadata=None,
            youtube_handler=None,
        )

    raise ValueError(f"入力を認識できません: {source}")


def upload_transcription_result(
    *,
    source_type: str,
    original_source: str,
    output_file: Path,
    metadata: Optional[Dict[str, Any]] = None,
    folder_id: Optional[str] = None,
) -> Optional[str]:
    """Upload transcription result based on source type and return URL if available.

    Args:
        source_type: Type of source (youtube, gdrive, local)
        original_source: Original source URL or path
        output_file: Path to output file
        metadata: YouTube metadata (required for YouTube sources)
        folder_id: Override folder ID for upload destination

    Returns:
        File URL if successful, None otherwise
    """
    if source_type == "youtube":
        if not metadata:
            return None
        from handlers.gdrive import GDriveClient

        gdrive_client = GDriveClient()
        upload_result = gdrive_client.upload_youtube_transcription(str(output_file), metadata)
        if upload_result:
            return upload_result.get("file_url")
        return None

    if source_type == "gdrive":
        return upload_text_to_gdrive_sibling(output_file, original_source, override_folder_id=folder_id)

    return None
