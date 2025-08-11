"""
Unified configuration management for transcription system.
Consolidates all configuration classes into a single, authoritative source.
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, List
import torch
import yaml
from pathlib import Path


@dataclass
class TranscriptionConfig:
    """Unified configuration for all transcription components."""
    
    # Core model settings
    model: str = "large-v3"
    language: str = "ja"
    device: str = field(default_factory=lambda: "cuda" if torch.cuda.is_available() else "cpu")
    compute_type: str = "float16"
    
    # Processing settings
    chunk_size: int = 1024
    temperature: float = 0.0
    beam_size: int = 5
    best_of: int = 3
    
    # Performance settings
    optimal_batch_size: int = 8
    max_cache_size: int = 5
    enable_async: bool = True
    memory_efficiency: bool = True
    performance_monitoring: bool = True
    
    # Advanced GPU optimization (RTX 4080)
    enable_multi_stream: bool = True
    enable_dynamic_memory_pool: bool = True
    enable_pipeline_parallel: bool = True
    max_concurrent_streams: int = 4
    memory_pool_size: int = 12  # GB
    enable_tensor_sharing: bool = True
    
    # Output formatting
    max_line_length: int = 80
    include_timestamps: bool = True
    timestamp_format: str = "elapsed"  # elapsed/absolute/relative
    
    # UI and progress
    show_progress: bool = True
    progress_bar: bool = True
    segment_callback: Optional[Callable] = None
    
    # Temporary storage
    temp_chunk_dir: Optional[str] = None
    
    @classmethod
    def for_language(cls, language: str, quality: str = "high") -> 'TranscriptionConfig':
        """Create optimized config for specific language."""
        config = cls(language=language)
        
        if language == "ja":
            config.model = "kotoba-tech/kotoba-whisper-v2.2"
        elif language == "en":
            config.model = "openai/whisper-large-v3"
        else:
            config.model = "openai/whisper-large-v3"  # fallback
            
        # Quality adjustments
        if quality == "high":
            config.beam_size = 5
            config.best_of = 3
            config.temperature = 0.0
        elif quality == "balanced":
            config.beam_size = 3
            config.best_of = 2
            config.temperature = 0.1
        elif quality == "fast":
            config.beam_size = 1
            config.best_of = 1
            config.temperature = 0.2
            
        return config
    
    @classmethod
    def for_device(cls, device: str) -> 'TranscriptionConfig':
        """Create optimized config for specific device."""
        config = cls(device=device)
        
        if device == "cuda":
            config.optimal_batch_size = 8
            config.enable_multi_stream = True
            config.memory_pool_size = 12
        elif device == "cpu":
            config.optimal_batch_size = 2
            config.enable_multi_stream = False
            config.memory_pool_size = 4
            config.compute_type = "float32"
            
        return config


@dataclass
class DiarizationConfig:
    """Configuration for speaker diarization."""
    
    enable_diarization: bool = False
    max_speakers: int = 10
    min_speakers: int = 1
    clustering_threshold: float = 0.7
    
    # Model settings
    model_name: str = "pyannote/speaker-diarization-3.1"
    device: str = field(default_factory=lambda: "cuda" if torch.cuda.is_available() else "cpu")
    
    # Processing settings
    chunk_length_s: float = 30.0
    overlap_length_s: float = 5.0
    
    @classmethod
    def create_default(cls) -> 'DiarizationConfig':
        """Create default diarization configuration."""
        return cls(enable_diarization=True)


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
    diarization: DiarizationConfig = field(default_factory=DiarizationConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    
    @classmethod
    def create_for_use_case(cls, use_case: str) -> 'UnifiedConfig':
        """Create configuration optimized for specific use case."""
        config = cls()
        
        if use_case == "japanese_high_quality":
            config.transcription = TranscriptionConfig.for_language("ja", "high")
            config.diarization.enable_diarization = True
            
        elif use_case == "english_fast":
            config.transcription = TranscriptionConfig.for_language("en", "fast")
            config.diarization.enable_diarization = False
            
        elif use_case == "multi_speaker_meeting":
            config.transcription = TranscriptionConfig.for_language("ja", "high")
            config.diarization = DiarizationConfig.create_default()
            config.diarization.max_speakers = 20
            
        elif use_case == "gpu_optimized":
            config.transcription = TranscriptionConfig.for_device("cuda")
            config.transcription.performance_monitoring = True
            
        return config
    
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "transcription": self.transcription.__dict__,
            "diarization": self.diarization.__dict__,
            "system": self.system.__dict__
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedConfig':
        """Create from dictionary."""
        config = cls()
        
        if "transcription" in data:
            config.transcription = TranscriptionConfig(**data["transcription"])
        if "diarization" in data:
            config.diarization = DiarizationConfig(**data["diarization"])
        if "system" in data:
            config.system = SystemConfig(**data["system"])
            
        return config