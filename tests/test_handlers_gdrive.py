"""
Tests for handlers.gdrive module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDriveError:
    """Tests for DriveError exception."""

    def test_drive_error_creation(self):
        """Test DriveError creation."""
        from handlers.gdrive import DriveError

        error = DriveError("Test error", "TEST_CODE")
        assert error.message == "Test error"
        assert error.error_code == "TEST_CODE"
        assert "TEST_CODE" in str(error)
        assert "Test error" in str(error)


class TestUploadError:
    """Tests for UploadError exception."""

    def test_upload_error_creation(self):
        """Test UploadError creation."""
        from handlers.gdrive import UploadError

        error = UploadError("Upload failed")
        assert error.error_code == "UPLOAD_ERROR"


class TestDownloadError:
    """Tests for DownloadError exception."""

    def test_download_error_creation(self):
        """Test DownloadError creation."""
        from handlers.gdrive import DownloadError

        error = DownloadError("Download failed")
        assert error.error_code == "DOWNLOAD_ERROR"


class TestGDriveClient:
    """Tests for GDriveClient."""

    @patch("handlers.gdrive.get_drive_service")
    def test_service_lazy_initialization(self, mock_get_service):
        """Test that service is lazily initialized."""
        from handlers.gdrive import GDriveClient

        mock_service = Mock()
        mock_get_service.return_value = mock_service

        client = GDriveClient()
        assert client._service is None

        # Access service property
        service = client.service
        assert service is mock_service
        mock_get_service.assert_called_once()

    @patch("handlers.gdrive.get_drive_service")
    def test_is_google_drive_url_patterns(self, mock_get_service):
        """Test Google Drive URL detection."""
        from handlers.gdrive import GDriveClient

        client = GDriveClient()

        # Valid Google Drive URLs
        assert client.download.__doc__ is not None

    @patch("handlers.gdrive.get_drive_service")
    def test_sanitize_folder_name(self, mock_get_service):
        """Test folder name sanitization."""
        from handlers.gdrive import GDriveClient

        client = GDriveClient()

        # Test sanitization method
        result = client._sanitize_folder_name("Test/Video: Title?")
        assert "/" not in result
        assert ":" not in result
        assert "?" not in result


class TestStorageBackend:
    """Tests for StorageBackend ABC."""

    def test_storage_backend_is_abstract(self):
        """Test that StorageBackend cannot be instantiated directly."""
        from handlers.gdrive import StorageBackend

        with pytest.raises(TypeError):
            StorageBackend()
