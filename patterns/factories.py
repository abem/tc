"""
Abstract Factory Pattern implementation for model creation and configuration management.
Provides centralized, flexible model instantiation with proper abstraction layers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, Type
from pathlib import Path
import yaml

from transcriber import TranscriptionConfig
from speaker_diarization import DiarizationConfig


class BaseTranscriber(ABC):
    """Abstract base class for all transcription implementations."""
    
    @abstractmethod
    def transcribe(self, audio_path: str, **kwargs) -> str:
        """Transcribe audio file to text."""
        pass
    
    @abstractmethod
    def load_model(self) -> None:
        """Load the transcription model."""
        pass


class BaseDiarizer(ABC):
    """Abstract base class for all speaker diarization implementations."""
    
    @abstractmethod
    def diarize(self, audio_path: str) -> Dict[str, Any]:
        """Perform speaker diarization on audio file."""
        pass


class ModelFactory(ABC):
    """Abstract factory for creating transcription and diarization models."""
    
    @abstractmethod
    def create_transcriber(self, config: TranscriptionConfig) -> BaseTranscriber:
        """Create a transcriber instance."""
        pass
    
    @abstractmethod
    def create_diarizer(self, config: DiarizationConfig) -> BaseDiarizer:
        """Create a diarizer instance."""
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages."""
        pass


class WhisperModelFactory(ModelFactory):
    """Concrete factory for Whisper-based models."""
    
    def create_transcriber(self, config: TranscriptionConfig) -> BaseTranscriber:
        from transcriber import WhisperTranscriber
        return WhisperTranscriber(config)
    
    def create_diarizer(self, config: DiarizationConfig) -> BaseDiarizer:
        from speaker_diarization import SpeakerDiarizer
        return SpeakerDiarizer(config)
    
    def get_supported_languages(self) -> list[str]:
        return ['ja', 'en', 'zh', 'ko', 'es', 'fr', 'de', 'it', 'pt', 'ru']


class ConfigurationFactory:
    """Factory for creating and managing configuration objects."""
    
    _config_cache: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def load_config_file(cls, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file with caching."""
        if config_path not in cls._config_cache:
            with open(config_path, 'r', encoding='utf-8') as f:
                cls._config_cache[config_path] = yaml.safe_load(f)
        return cls._config_cache[config_path]
    
    @classmethod
    def create_transcription_config(
        cls,
        language: str = 'ja',
        model: Optional[str] = None,
        config_path: str = 'config/config.yaml',
        **overrides
    ) -> TranscriptionConfig:
        """Create transcription configuration with language-aware defaults."""
        config_data = cls.load_config_file(config_path)
        
        # Language-specific model selection
        if model is None:
            language_models = config_data.get('models', {}).get('language_specific', {})
            model = language_models.get(language, config_data.get('models', {}).get('default', 'openai/whisper-large-v3'))
        
        # Build configuration with overrides
        transcription_config = config_data.get('transcription', {})
        transcription_config.update(overrides)
        
        return TranscriptionConfig(
            model=model,
            language=language,
            **transcription_config
        )
    
    @classmethod
    def create_diarization_config(
        cls,
        config_path: str = 'config/config.yaml',
        **overrides
    ) -> DiarizationConfig:
        """Create speaker diarization configuration."""
        config_data = cls.load_config_file(config_path)
        diarization_config = config_data.get('speaker_diarization', {})
        diarization_config.update(overrides)
        
        return DiarizationConfig(**diarization_config)


@dataclass
class ProcessingConfiguration:
    """Unified configuration for the entire processing pipeline."""
    transcription: TranscriptionConfig
    diarization: Optional[DiarizationConfig] = None
    enable_speaker_diarization: bool = False
    output_format: str = 'txt'
    upload_to_gdrive: bool = True
    
    @classmethod
    def create_for_language(
        cls,
        language: str,
        enable_diarization: bool = False,
        config_path: str = 'config/config.yaml'
    ) -> 'ProcessingConfiguration':
        """Create processing configuration optimized for specific language."""
        transcription_config = ConfigurationFactory.create_transcription_config(
            language=language,
            config_path=config_path
        )
        
        diarization_config = None
        if enable_diarization:
            diarization_config = ConfigurationFactory.create_diarization_config(
                config_path=config_path
            )
        
        return cls(
            transcription=transcription_config,
            diarization=diarization_config,
            enable_speaker_diarization=enable_diarization
        )


class ModelFactoryRegistry:
    """Registry for managing different model factory implementations."""
    
    _factories: Dict[str, Type[ModelFactory]] = {
        'whisper': WhisperModelFactory,
    }
    _instances: Dict[str, ModelFactory] = {}
    
    @classmethod
    def register_factory(cls, name: str, factory_class: Type[ModelFactory]) -> None:
        """Register a new model factory."""
        cls._factories[name] = factory_class
    
    @classmethod
    def get_factory(cls, name: str = 'whisper') -> ModelFactory:
        """Get factory instance (singleton pattern)."""
        if name not in cls._instances:
            if name not in cls._factories:
                raise ValueError(f"Unknown factory type: {name}")
            cls._instances[name] = cls._factories[name]()
        return cls._instances[name]
    
    @classmethod
    def get_available_factories(cls) -> list[str]:
        """Get list of available factory names."""
        return list(cls._factories.keys())


class LanguageAwareModelSelector:
    """Intelligent model selection based on language and quality requirements."""
    
    _model_recommendations = {
        'ja': {
            'high_quality': 'kotoba-tech/kotoba-whisper-v2.2',
            'fast': 'openai/whisper-medium',
            'balanced': 'kotoba-tech/kotoba-whisper-v2.2'
        },
        'en': {
            'high_quality': 'openai/whisper-large-v3',
            'fast': 'openai/whisper-base',
            'balanced': 'openai/whisper-medium'
        },
        'default': {
            'high_quality': 'openai/whisper-large-v3',
            'fast': 'openai/whisper-base',
            'balanced': 'openai/whisper-medium'
        }
    }
    
    @classmethod
    def select_optimal_model(
        cls,
        language: str,
        quality_preference: str = 'balanced',
        available_models: Optional[list[str]] = None
    ) -> str:
        """Select optimal model based on language and quality preferences."""
        language_models = cls._model_recommendations.get(
            language, 
            cls._model_recommendations['default']
        )
        
        selected_model = language_models.get(quality_preference, language_models['balanced'])
        
        # Fallback to available models if preferred model is not available
        if available_models and selected_model not in available_models:
            for fallback in language_models.values():
                if fallback in available_models:
                    return fallback
            return available_models[0] if available_models else selected_model
        
        return selected_model


# Convenience functions for common use cases
def create_japanese_transcriber(quality: str = 'high_quality') -> BaseTranscriber:
    """Create optimized Japanese transcriber."""
    model = LanguageAwareModelSelector.select_optimal_model('ja', quality)
    config = ConfigurationFactory.create_transcription_config(
        language='ja',
        model=model
    )
    factory = ModelFactoryRegistry.get_factory('whisper')
    return factory.create_transcriber(config)


def create_multilingual_transcriber(language: str, quality: str = 'balanced') -> BaseTranscriber:
    """Create transcriber optimized for specific language."""
    model = LanguageAwareModelSelector.select_optimal_model(language, quality)
    config = ConfigurationFactory.create_transcription_config(
        language=language,
        model=model
    )
    factory = ModelFactoryRegistry.get_factory('whisper')
    return factory.create_transcriber(config)


def create_complete_processing_pipeline(
    language: str,
    enable_diarization: bool = False,
    quality: str = 'balanced'
) -> tuple[BaseTranscriber, Optional[BaseDiarizer]]:
    """Create complete transcription + diarization pipeline."""
    factory = ModelFactoryRegistry.get_factory('whisper')
    
    # Create transcriber
    transcription_config = ConfigurationFactory.create_transcription_config(
        language=language,
        model=LanguageAwareModelSelector.select_optimal_model(language, quality)
    )
    transcriber = factory.create_transcriber(transcription_config)
    
    # Create diarizer if needed
    diarizer = None
    if enable_diarization:
        diarization_config = ConfigurationFactory.create_diarization_config()
        diarizer = factory.create_diarizer(diarization_config)
    
    return transcriber, diarizer