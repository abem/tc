"""
Unified configuration management for transcription system.
Consolidates all configuration classes into a single, authoritative source.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import yaml


def _cuda_is_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return torch.cuda.is_available()


@dataclass
class TranscriptionConfig:
    """Unified configuration for all transcription components."""
    
    # Core model settings
    model: str = "large-v3"
    # None(またはconfig.yaml上のnull)は自動言語判定を意味する(2026-08-03)。
    # Qwen3ASREngineのlang_map.get(self.config.language, None)は未知の値/None
    # いずれでもNoneへ解決されqwen_asrへlanguage=Noneとして渡る(自動判定)。
    # WhisperTranscriptionEngineもgenerate()へそのまま渡す(HF Whisperの
    # 標準的な自動判定サポートに委ねる)。既定値自体は後方互換のため"ja"のまま。
    language: Optional[str] = "ja"
    device: str = field(default_factory=lambda: "cuda" if _cuda_is_available() else "cpu")
    # 固有名詞・専門用語の認識ヒント文字列(Qwen3-ASRのcontext引数に相当。
    # WhisperTranscriptionEngineは未対応/無視)。空文字がデフォルトで後方互換。
    context: str = ""
    # タイムスタンプ付与(bugfix 2026-08-03でQwen3ASREngineに実配線するまでは
    # どこからも参照されないdeadフィールドだった)。ForcedAligner追加ロードを
    # 伴うオプトイン機能のため、既存の出力形式を壊さないようデフォルトFalse。
    include_timestamps: bool = False

    @classmethod
    def for_language(cls, language: str, quality: str = "high") -> 'TranscriptionConfig':
        """Create config with the model preset for a specific language.

        quality は互換のために受け付ける引数で、現在は結果に影響しない。
        """
        config = cls(language=language)
        
        if language == "ja":
            config.model = "kotoba-tech/kotoba-whisper-v2.2"
        elif language == "en":
            config.model = "openai/whisper-large-v3"
        else:
            config.model = "openai/whisper-large-v3"  # fallback

        return config


@dataclass
class SystemConfig:
    """System-wide configuration settings."""
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    enable_file_logging: bool = True
    
    # Cache settings
    cache_dir: str = ".cache"
    max_disk_cache_gb: float = 10.0
    
    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 8080
    
    # Security
    max_file_size_mb: float = 500.0
    allowed_file_types: List[str] = field(default_factory=lambda: [
        ".wav", ".mp3", ".mp4", ".m4a", ".flac", ".ogg"
    ])


@dataclass
class UnifiedConfig:
    """Master configuration containing all subsystem configs."""
    
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    
    _config_data: Optional[Dict[str, Any]] = None
    
    @classmethod
    def load(cls, config_path: str = "config/config.yaml") -> None:
        """Load configuration from YAML file."""
        with open(config_path, 'r', encoding='utf-8') as f:
            cls._config_data = yaml.safe_load(f)
    
    @classmethod 
    def get(cls, *keys, default=None) -> Any:
        """Get configuration value using dot notation."""
        if cls._config_data is None:
            cls.load()
        
        d = cls._config_data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d
