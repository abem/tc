"""
Refactored components from WhisperTranscriber to follow Single Responsibility Principle.
Breaks down the large WhisperTranscriber class into focused, testable components.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import torch
import logging
from pathlib import Path
import time
import threading
from collections import OrderedDict

from patterns.strategies import BatchSizeStrategy, TimestampStrategy, ProcessingStrategy


@dataclass
class ModelCacheEntry:
    """Entry in the model cache with metadata."""
    model: Any
    last_accessed: float
    access_count: int
    memory_usage: int  # in MB
    device: str


class ModelManager:
    """Manages model loading, caching, and device allocation."""
    
    def __init__(self, cache_size_limit: int = 3, memory_limit_mb: int = 8192):
        self.cache_size_limit = cache_size_limit
        self.memory_limit_mb = memory_limit_mb
        self._model_cache: OrderedDict[str, ModelCacheEntry] = OrderedDict()
        self._cache_lock = threading.RLock()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def load_model(self, model_name: str, device: str = 'auto', **kwargs) -> Any:
        """Load or retrieve model from cache."""
        cache_key = f"{model_name}_{device}"
        
        with self._cache_lock:
            # Check if model is in cache
            if cache_key in self._model_cache:
                entry = self._model_cache[cache_key]
                entry.last_accessed = time.time()
                entry.access_count += 1
                
                # Move to end (most recently used)
                self._model_cache.move_to_end(cache_key)
                
                self.logger.info(f"Model loaded from cache: {model_name}")
                return entry.model
            
            # Load new model
            model = self._load_new_model(model_name, device, **kwargs)
            
            # Add to cache
            memory_usage = self._estimate_model_memory(model)
            entry = ModelCacheEntry(
                model=model,
                last_accessed=time.time(),
                access_count=1,
                memory_usage=memory_usage,
                device=device
            )
            
            self._model_cache[cache_key] = entry
            
            # Manage cache size
            self._manage_cache_size()
            
            self.logger.info(f"New model loaded and cached: {model_name}")
            return model
    
    def _load_new_model(self, model_name: str, device: str, **kwargs) -> Any:
        """Load new model from disk/network."""
        try:
            # Determine device
            if device == 'auto':
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
            # Load model using transformers or whisper
            if model_name.startswith('openai/'):
                import whisper
                model = whisper.load_model(model_name.split('/')[-1], device=device)
            else:
                from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
                model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
                    device_map=device,
                    **kwargs
                )
            
            return model
            
        except Exception as e:
            self.logger.error(f"Failed to load model {model_name}: {str(e)}")
            raise
    
    def _manage_cache_size(self):
        """Manage cache size by removing least recently used models."""
        # Remove by cache size limit
        while len(self._model_cache) > self.cache_size_limit:
            oldest_key = next(iter(self._model_cache))
            self._remove_model_from_cache(oldest_key)
        
        # Remove by memory limit
        total_memory = sum(entry.memory_usage for entry in self._model_cache.values())
        while total_memory > self.memory_limit_mb and self._model_cache:
            oldest_key = next(iter(self._model_cache))
            removed_entry = self._model_cache[oldest_key]
            total_memory -= removed_entry.memory_usage
            self._remove_model_from_cache(oldest_key)
    
    def _remove_model_from_cache(self, cache_key: str):
        """Remove model from cache and free memory."""
        if cache_key in self._model_cache:
            entry = self._model_cache[cache_key]
            
            # Clear CUDA memory if applicable
            if hasattr(entry.model, 'to') and 'cuda' in entry.device:
                entry.model.to('cpu')
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            
            del self._model_cache[cache_key]
            self.logger.info(f"Removed model from cache: {cache_key}")
    
    def _estimate_model_memory(self, model: Any) -> int:
        """Estimate model memory usage in MB."""
        try:
            if hasattr(model, 'get_memory_footprint'):
                return model.get_memory_footprint() // (1024 ** 2)
            elif hasattr(model, 'num_parameters'):
                # Rough estimation: 4 bytes per parameter for float32
                return (model.num_parameters() * 4) // (1024 ** 2)
            else:
                return 500  # Default estimate in MB
        except Exception:
            return 500  # Fallback estimate
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._cache_lock:
            total_memory = sum(entry.memory_usage for entry in self._model_cache.values())
            return {
                'cache_size': len(self._model_cache),
                'cache_limit': self.cache_size_limit,
                'total_memory_mb': total_memory,
                'memory_limit_mb': self.memory_limit_mb,
                'models': {
                    key: {
                        'access_count': entry.access_count,
                        'memory_usage_mb': entry.memory_usage,
                        'device': entry.device
                    }
                    for key, entry in self._model_cache.items()
                }
            }
    
    def clear_cache(self):
        """Clear all models from cache."""
        with self._cache_lock:
            for cache_key in list(self._model_cache.keys()):
                self._remove_model_from_cache(cache_key)


class AudioProcessor:
    """Handles audio preprocessing, chunking, and validation."""
    
    def __init__(self, chunk_duration: float = 30.0, overlap_duration: float = 1.0):
        self.chunk_duration = chunk_duration
        self.overlap_duration = overlap_duration
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def preprocess_audio(self, audio_path: str) -> Tuple[Any, Dict[str, Any]]:
        """Preprocess audio file and return audio data with metadata."""
        try:
            import librosa
            
            audio_path = Path(audio_path)
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            # Load audio
            audio_data, sample_rate = librosa.load(str(audio_path), sr=16000)
            
            # Get metadata
            duration = len(audio_data) / sample_rate
            metadata = {
                'file_path': str(audio_path),
                'file_size': audio_path.stat().st_size,
                'duration': duration,
                'sample_rate': sample_rate,
                'channels': 1,  # librosa loads as mono by default
                'format': audio_path.suffix.lower()
            }
            
            self.logger.info(f"Audio preprocessed: {duration:.2f}s, {sample_rate}Hz")
            return audio_data, metadata
            
        except Exception as e:
            self.logger.error(f"Audio preprocessing failed: {str(e)}")
            raise
    
    def create_chunks(self, audio_data: Any, sample_rate: int) -> List[Tuple[Any, float, float]]:
        """Create overlapping audio chunks."""
        chunks = []
        chunk_samples = int(self.chunk_duration * sample_rate)
        overlap_samples = int(self.overlap_duration * sample_rate)
        step_samples = chunk_samples - overlap_samples
        
        for i in range(0, len(audio_data), step_samples):
            chunk_start = i
            chunk_end = min(i + chunk_samples, len(audio_data))
            
            if chunk_end - chunk_start < sample_rate:  # Skip chunks shorter than 1 second
                break
            
            chunk_audio = audio_data[chunk_start:chunk_end]
            start_time = chunk_start / sample_rate
            end_time = chunk_end / sample_rate
            
            chunks.append((chunk_audio, start_time, end_time))
        
        self.logger.info(f"Created {len(chunks)} audio chunks")
        return chunks
    
    def validate_audio_format(self, audio_path: str) -> bool:
        """Validate if audio format is supported."""
        supported_formats = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.wma'}
        path = Path(audio_path)
        return path.suffix.lower() in supported_formats


class MemoryManager:
    """Manages GPU memory allocation and cleanup."""
    
    def __init__(self, enable_memory_pool: bool = True, pool_size_mb: int = 1024):
        self.enable_memory_pool = enable_memory_pool
        self.pool_size_mb = pool_size_mb
        self._memory_pool: Dict[Tuple[int, ...], torch.Tensor] = {}
        self._pool_lock = threading.RLock()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_memory_pool_tensor(self, shape: Tuple[int, ...], dtype: torch.dtype, device: str) -> Optional[torch.Tensor]:
        """Get tensor from memory pool if available."""
        if not self.enable_memory_pool or device == 'cpu':
            return None
        
        with self._pool_lock:
            pool_key = shape
            if pool_key in self._memory_pool:
                tensor = self._memory_pool.pop(pool_key)
                if tensor.dtype == dtype and str(tensor.device) == device:
                    return tensor.zero_()  # Clear and return
        
        return None
    
    def return_memory_pool_tensor(self, tensor: torch.Tensor):
        """Return tensor to memory pool for reuse."""
        if not self.enable_memory_pool or tensor.device.type == 'cpu':
            return
        
        with self._pool_lock:
            # Check pool size limit
            current_pool_memory = sum(
                t.numel() * t.element_size()
                for t in self._memory_pool.values()
            ) / (1024 ** 2)  # Convert to MB
            
            tensor_memory_mb = (tensor.numel() * tensor.element_size()) / (1024 ** 2)
            
            if current_pool_memory + tensor_memory_mb <= self.pool_size_mb:
                self._memory_pool[tuple(tensor.shape)] = tensor.detach()
    
    def cleanup_memory(self):
        """Clean up memory and empty cache."""
        with self._pool_lock:
            self._memory_pool.clear()
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        
        self.logger.info("Memory cleanup completed")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        stats = {'memory_pool_enabled': self.enable_memory_pool}
        
        if torch.cuda.is_available():
            stats.update({
                'cuda_allocated_mb': torch.cuda.memory_allocated() / (1024 ** 2),
                'cuda_reserved_mb': torch.cuda.memory_reserved() / (1024 ** 2),
                'cuda_max_allocated_mb': torch.cuda.max_memory_allocated() / (1024 ** 2)
            })
        
        with self._pool_lock:
            pool_memory_mb = sum(
                t.numel() * t.element_size()
                for t in self._memory_pool.values()
            ) / (1024 ** 2)
            stats['memory_pool_mb'] = pool_memory_mb
            stats['memory_pool_tensors'] = len(self._memory_pool)
        
        return stats


class BatchProcessor:
    """Handles batch processing with different strategies."""
    
    def __init__(
        self,
        batch_strategy: BatchSizeStrategy,
        processing_strategy: ProcessingStrategy
    ):
        self.batch_strategy = batch_strategy
        self.processing_strategy = processing_strategy
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def process_chunks(
        self,
        chunks: List[Tuple[Any, float, float]],
        model: Any,
        audio_info: Any,
        device_info: Any,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Process audio chunks using configured strategies."""
        try:
            # Calculate optimal batch size
            batch_size = self.batch_strategy.calculate_batch_size(audio_info, device_info)
            self.logger.info(f"Using batch size: {batch_size}")
            
            # Extract audio data for processing
            chunk_data = [chunk[0] for chunk in chunks]
            
            # Process using strategy
            results = self.processing_strategy.process_audio_chunks(
                chunk_data, model, batch_size, **kwargs
            )
            
            # Combine with timing information
            for i, result in enumerate(results):
                if i < len(chunks):
                    _, start_time, end_time = chunks[i]
                    result['start_time'] = start_time
                    result['end_time'] = end_time
            
            return results
            
        except Exception as e:
            self.logger.error(f"Batch processing failed: {str(e)}")
            raise


class TranscriptionFormatter:
    """Handles transcription result formatting with different timestamp strategies."""
    
    def __init__(self, timestamp_strategy: TimestampStrategy):
        self.timestamp_strategy = timestamp_strategy
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def format_transcription_results(
        self,
        results: List[Dict[str, Any]],
        include_timestamps: bool = True,
        speaker_labels: Optional[Dict[float, str]] = None
    ) -> str:
        """Format transcription results into readable text."""
        try:
            formatted_lines = []
            
            for result in results:
                text = result.get('text', '').strip()
                if not text:
                    continue
                
                line_parts = []
                
                # Add timestamp if requested
                if include_timestamps and 'start_time' in result:
                    timestamp = self.timestamp_strategy.format_timestamp(result['start_time'])
                    line_parts.append(timestamp)
                
                # Add speaker label if available
                if speaker_labels and 'start_time' in result:
                    speaker = speaker_labels.get(result['start_time'], 'Speaker')
                    line_parts.append(f"{speaker}:")
                
                # Add text
                line_parts.append(text)
                
                formatted_lines.append(' '.join(line_parts))
            
            return '\n'.join(formatted_lines)
            
        except Exception as e:
            self.logger.error(f"Transcription formatting failed: {str(e)}")
            raise
    
    def format_with_confidence_scores(
        self,
        results: List[Dict[str, Any]],
        confidence_threshold: float = 0.5
    ) -> str:
        """Format results with confidence score indicators."""
        formatted_lines = []
        
        for result in results:
            text = result.get('text', '').strip()
            confidence = result.get('confidence', 1.0)
            
            if confidence < confidence_threshold:
                text = f"[低信頼度] {text}"
            
            timestamp = ""
            if 'start_time' in result:
                timestamp = self.timestamp_strategy.format_timestamp(result['start_time'])
            
            formatted_lines.append(f"{timestamp} {text}")
        
        return '\n'.join(formatted_lines)


class RefactoredWhisperTranscriber:
    """Refactored WhisperTranscriber using composition and separation of concerns."""
    
    def __init__(
        self,
        model_name: str = 'openai/whisper-large-v3',
        device: str = 'auto',
        batch_strategy: Optional[BatchSizeStrategy] = None,
        timestamp_strategy: Optional[TimestampStrategy] = None,
        processing_strategy: Optional[ProcessingStrategy] = None
    ):
        self.model_name = model_name
        self.device = device
        
        # Initialize components
        self.model_manager = ModelManager()
        self.audio_processor = AudioProcessor()
        self.memory_manager = MemoryManager()
        
        # Initialize strategies
        if batch_strategy is None:
            from patterns.strategies import AdaptiveBatchSizeStrategy
            batch_strategy = AdaptiveBatchSizeStrategy()
        
        if timestamp_strategy is None:
            from patterns.strategies import ElapsedTimeStrategy
            timestamp_strategy = ElapsedTimeStrategy()
        
        if processing_strategy is None:
            from patterns.strategies import SequentialProcessingStrategy
            processing_strategy = SequentialProcessingStrategy()
        
        self.batch_processor = BatchProcessor(batch_strategy, processing_strategy)
        self.formatter = TranscriptionFormatter(timestamp_strategy)
        
        self.logger = logging.getLogger(self.__class__.__name__)
        self._model = None
    
    def load_model(self):
        """Load transcription model."""
        self._model = self.model_manager.load_model(self.model_name, self.device)
    
    def transcribe(self, audio_path: str, **kwargs) -> str:
        """Transcribe audio file."""
        try:
            # Load model if not already loaded
            if self._model is None:
                self.load_model()
            
            # Preprocess audio
            audio_data, metadata = self.audio_processor.preprocess_audio(audio_path)
            
            # Create chunks
            chunks = self.audio_processor.create_chunks(
                audio_data, metadata['sample_rate']
            )
            
            # Create info objects for batch processing
            from patterns.strategies import create_audio_info, create_device_info
            audio_info = create_audio_info(audio_path, len(chunks))
            device_info = create_device_info()
            
            # Process chunks
            results = self.batch_processor.process_chunks(
                chunks, self._model, audio_info, device_info, **kwargs
            )
            
            # Format results
            formatted_text = self.formatter.format_transcription_results(results)
            
            # Cleanup
            self.memory_manager.cleanup_memory()
            
            return formatted_text
            
        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            self.memory_manager.cleanup_memory()
            raise
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics from all components."""
        return {
            'model_cache': self.model_manager.get_cache_stats(),
            'memory': self.memory_manager.get_memory_stats(),
            'batch_strategy': self.batch_processor.batch_strategy.__class__.__name__,
            'processing_strategy': self.batch_processor.processing_strategy.__class__.__name__,
            'timestamp_strategy': self.formatter.timestamp_strategy.__class__.__name__
        }
    
    def update_strategies(
        self,
        batch_strategy: Optional[BatchSizeStrategy] = None,
        timestamp_strategy: Optional[TimestampStrategy] = None,
        processing_strategy: Optional[ProcessingStrategy] = None
    ):
        """Update processing strategies at runtime."""
        if batch_strategy:
            self.batch_processor.batch_strategy = batch_strategy
        
        if timestamp_strategy:
            self.formatter.timestamp_strategy = timestamp_strategy
        
        if processing_strategy:
            self.batch_processor.processing_strategy = processing_strategy
        
        self.logger.info("Processing strategies updated")