"""
Tests for core.utils module.
"""


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


class TestTwitterUrlDetection:
    """Tests for X(Twitter) URL detection."""

    def test_is_twitter_url_valid(self):
        """Test valid X(Twitter) status URLs."""
        from core.utils import is_twitter_url

        assert is_twitter_url("https://x.com/hanakoxbt/status/2083602828744859845/video/1")
        assert is_twitter_url("https://x.com/hanakoxbt/status/2083602828744859845")
        assert is_twitter_url("https://twitter.com/hanakoxbt/status/2083602828744859845")
        assert is_twitter_url("https://www.twitter.com/hanakoxbt/status/2083602828744859845")

    def test_is_twitter_url_invalid(self):
        """Test invalid X(Twitter) URLs."""
        from core.utils import is_twitter_url

        assert not is_twitter_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert not is_twitter_url("https://drive.google.com/file/d/123")
        assert not is_twitter_url("https://x.com/hanakoxbt")  # ステータスIDなし
        assert not is_twitter_url("/local/path/to/file.mp3")
        assert not is_twitter_url("")


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

    def test_detect_twitter(self):
        """Test X(Twitter) URL detection."""
        from core.utils import detect_input_type

        result = detect_input_type("https://x.com/hanakoxbt/status/2083602828744859845/video/1")
        assert result["type"] == "twitter"

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


class TestLoadContextHints:
    """Tests for context hints file loading."""

    def test_nonexistent_file_returns_empty(self):
        """Test that a missing file returns empty string (backward compat)."""
        from core.utils import load_context_hints

        result = load_context_hints("/nonexistent/path/to/context_hints.txt")
        assert result == ""

    def test_empty_file_returns_empty(self):
        """Test that an empty file returns empty string."""
        from core.utils import load_context_hints
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            temp_path = f.name

        try:
            result = load_context_hints(temp_path)
            assert result == ""
        finally:
            os.unlink(temp_path)

    def test_comments_and_blank_lines_only_returns_empty(self):
        """Test that a file with only comments/blank lines returns empty string."""
        from core.utils import load_context_hints
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("# comment line\n\n# another comment\n   \n")
            temp_path = f.name

        try:
            result = load_context_hints(temp_path)
            assert result == ""
        finally:
            os.unlink(temp_path)

    def test_hints_joined_with_comma_space(self):
        """Test that valid hint lines are joined with ', '."""
        from core.utils import load_context_hints
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("# comment\n田中太郎\n\nGAZOO Racing\n  スーパーGT  \n")
            temp_path = f.name

        try:
            result = load_context_hints(temp_path)
            assert result == "田中太郎, GAZOO Racing, スーパーGT"
        finally:
            os.unlink(temp_path)


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

    def test_resolve_auto(self):
        """Test auto device resolution."""
        from core.utils import resolve_device

        result = resolve_device("auto")
        # Should be either cuda or cpu depending on system
        assert result in ["cuda", "cpu"]


class TestGetAudioDuration:
    """core.utils.get_audio_duration(3 エンジンが共有する音声長の取得)。"""

    @staticmethod
    def _write_wav(path, seconds, sample_rate=8000):
        import wave

        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * int(seconds * sample_rate))

    def test_reads_duration_of_real_wav(self, tmp_path):
        from core.utils import get_audio_duration

        wav = tmp_path / "a.wav"
        self._write_wav(wav, 2.5)
        assert get_audio_duration(str(wav)) == 2.5

    def test_missing_file_returns_default_fallback(self, tmp_path):
        from core.utils import DEFAULT_AUDIO_DURATION_SEC, get_audio_duration

        assert DEFAULT_AUDIO_DURATION_SEC == 600.0
        assert get_audio_duration(str(tmp_path / "none.wav")) == 600.0

    def test_custom_fallback_is_used(self, tmp_path):
        from core.utils import get_audio_duration

        assert get_audio_duration(str(tmp_path / "none.wav"), fallback_sec=12.0) == 12.0

    def test_unreadable_file_returns_fallback(self, tmp_path):
        from core.utils import get_audio_duration

        bad = tmp_path / "bad.wav"
        bad.write_bytes(b"not audio")
        assert get_audio_duration(str(bad), fallback_sec=7.0) == 7.0

    def test_falls_back_to_librosa_when_soundfile_fails(self, tmp_path, monkeypatch):
        import soundfile
        import librosa
        from core.utils import get_audio_duration

        def boom(path):
            raise RuntimeError("soundfile cannot read this")

        monkeypatch.setattr(soundfile, "info", boom)
        monkeypatch.setattr(librosa, "get_duration", lambda path: 42.0)
        assert get_audio_duration(str(tmp_path / "x.m4a")) == 42.0

