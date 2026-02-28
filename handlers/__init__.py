"""
Handlers for external services (Google Drive, YouTube).

This package provides unified interfaces for:
- Google Drive operations (upload, download, folder management)
- YouTube operations (audio extraction, metadata)
"""

from .gdrive import GDriveClient, DriveError, UploadError, DownloadError
from .youtube import YouTubeClient

__all__ = [
    'GDriveClient',
    'DriveError',
    'UploadError',
    'DownloadError',
    'YouTubeClient',
]
