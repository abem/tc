"""
Model caching functionality extracted from WhisperTranscriber.
Manages model loading, caching, and memory optimization.
"""

import time
import torch
from collections import OrderedDict
from typing import Dict, Any, Optional
from transformers import AutoProcessor, WhisperForConditionalGeneration

from core.logging_config import UnifiedLogger


class ModelCache:
    """Model caching system for Whisper models."""
    
    def __init__(self, max_cache_size: int = 5):
        self.max_cache_size = max_cache_size
        self._model_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_usage: Dict[str, float] = {}
        self.logger = UnifiedLogger.get_logger(__name__)
    
    def get_model(self, model_name: str, device: str) -> tuple:
        """Get or load model from cache."""
        cache_key = f"{model_name}_{device}"
        
        if cache_key in self._model_cache:
            # Update cache usage
            self._cache_usage[cache_key] = time.time()
            
            cached_model = self._model_cache[cache_key]
            self.logger.info(f"Model loaded from cache: {model_name}")
            
            return cached_model['model'], cached_model['processor']
        
        # Load new model
        self.logger.info(f"Loading new model: {model_name}")
        model, processor = self._load_model(model_name, device)
        
        # Add to cache
        self._add_to_cache(cache_key, model, processor)
        
        return model, processor
    
    def _load_model(self, model_name: str, device: str) -> tuple:
        """Load model from HuggingFace."""
        try:
            processor = AutoProcessor.from_pretrained(model_name)
            model = WhisperForConditionalGeneration.from_pretrained(model_name)
            
            if device != "cpu":
                model = model.to(device)
            
            return model, processor
            
        except Exception as e:
            self.logger.error(f"Failed to load model {model_name}: {str(e)}")
            raise
    
    def _add_to_cache(self, cache_key: str, model: Any, processor: Any) -> None:
        """Add model to cache with LRU eviction."""
        # Check cache size limit
        if len(self._model_cache) >= self.max_cache_size:
            self._evict_lru()
        
        # Add to cache
        self._model_cache[cache_key] = {
            'model': model,
            'processor': processor,
            'cached_at': time.time()
        }
        self._cache_usage[cache_key] = time.time()
        
        self.logger.info(f"Model added to cache: {cache_key}")
    
    def _evict_lru(self) -> None:
        """Evict least recently used model."""
        if not self._cache_usage:
            return
        
        # Find least recently used
        lru_key = min(self._cache_usage.items(), key=lambda x: x[1])[0]
        
        # Remove from cache
        del self._model_cache[lru_key]
        del self._cache_usage[lru_key]
        
        self.logger.info(f"Evicted model from cache: {lru_key}")
    
    def clear_cache(self) -> None:
        """Clear all cached models."""
        count = len(self._model_cache)
        self._model_cache.clear()
        self._cache_usage.clear()
        self.logger.info(f"Cache cleared: {count} models removed")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'cache_size': len(self._model_cache),
            'max_cache_size': self.max_cache_size,
            'cached_models': list(self._model_cache.keys()),
            'cache_usage': self._cache_usage.copy()
        }