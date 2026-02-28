"""
Tests for handlers.youtube module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestYouTubeClient:
    """Tests for YouTubeClient."""

    def test_is_youtube_url_valid(self):
        """Test valid YouTube URL detection."""
        from handlers.youtube import YouTubeClient

        client = YouTubeClient()

        # Valid YouTube URLs
        assert client.is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert client.is_youtube_url("https://youtu.be/dQw4w9WgXcQ")
        assert client.is_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert client.is_youtube_url("https://www.youtube.com/shorts/abc123")

    def test_is_youtube_url_invalid(self):
        """Test invalid YouTube URL detection."""
        from handlers.youtube import YouTubeClient

        client = YouTubeClient()

        # Invalid URLs
        assert not client.is_youtube_url("https://drive.google.com/file/d/123")
        assert not client.is_youtube_url("https://example.com/video")
        assert not client.is_youtube_url("/local/path/to/file.mp3")

    def test_output_dir_default(self):
        """Test default output directory."""
        from handlers.youtube import YouTubeClient
        import tempfile

        client = YouTubeClient()
        assert client.output_dir == tempfile.gettempdir()

    def test_output_dir_custom(self):
        """Test custom output directory."""
        from handlers.youtube import YouTubeClient

        client = YouTubeClient(output_dir="/custom/path")
        assert client.output_dir == "/custom/path"

    @patch("subprocess.run")
    def test_extract_video_info(self, mock_run):
        """Test video info extraction."""
        from handlers.youtube import YouTubeClient

        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"title": "Test Video", "id": "abc123", "duration": 300}'
        )

        client = YouTubeClient()
        info = client.extract_video_info("https://youtube.com/watch?v=abc123")

        assert info["title"] == "Test Video"
        assert info["id"] == "abc123"
        assert info["duration"] == 300

    @patch("subprocess.run")
    def test_extract_video_info_failure(self, mock_run):
        """Test video info extraction failure."""
        from handlers.youtube import YouTubeClient

        mock_run.return_value = Mock(
            returncode=1,
            stderr="Error"
        )

        client = YouTubeClient()
        info = client.extract_video_info("https://youtube.com/watch?v=abc123")

        assert info == {}

    def test_cleanup_temp_file_existing(self):
        """Test cleanup of existing temp file."""
        from handlers.youtube import YouTubeClient
        import tempfile
        import os

        # Create a temp file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        assert os.path.exists(temp_path)

        client = YouTubeClient()
        client.cleanup_temp_file(temp_path)

        assert not os.path.exists(temp_path)


class TestCheckYtDlpInstalled:
    """Tests for check_yt_dlp_installed function."""

    @patch("subprocess.run")
    def test_installed(self, mock_run):
        """Test when yt-dlp is installed."""
        from handlers.youtube import check_yt_dlp_installed

        mock_run.return_value = Mock(returncode=0)
        assert check_yt_dlp_installed() is True

    @patch("subprocess.run")
    def test_not_installed(self, mock_run):
        """Test when yt-dlp is not installed."""
        from handlers.youtube import check_yt_dlp_installed

        mock_run.side_effect = FileNotFoundError()
        assert check_yt_dlp_installed() is False


class TestYouTubeHandlerAlias:
    """Tests for backward compatibility alias."""

    def test_youtube_handler_alias(self):
        """Test that YouTubeHandler is an alias for YouTubeClient."""
        from handlers.youtube import YouTubeHandler, YouTubeClient

        assert YouTubeHandler is YouTubeClient
