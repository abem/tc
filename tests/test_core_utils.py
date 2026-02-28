"""
Tests for core.utils module.
"""

import pytest


class TestYouTubeUrlDetection:
    """Tests for YouTube URL detection."""

    def test_is_youtube_url_valid(self):
        """Test valid YouTube URLs."""
        from core.utils import is_youtube_url

        assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ")
        assert is_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ")
        assert is_youtube_url("https://www.youtube.com/v/dQw4w9WgXcQ")
        assert is_youtube_url("https://www.youtube.com/shorts/abc123")

    def test_is_youtube_url_invalid(self):
        """Test invalid YouTube URLs."""
        from core.utils import is_youtube_url

        assert not is_youtube_url("https://drive.google.com/file/d/123")
        assert not is_youtube_url("https://example.com/video")
        assert not is_youtube_url("/local/path/to/file.mp3")
        assert not is_youtube_url("")


class TestGoogleDriveUrlDetection:
    """Tests for Google Drive URL detection."""

    def test_is_google_drive_url_valid(self):
        """Test valid Google Drive URLs."""
        from core.utils import is_google_drive_url

        assert is_google_drive_url("https://drive.google.com/file/d/abc123/view")
        assert is_google_drive_url("https://drive.google.com/open?id=abc123")

    def test_is_google_drive_url_invalid(self):
        """Test invalid Google Drive URLs."""
        from core.utils import is_google_drive_url

        assert not is_google_drive_url("https://youtube.com/watch?v=abc123")
        assert not is_google_drive_url("https://example.com/file")
        assert not is_google_drive_url("/local/path")


class TestExtractGdriveFileId:
    """Tests for Google Drive file ID extraction."""

    def test_extract_from_file_url(self):
        """Test extraction from /file/d/ URL."""
        from core.utils import extract_gdrive_file_id

        result = extract_gdrive_file_id("https://drive.google.com/file/d/abc123xyz/view")
        assert result == "abc123xyz"

    def test_extract_from_open_url(self):
        """Test extraction from /open?id= URL."""
        from core.utils import extract_gdrive_file_id

        result = extract_gdrive_file_id("https://drive.google.com/open?id=abc123xyz")
        assert result == "abc123xyz"

    def test_extract_returns_none_for_non_gdrive(self):
        """Test that non-GDrive URLs return None."""
        from core.utils import extract_gdrive_file_id

        result = extract_gdrive_file_id("https://youtube.com/watch?v=abc")
        assert result is None


class TestDetectInputType:
    """Tests for input type detection."""

    def test_detect_youtube(self):
        """Test YouTube URL detection."""
        from core.utils import detect_input_type

        result = detect_input_type("https://youtube.com/watch?v=abc123")
        assert result["type"] == "youtube"

    def test_detect_gdrive(self):
        """Test Google Drive URL detection."""
        from core.utils import detect_input_type

        result = detect_input_type("https://drive.google.com/file/d/abc123/view")
        assert result["type"] == "gdrive"

    def test_detect_local_existing_file(self):
        """Test local file detection for existing file."""
        from core.utils import detect_input_type
        import tempfile
        import os

        # Create a temp file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            result = detect_input_type(temp_path)
            assert result["type"] == "local"
        finally:
            os.unlink(temp_path)

    def test_detect_unknown(self):
        """Test unknown input detection."""
        from core.utils import detect_input_type

        result = detect_input_type("/nonexistent/path/to/file.mp3")
        assert result["type"] == "unknown"


class TestResolveDevice:
    """Tests for device resolution."""

    def test_resolve_explicit_cuda(self):
        """Test explicit cuda device."""
        from core.utils import resolve_device

        result = resolve_device("cuda")
        assert result == "cuda"

    def test_resolve_explicit_cpu(self):
        """Test explicit cpu device."""
        from core.utils import resolve_device

        result = resolve_device("cpu")
        assert result == "cpu"

    @pytest.mark.skip(reason="Requires torch which may not be installed")
    def test_resolve_auto(self):
        """Test auto device resolution."""
        from core.utils import resolve_device

        result = resolve_device("auto")
        # Should be either cuda or cpu depending on system
        assert result in ["cuda", "cpu"]
