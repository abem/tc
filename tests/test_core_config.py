"""
Tests for core.config module.
"""

import pytest
from unittest.mock import patch, mock_open


class TestTranscriptionConfig:
    """Tests for TranscriptionConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        from core.config import TranscriptionConfig

        config = TranscriptionConfig()
        assert config.model == "large-v3"
        # device のデフォルトは環境依存(cuda が有効なら "cuda"、否则 "cpu")
        assert config.device in ("cuda", "cpu")
        assert config.language == "ja"

    def test_custom_values(self):
        """Test custom configuration values."""
        from core.config import TranscriptionConfig

        config = TranscriptionConfig(
            model="openai/whisper-large-v3",
            device="cuda",
            language="en"
        )
        assert config.model == "openai/whisper-large-v3"
        assert config.device == "cuda"
        assert config.language == "en"


class TestDiarizationConfig:
    """Tests for DiarizationConfig."""

    def test_default_values(self):
        """Test default diarization configuration."""
        from core.config import DiarizationConfig

        config = DiarizationConfig()
        assert config.enable_diarization is False
        assert config.model_name == "pyannote/speaker-diarization-3.1"

    def test_custom_values(self):
        """Test custom diarization configuration."""
        from core.config import DiarizationConfig

        config = DiarizationConfig(
            enable_diarization=True,
            max_speakers=4
        )
        assert config.enable_diarization is True
        assert config.max_speakers == 4


class TestUnifiedConfig:
    """Tests for UnifiedConfig."""

    def test_load_yaml(self):
        """Test loading configuration from YAML."""
        from core.config import UnifiedConfig

        yaml_content = """
whisper:
  model: test-model
  device: cpu
"""
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("os.path.exists", return_value=True):
                UnifiedConfig._config_data = None  # Reset cache
                UnifiedConfig.load("config/test.yaml")
                # Config should be loaded
                assert UnifiedConfig._config_data is not None

    def test_get_nested_value(self):
        """Test getting nested configuration values."""
        from core.config import UnifiedConfig

        UnifiedConfig._config_data = {
            "whisper": {
                "model": "test-model",
                "language_models": {
                    "ja": {"default": "kotoba-whisper"}
                }
            }
        }

        result = UnifiedConfig.get("whisper", "model")
        assert result == "test-model"

        result = UnifiedConfig.get("whisper", "language_models", "ja", "default")
        assert result == "kotoba-whisper"

    def test_get_with_default(self):
        """Test getting value with default fallback."""
        from core.config import UnifiedConfig

        UnifiedConfig._config_data = {"whisper": {}}

        result = UnifiedConfig.get("whisper", "nonexistent", default="default-value")
        assert result == "default-value"
