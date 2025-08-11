"""
Strategy Pattern implementation for batch optimization, timestamp formatting, and processing strategies.
Provides flexible, interchangeable algorithms for different processing scenarios.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List
import math
import torch
import psutil
from pathlib import Path


@dataclass
class DeviceInfo:
    """Device information for optimization strategies."""
    device_type: str  # 'cuda', 'cpu', 'mps'
    device_name: str
    memory_total: int  # in MB
    memory_available: int  # in MB
    compute_capability: Optional[str] = None  # for CUDA devices
    cores: int = 1


@dataclass
class AudioInfo:
    """Audio file information for processing strategies."""
    duration: float  # in seconds
    sample_rate: int
    channels: int
    file_size: int  # in bytes
    num_chunks: int


class BatchSizeStrategy(ABC):
    """Abstract strategy for calculating optimal batch sizes."""
    
    @abstractmethod
    def calculate_batch_size(self, audio_info: AudioInfo, device_info: DeviceInfo) -> int:
        """Calculate optimal batch size based on audio and device characteristics."""
        pass
    
    @abstractmethod
    def get_memory_threshold(self) -> float:
        """Get memory threshold for this strategy (0.0 to 1.0)."""
        pass


class GPUBatchSizeStrategy(BatchSizeStrategy):
    """GPU-optimized batch size calculation strategy."""
    
    def __init__(self, memory_threshold: float = 0.85, rtx_4080_optimized: bool = True):
        self.memory_threshold = memory_threshold
        self.rtx_4080_optimized = rtx_4080_optimized
    
    def calculate_batch_size(self, audio_info: AudioInfo, device_info: DeviceInfo) -> int:
        """Calculate GPU-optimized batch size."""
        if device_info.device_type != 'cuda':
            raise ValueError("GPUBatchSizeStrategy requires CUDA device")
        
        # RTX 4080 specific optimizations
        if self.rtx_4080_optimized and 'RTX 4080' in device_info.device_name:
            return self._calculate_rtx_4080_batch_size(audio_info, device_info)
        
        # General GPU optimization
        available_memory_mb = device_info.memory_available * self.memory_threshold
        
        # Estimate memory per chunk (empirical formula)
        estimated_memory_per_chunk = self._estimate_memory_per_chunk(audio_info)
        
        batch_size = max(1, int(available_memory_mb / estimated_memory_per_chunk))
        
        # Cap batch size based on audio characteristics
        return min(batch_size, audio_info.num_chunks, self._get_max_batch_size())
    
    def _calculate_rtx_4080_batch_size(self, audio_info: AudioInfo, device_info: DeviceInfo) -> int:
        """RTX 4080 specific batch size calculation."""
        # RTX 4080 has 16GB GDDR6X - optimized for this specific GPU
        base_memory_per_chunk = 85  # MB per chunk for RTX 4080
        
        # Adjust based on audio duration
        duration_factor = min(2.0, audio_info.duration / 30.0)  # Scale up to 2x for longer audio
        memory_per_chunk = base_memory_per_chunk * duration_factor
        
        available_memory = device_info.memory_available * 0.9  # Conservative for RTX 4080
        batch_size = max(1, int(available_memory / memory_per_chunk))
        
        # RTX 4080 sweet spot optimizations
        if batch_size > 32:
            batch_size = 32  # Diminishing returns above this
        elif batch_size > 16:
            batch_size = (batch_size // 4) * 4  # Align to tensor cores
        
        return min(batch_size, audio_info.num_chunks)
    
    def _estimate_memory_per_chunk(self, audio_info: AudioInfo) -> float:
        """Estimate memory usage per audio chunk."""
        # Base memory estimation (in MB)
        base_memory = 50
        
        # Scale with duration
        duration_factor = min(2.0, audio_info.duration / 60.0)
        
        # Scale with sample rate
        sample_rate_factor = audio_info.sample_rate / 16000.0
        
        return base_memory * duration_factor * sample_rate_factor
    
    def _get_max_batch_size(self) -> int:
        """Get maximum recommended batch size."""
        return 64  # Conservative maximum
    
    def get_memory_threshold(self) -> float:
        return self.memory_threshold


class CPUBatchSizeStrategy(BatchSizeStrategy):
    """CPU-optimized batch size calculation strategy."""
    
    def __init__(self, memory_threshold: float = 0.7):
        self.memory_threshold = memory_threshold
    
    def calculate_batch_size(self, audio_info: AudioInfo, device_info: DeviceInfo) -> int:
        """Calculate CPU-optimized batch size."""
        if device_info.device_type != 'cpu':
            raise ValueError("CPUBatchSizeStrategy requires CPU device")
        
        # CPU processing is more memory efficient but slower
        available_memory_mb = device_info.memory_available * self.memory_threshold
        
        # CPU uses less memory per chunk but benefits from larger batches
        memory_per_chunk = 25  # MB per chunk for CPU
        batch_size = max(1, int(available_memory_mb / memory_per_chunk))
        
        # Scale with CPU cores
        optimal_batch_size = min(batch_size, device_info.cores * 2)
        
        return min(optimal_batch_size, audio_info.num_chunks, 16)  # Cap at 16 for CPU
    
    def get_memory_threshold(self) -> float:
        return self.memory_threshold


class AdaptiveBatchSizeStrategy(BatchSizeStrategy):
    """Adaptive strategy that selects appropriate sub-strategy based on device."""
    
    def __init__(self):
        self.gpu_strategy = GPUBatchSizeStrategy()
        self.cpu_strategy = CPUBatchSizeStrategy()
    
    def calculate_batch_size(self, audio_info: AudioInfo, device_info: DeviceInfo) -> int:
        """Calculate batch size using appropriate sub-strategy."""
        if device_info.device_type == 'cuda':
            return self.gpu_strategy.calculate_batch_size(audio_info, device_info)
        else:
            return self.cpu_strategy.calculate_batch_size(audio_info, device_info)
    
    def get_memory_threshold(self) -> float:
        return 0.8  # Balanced threshold


class TimestampStrategy(ABC):
    """Abstract strategy for timestamp formatting."""
    
    @abstractmethod
    def format_timestamp(self, seconds: float) -> str:
        """Format timestamp in seconds to string representation."""
        pass
    
    @abstractmethod
    def get_format_name(self) -> str:
        """Get name of timestamp format."""
        pass


class ElapsedTimeStrategy(TimestampStrategy):
    """Strategy for elapsed time format (HH:MM:SS)."""
    
    def format_timestamp(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    def get_format_name(self) -> str:
        return "elapsed"


class AbsoluteTimeStrategy(TimestampStrategy):
    """Strategy for absolute timestamp format."""
    
    def __init__(self, start_time: float):
        self.start_time = start_time
    
    def format_timestamp(self, seconds: float) -> str:
        absolute_time = self.start_time + seconds
        hours = int(absolute_time // 3600) % 24
        minutes = int((absolute_time % 3600) // 60)
        secs = int(absolute_time % 60)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    def get_format_name(self) -> str:
        return "absolute"


class RelativeTimeStrategy(TimestampStrategy):
    """Strategy for relative timestamp format with reference point."""
    
    def __init__(self, reference_time: float = 0.0):
        self.reference_time = reference_time
    
    def format_timestamp(self, seconds: float) -> str:
        relative_seconds = seconds - self.reference_time
        if relative_seconds < 0:
            sign = "-"
            relative_seconds = abs(relative_seconds)
        else:
            sign = "+"
        
        hours = int(relative_seconds // 3600)
        minutes = int((relative_seconds % 3600) // 60)
        secs = int(relative_seconds % 60)
        return f"[{sign}{hours:02d}:{minutes:02d}:{secs:02d}]"
    
    def get_format_name(self) -> str:
        return "relative"


class MillisecondsStrategy(TimestampStrategy):
    """Strategy for high-precision timestamp with milliseconds."""
    
    def format_timestamp(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}]"
    
    def get_format_name(self) -> str:
        return "milliseconds"


class ProcessingStrategy(ABC):
    """Abstract strategy for different processing approaches."""
    
    @abstractmethod
    def process_audio_chunks(
        self,
        chunks: List[Any],
        model: Any,
        batch_size: int,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Process audio chunks with specific strategy."""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get name of processing strategy."""
        pass


class SequentialProcessingStrategy(ProcessingStrategy):
    """Sequential processing strategy - processes one batch at a time."""
    
    def process_audio_chunks(
        self,
        chunks: List[Any],
        model: Any,
        batch_size: int,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Process chunks sequentially."""
        results = []
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_results = self._process_batch(batch, model, **kwargs)
            results.extend(batch_results)
        
        return results
    
    def _process_batch(self, batch: List[Any], model: Any, **kwargs) -> List[Dict[str, Any]]:
        """Process a single batch."""
        # Implementation would call the actual model processing
        # This is a template method that would be used by the transcriber
        return []
    
    def get_strategy_name(self) -> str:
        return "sequential"


class ParallelProcessingStrategy(ProcessingStrategy):
    """Parallel processing strategy using multiple GPU streams."""
    
    def __init__(self, num_streams: int = 2):
        self.num_streams = num_streams
        self._streams = None
    
    def process_audio_chunks(
        self,
        chunks: List[Any],
        model: Any,
        batch_size: int,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Process chunks in parallel using multiple GPU streams."""
        if not torch.cuda.is_available():
            # Fallback to sequential for non-CUDA devices
            sequential_strategy = SequentialProcessingStrategy()
            return sequential_strategy.process_audio_chunks(chunks, model, batch_size, **kwargs)
        
        self._initialize_streams()
        results = []
        
        # Process chunks across multiple streams
        for stream_id in range(self.num_streams):
            stream_chunks = chunks[stream_id::self.num_streams]
            if stream_chunks:
                with torch.cuda.stream(self._streams[stream_id]):
                    stream_results = self._process_stream_chunks(
                        stream_chunks, model, batch_size, stream_id, **kwargs
                    )
                    results.extend(stream_results)
        
        # Synchronize all streams
        for stream in self._streams:
            stream.synchronize()
        
        return sorted(results, key=lambda x: x.get('chunk_index', 0))
    
    def _initialize_streams(self):
        """Initialize CUDA streams."""
        if self._streams is None:
            self._streams = [torch.cuda.Stream() for _ in range(self.num_streams)]
    
    def _process_stream_chunks(
        self, chunks: List[Any], model: Any, batch_size: int, stream_id: int, **kwargs
    ) -> List[Dict[str, Any]]:
        """Process chunks for a specific stream."""
        # Template method for stream-specific processing
        return []
    
    def get_strategy_name(self) -> str:
        return f"parallel_{self.num_streams}_streams"


class StrategyRegistry:
    """Registry for managing different strategy implementations."""
    
    _batch_strategies: Dict[str, type] = {
        'gpu': GPUBatchSizeStrategy,
        'cpu': CPUBatchSizeStrategy,
        'adaptive': AdaptiveBatchSizeStrategy,
    }
    
    _timestamp_strategies: Dict[str, type] = {
        'elapsed': ElapsedTimeStrategy,
        'absolute': AbsoluteTimeStrategy,
        'relative': RelativeTimeStrategy,
        'milliseconds': MillisecondsStrategy,
    }
    
    _processing_strategies: Dict[str, type] = {
        'sequential': SequentialProcessingStrategy,
        'parallel': ParallelProcessingStrategy,
    }
    
    @classmethod
    def get_batch_strategy(cls, name: str, **kwargs) -> BatchSizeStrategy:
        """Get batch size strategy by name."""
        if name not in cls._batch_strategies:
            raise ValueError(f"Unknown batch strategy: {name}")
        return cls._batch_strategies[name](**kwargs)
    
    @classmethod
    def get_timestamp_strategy(cls, name: str, **kwargs) -> TimestampStrategy:
        """Get timestamp strategy by name."""
        if name not in cls._timestamp_strategies:
            raise ValueError(f"Unknown timestamp strategy: {name}")
        return cls._timestamp_strategies[name](**kwargs)
    
    @classmethod
    def get_processing_strategy(cls, name: str, **kwargs) -> ProcessingStrategy:
        """Get processing strategy by name."""
        if name not in cls._processing_strategies:
            raise ValueError(f"Unknown processing strategy: {name}")
        return cls._processing_strategies[name](**kwargs)


def create_device_info() -> DeviceInfo:
    """Create DeviceInfo object for current system."""
    if torch.cuda.is_available():
        device = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(device)
        memory_total = props.total_memory // (1024**2)  # Convert to MB
        memory_available = (props.total_memory - torch.cuda.memory_reserved()) // (1024**2)
        
        return DeviceInfo(
            device_type='cuda',
            device_name=props.name,
            memory_total=memory_total,
            memory_available=memory_available,
            compute_capability=f"{props.major}.{props.minor}",
            cores=props.multi_processor_count
        )
    else:
        memory = psutil.virtual_memory()
        return DeviceInfo(
            device_type='cpu',
            device_name=f"CPU ({psutil.cpu_count()} cores)",
            memory_total=memory.total // (1024**2),
            memory_available=memory.available // (1024**2),
            cores=psutil.cpu_count()
        )


def create_audio_info(audio_path: str, num_chunks: int) -> AudioInfo:
    """Create AudioInfo object from audio file."""
    import librosa
    
    audio_path = Path(audio_path)
    duration = librosa.get_duration(path=str(audio_path))
    
    # Get audio properties
    y, sr = librosa.load(str(audio_path), sr=None)
    channels = 1 if len(y.shape) == 1 else y.shape[0]
    
    return AudioInfo(
        duration=duration,
        sample_rate=sr,
        channels=channels,
        file_size=audio_path.stat().st_size,
        num_chunks=num_chunks
    )