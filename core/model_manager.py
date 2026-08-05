"""
Unified model management system.
Consolidates all model loading, caching, and device management functionality.
"""

import threading
import time
import torch
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path

from core.logging import UnifiedLogger, PerformanceLogger


@dataclass
class ModelCacheEntry:
    """Entry in the model cache with comprehensive metadata."""
    model: Any
    model_name: str
    device: str
    last_accessed: float
    access_count: int
    memory_usage_mb: float
    load_time: float
    model_type: str  # 'whisper', etc.


class ModelLoader(ABC):
    """Abstract base class for model loaders."""
    
    @abstractmethod
    def load_model(self, model_name: str, device: str, **kwargs) -> Any:
        """Load a model with the specified parameters."""
        pass
    
    @abstractmethod
    def estimate_memory_usage(self, model: Any) -> float:
        """Estimate model memory usage in MB."""
        pass
    
    @abstractmethod
    def get_model_type(self) -> str:
        """Get the type of models this loader handles."""
        pass


class WhisperModelLoader(ModelLoader):
    """Loader for Whisper models."""
    
    def load_model(self, model_name: str, device: str, **kwargs) -> Any:
        """Load a Whisper model."""
        from transformers import AutoProcessor, WhisperForConditionalGeneration
        
        processor = AutoProcessor.from_pretrained(model_name)
        model = WhisperForConditionalGeneration.from_pretrained(model_name)
        
        if device != "cpu":
            model = model.to(device)
        
        return {"model": model, "processor": processor}
    
    def estimate_memory_usage(self, model: Any) -> float:
        """Estimate Whisper model memory usage."""
        if isinstance(model, dict) and "model" in model:
            actual_model = model["model"]
            if hasattr(actual_model, 'get_memory_footprint'):
                return actual_model.get_memory_footprint() / 1024 / 1024  # Convert to MB
            else:
                # Rough estimate based on parameters
                total_params = sum(p.numel() for p in actual_model.parameters())
                return total_params * 4 / 1024 / 1024  # 4 bytes per float32 parameter
        return 1000.0  # Default estimate
    
    def get_model_type(self) -> str:
        return "whisper"


class UnifiedModelManager:
    """Centralized model management system."""
    
    def __init__(self, 
                 cache_size_limit: int = 3,
                 memory_limit_mb: float = 8192,
                 enable_metrics: bool = True):
        self.cache_size_limit = cache_size_limit
        self.memory_limit_mb = memory_limit_mb
        self.enable_metrics = enable_metrics
        
        self._model_cache: OrderedDict[str, ModelCacheEntry] = OrderedDict()
        self._cache_lock = threading.RLock()
        self._loaders: Dict[str, ModelLoader] = {}
        
        # Initialize default loaders
        self._register_default_loaders()
        
        # Logging
        self.logger = UnifiedLogger.get_logger(self.__class__.__name__)
        self.perf_logger = PerformanceLogger(self.__class__.__name__)
        
        self.logger.info(f"UnifiedModelManager initialized: cache_limit={cache_size_limit}, memory_limit={memory_limit_mb}MB")
    
    def _register_default_loaders(self) -> None:
        """Register default model loaders."""
        self._loaders["whisper"] = WhisperModelLoader()
    
    def register_loader(self, model_type: str, loader: ModelLoader) -> None:
        """Register a custom model loader."""
        self._loaders[model_type] = loader
        self.logger.info(f"Registered loader for model type: {model_type}")
    
    def load_model(self, 
                   model_name: str, 
                   model_type: str = "whisper",
                   device: str = "auto",
                   **kwargs) -> Any:
        """Load or retrieve model from cache."""
        
        # Auto-detect device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        cache_key = f"{model_type}:{model_name}:{device}"
        
        with self._cache_lock:
            # Check cache first
            if cache_key in self._model_cache:
                entry = self._model_cache[cache_key]
                entry.last_accessed = time.time()
                entry.access_count += 1
                
                # Move to end (most recently used)
                self._model_cache.move_to_end(cache_key)
                
                self.logger.info(f"Model loaded from cache: {model_name}")
                if self.enable_metrics:
                    self.perf_logger.log_metric("cache_hit", model_name)
                
                return entry.model
            
            # Load new model
            if model_type not in self._loaders:
                raise ValueError(f"No loader registered for model type: {model_type}")
            
            loader = self._loaders[model_type]
            
            self.logger.info(f"Loading new model: {model_name} on {device}")
            if self.enable_metrics:
                self.perf_logger.start_timing(f"model_load_{model_name}")
            
            try:
                model = loader.load_model(model_name, device, **kwargs)
                load_time = self.perf_logger.end_timing(f"model_load_{model_name}") if self.enable_metrics else 0.0
                
                # Estimate memory usage
                memory_usage = loader.estimate_memory_usage(model)
                
                # Check memory limits
                if not self._check_memory_limits(memory_usage):
                    self._cleanup_cache(memory_usage)
                
                # Create cache entry
                entry = ModelCacheEntry(
                    model=model,
                    model_name=model_name,
                    device=device,
                    last_accessed=time.time(),
                    access_count=1,
                    memory_usage_mb=memory_usage,
                    load_time=load_time,
                    model_type=model_type
                )
                
                # Add to cache
                self._model_cache[cache_key] = entry
                
                # Enforce cache size limits
                self._enforce_cache_limits()
                
                self.logger.info(f"Model loaded successfully: {model_name} ({memory_usage:.1f}MB)")
                if self.enable_metrics:
                    self.perf_logger.log_metric("model_memory_usage", memory_usage, "MB")
                    self.perf_logger.log_metric("cache_size", len(self._model_cache))
                
                return model
                
            except Exception as e:
                self.logger.error(f"Failed to load model {model_name}: {str(e)}")
                raise
    
    def _check_memory_limits(self, new_model_memory: float) -> bool:
        """Check if adding a new model would exceed memory limits."""
        current_memory = sum(entry.memory_usage_mb for entry in self._model_cache.values())
        return (current_memory + new_model_memory) <= self.memory_limit_mb
    
    def _cleanup_cache(self, required_memory: float) -> None:
        """Clean up cache to make room for new model."""
        current_memory = sum(entry.memory_usage_mb for entry in self._model_cache.values())
        
        # Sort by access time (least recently used first)
        sorted_entries = sorted(
            self._model_cache.items(),
            key=lambda x: (x[1].last_accessed, x[1].access_count)
        )
        
        freed_memory = 0.0
        for cache_key, entry in sorted_entries:
            if (current_memory - freed_memory + required_memory) <= self.memory_limit_mb:
                break
            
            self.logger.info(f"Evicting model from cache: {entry.model_name} ({entry.memory_usage_mb:.1f}MB)")
            del self._model_cache[cache_key]
            freed_memory += entry.memory_usage_mb
        
        if self.enable_metrics:
            self.perf_logger.log_metric("cache_evicted_memory", freed_memory, "MB")
    
    def _enforce_cache_limits(self) -> None:
        """Enforce cache size limits."""
        while len(self._model_cache) > self.cache_size_limit:
            # Remove least recently used
            oldest_key = next(iter(self._model_cache))
            entry = self._model_cache[oldest_key]
            self.logger.info(f"Cache size limit exceeded, removing: {entry.model_name}")
            del self._model_cache[oldest_key]
    
    def clear_cache(self) -> None:
        """Clear all cached models."""
        with self._cache_lock:
            cleared_count = len(self._model_cache)
            self._model_cache.clear()
            self.logger.info(f"Cache cleared: {cleared_count} models removed")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._cache_lock:
            total_memory = sum(entry.memory_usage_mb for entry in self._model_cache.values())
            
            stats = {
                "cache_size": len(self._model_cache),
                "cache_limit": self.cache_size_limit,
                "total_memory_mb": total_memory,
                "memory_limit_mb": self.memory_limit_mb,
                "memory_utilization": (total_memory / self.memory_limit_mb) * 100,
                "models": []
            }
            
            for cache_key, entry in self._model_cache.items():
                stats["models"].append({
                    "cache_key": cache_key,
                    "model_name": entry.model_name,
                    "model_type": entry.model_type,
                    "device": entry.device,
                    "memory_mb": entry.memory_usage_mb,
                    "access_count": entry.access_count,
                    "last_accessed": entry.last_accessed,
                    "load_time": entry.load_time
                })
            
            return stats
    
    def preload_models(self, model_configs: List[Dict[str, Any]]) -> None:
        """Preload multiple models."""
        self.logger.info(f"Preloading {len(model_configs)} models")
        
        for config in model_configs:
            try:
                self.load_model(**config)
            except Exception as e:
                self.logger.error(f"Failed to preload model {config}: {str(e)}")
    
    def warm_up_cache(self) -> None:
        """Warm up cache with commonly used models."""
        common_models = [
            {"model_name": "kotoba-tech/kotoba-whisper-v2.2", "model_type": "whisper"},
            {"model_name": "openai/whisper-large-v3", "model_type": "whisper"}
        ]
        
        self.logger.info("Warming up model cache")
        self.preload_models(common_models)


# Global instance
_global_manager: Optional[UnifiedModelManager] = None


def get_global_model_manager() -> UnifiedModelManager:
    """Get the global model manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = UnifiedModelManager()
    return _global_manager


def configure_model_manager(cache_size_limit: int = 3,
                           memory_limit_mb: float = 8192,
                           enable_metrics: bool = True) -> UnifiedModelManager:
    """Configure and get the global model manager."""
    global _global_manager
    _global_manager = UnifiedModelManager(
        cache_size_limit=cache_size_limit,
        memory_limit_mb=memory_limit_mb,
        enable_metrics=enable_metrics
    )
    return _global_manager


# Testing
if __name__ == "__main__":
    manager = UnifiedModelManager(cache_size_limit=2, memory_limit_mb=4096)
    
    # Test model loading
    try:
        model = manager.load_model("openai/whisper-tiny", "whisper", "cpu")
        print("Model loaded successfully")
        
        # Get stats
        stats = manager.get_cache_stats()
        print(f"Cache stats: {stats}")
        
    except Exception as e:
        print(f"Test failed: {e}")