#!/usr/bin/env python3
"""
Unified Google Drive client.
Consolidates GDriveHandler, YouTubeGDriveHandler, and GDriveStorageHandler.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional, Dict, Any, Union

from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload, MediaFileUpload

from config import get_drive_service
from core.config import UnifiedConfig
from core.logging import get_logger

logger = get_logger(__name__)


class DriveError(Exception):
    """Google Drive operation error."""
    def __init__(self, message: str, error_code: str = "UNKNOWN"):
        self.message = message
        self.error_code = error_code
        super().__init__(f"{error_code}: {message}")


class UploadError(DriveError):
    """Upload operation error."""
    def __init__(self, message: str, error_code: str = "UPLOAD_ERROR"):
        super().__init__(message, error_code)


class DownloadError(DriveError):
    """Download operation error."""
    def __init__(self, message: str, error_code: str = "DOWNLOAD_ERROR"):
        super().__init__(message, error_code)


class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def download(self, file_id_or_path: str) -> Path:
        pass

    @abstractmethod
    def upload(self, file_path: Path, parent_id: Optional[str] = None) -> Optional[str]:
        pass


class GDriveClient(StorageBackend):
    """
    Unified Google Drive client.
    Handles file operations, folder management, and YouTube-specific uploads.
    """

    def __init__(self, credentials_path: str = "credentials.json"):
        self.credentials_path = credentials_path
        self._service = None
        self._base_folder_id = None
        self.base_folder_name = "ボイス共有"

    @property
    def service(self):
        """Lazy initialization of Drive service."""
        if self._service is None:
            self._service = get_drive_service()
        return self._service

    # =====================
    # Basic File Operations
    # =====================

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """Get file metadata."""
        try:
            return self.service.files().get(
                fileId=file_id,
                fields="id, name, size, parents"
            ).execute()
        except Exception as e:
            logger.error(f"Failed to get metadata: {e}")
            raise

    def get_file_url(self, file_id: str) -> Optional[str]:
        """Get file URL."""
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields="webViewLink"
            ).execute()
            return file.get("webViewLink")
        except Exception as e:
            logger.error(f"Failed to get file URL: {e}")
            return None

    def get_parent_folder_id(self, file_id: str) -> Optional[str]:
        """Get parent folder ID for a file."""
        try:
            file_metadata = self.service.files().get(
                fileId=file_id,
                fields='parents'
            ).execute()

            parents = file_metadata.get('parents')
            if parents:
                logger.info(f"Parent folder ID for {file_id}: {parents[0]}")
                return parents[0]
            else:
                logger.warning(f"No parent folder found for file {file_id}")
                return None
        except Exception as e:
            logger.error(f"Failed to get parent folder ID: {e}")
            return None

    def download_file(self, file_id: str, output_path: str) -> None:
        """Download file from Google Drive."""
        try:
            request = self.service.files().get_media(fileId=file_id)
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.info(f"Download progress: {int(status.progress() * 100)}%")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise DownloadError(f"Failed to download file: {e}")

    def upload_file(
        self,
        file_content: Union[str, Path, io.BytesIO],
        filename: str,
        parent_id: Optional[str] = None,
        mimetype: str = "text/plain"
    ) -> str:
        """Upload file to Google Drive."""
        try:
            file_metadata = {
                "name": filename,
                "mimeType": mimetype
            }
            if parent_id:
                file_metadata["parents"] = [parent_id]

            if isinstance(file_content, io.BytesIO):
                file_content.seek(0)
                media_body_content = file_content
                logger.info(f"Uploading from BytesIO: {filename}")
            elif isinstance(file_content, (str, Path)):
                file_path_obj = Path(file_content)
                if not file_path_obj.is_file():
                    raise FileNotFoundError(f"File not found: {file_path_obj}")
                media_body_content = io.FileIO(str(file_path_obj), "rb")
                logger.info(f"Uploading from file: {file_path_obj}")
            else:
                raise TypeError("file_content must be str, Path, or BytesIO")

            media = MediaIoBaseUpload(
                media_body_content,
                mimetype=mimetype,
                resumable=True,
                chunksize=1024*1024
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True
            ).execute()

            logger.info(f"File uploaded: {file.get('webViewLink')}")
            return file.get("id")

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise UploadError(f"Failed to upload file: {e}")

    def stream_file_chunks(
        self,
        file_id: str,
        chunk_size_mb: Optional[int] = None
    ) -> Generator[bytes, None, None]:
        """Stream file in chunks."""
        if chunk_size_mb is None:
            chunk_size_mb = UnifiedConfig.get('gdrive', 'chunk_size', default=100)

        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False

            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")

                if fh.getbuffer().nbytes >= chunk_size_mb * 1024 * 1024 or done:
                    fh.seek(0)
                    chunk_data = fh.getvalue()
                    fh = io.BytesIO()
                    yield chunk_data

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            raise

    # =====================
    # Folder Operations
    # =====================

    def find_folder_by_name(
        self,
        folder_name: str,
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """Find folder by name."""
        try:
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])
            if files:
                logger.info(f"Folder '{folder_name}' found: {files[0]['id']}")
                return files[0]['id']
            else:
                logger.info(f"Folder '{folder_name}' not found")
                return None

        except Exception as e:
            logger.error(f"Folder search error: {e}")
            return None

    def create_folder(
        self,
        folder_name: str,
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """Create folder."""
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            if parent_id:
                folder_metadata['parents'] = [parent_id]

            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()

            folder_id = folder.get('id')
            logger.info(f"Folder '{folder_name}' created: {folder_id}")
            return folder_id

        except Exception as e:
            logger.error(f"Folder creation error: {e}")
            return None

    def find_or_create_folder(
        self,
        folder_name: str,
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """Find or create folder."""
        folder_id = self.find_folder_by_name(folder_name, parent_id)
        if not folder_id:
            folder_id = self.create_folder(folder_name, parent_id)
        return folder_id

    # =====================
    # YouTube-Specific Operations
    # =====================

    def _sanitize_folder_name(self, title: str) -> str:
        """Sanitize folder name."""
        sanitized = re.sub(r'[^\w\s\-_\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\u3400-\u4DBF]', '', title)
        sanitized = re.sub(r'\s+', ' ', sanitized)
        sanitized = sanitized.strip()
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        return sanitized

    def _get_or_create_base_folder(self) -> Optional[str]:
        """Get or create base folder for YouTube uploads."""
        if self._base_folder_id:
            return self._base_folder_id

        folder_id = self.find_folder_by_name(self.base_folder_name)
        if not folder_id:
            logger.info(f"Creating base folder '{self.base_folder_name}'")
            folder_id = self.create_folder(self.base_folder_name)

        self._base_folder_id = folder_id
        return folder_id

    def _get_or_create_date_folder(self, youtube_title: str) -> Optional[str]:
        """Get or create date-prefixed folder for YouTube uploads."""
        base_folder_id = self._get_or_create_base_folder()
        if not base_folder_id:
            logger.error("Failed to get/create base folder")
            return None

        today = datetime.now()
        date_prefix = today.strftime("%y_%m_%d")
        sanitized_title = self._sanitize_folder_name(youtube_title)
        folder_name = f"{date_prefix}_{sanitized_title}"

        folder_id = self.find_folder_by_name(folder_name, base_folder_id)
        if not folder_id:
            logger.info(f"Creating date folder '{folder_name}'")
            folder_id = self.create_folder(folder_name, base_folder_id)

        return folder_id

    def upload_youtube_transcription(
        self,
        file_path: str,
        youtube_metadata: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        Upload YouTube transcription result to organized folder.

        Args:
            file_path: Path to transcription file
            youtube_metadata: YouTube video metadata

        Returns:
            Upload info dict or None on failure
        """
        try:
            youtube_title = youtube_metadata.get('title', 'unknown_video')
            video_id = youtube_metadata.get('video_id', 'unknown')

            logger.info(f"Uploading transcription for '{youtube_title}'")

            target_folder_id = self._get_or_create_date_folder(youtube_title)
            if not target_folder_id:
                logger.error("Failed to get/create target folder")
                return None

            file_name = Path(file_path).name

            file_metadata = {
                'name': file_name,
                'parents': [target_folder_id],
                'description': f'YouTube transcription\n'
                             f'Title: {youtube_title}\n'
                             f'Video ID: {video_id}\n'
                             f'Channel: {youtube_metadata.get("channel", "unknown")}\n'
                             f'Duration: {youtube_metadata.get("duration", 0)}s\n'
                             f'Uploaded: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
            }

            media = MediaFileUpload(
                file_path,
                mimetype='text/plain',
                resumable=True
            )

            file_result = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()

            file_id = file_result.get('id')
            file_url = file_result.get('webViewLink')

            logger.info(f"Upload complete: {file_name}")
            logger.info(f"File URL: {file_url}")

            return {
                'file_id': file_id,
                'file_url': file_url,
                'file_name': file_name,
                'folder_id': target_folder_id
            }

        except Exception as e:
            logger.error(f"YouTube transcription upload error: {e}")
            return None

    # =====================
    # StorageBackend Interface
    # =====================

    def download(self, file_id_or_url: str) -> Path:
        """Download from URL or file ID (StorageBackend interface)."""
        m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', file_id_or_url)
        file_id = m.group(1) if m else file_id_or_url

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            self.download_file(file_id, tmp.name)
            return Path(tmp.name)

    def upload(self, file_path: Path, parent_id: Optional[str] = None) -> Optional[str]:
        """Upload file (StorageBackend interface)."""
        return self.upload_file(
            file_content=str(file_path),
            filename=file_path.name,
            parent_id=parent_id
        )


# Legacy aliases for backward compatibility
GDriveHandler = GDriveClient
GDriveStorageHandler = GDriveClient
YouTubeGDriveHandler = GDriveClient
