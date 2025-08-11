"""
Performance optimization functionality extracted from WhisperTranscriber.
Handles GPU optimization, memory management, and performance monitoring.
"""

import torch
import time
import psutil
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
import asyncio

from core.logging_config import UnifiedLogger, PerformanceLogger


class PerformanceOptimizer:
    """Handles performance optimization for transcription."""
    
    def __init__(self, config):
        self.config = config
        self.logger = UnifiedLogger.get_logger(__name__)
        self.perf_logger = PerformanceLogger(__name__)
        
        # Performance tracking
        self.processing_times = []
        self.memory_usage = []
        self.gpu_usage = []
    
    def optimize_for_device(self) -> Dict[str, Any]:
        """Optimize settings based on available device."""
        device_info = {
            'device': self.config.device,
            'optimizations': []
        }
        
        if self.config.device == "cuda" and torch.cuda.is_available():
            device_info.update(self._optimize_gpu())
        else:
            device_info.update(self._optimize_cpu())
        
        return device_info
    
    def _optimize_gpu(self) -> Dict[str, Any]:
        """GPU-specific optimizations."""
        optimizations = []
        gpu_info = {}
        
        try:
            # Get GPU properties
            gpu_properties = torch.cuda.get_device_properties(0)
            gpu_info['name'] = gpu_properties.name
            gpu_info['memory_total'] = gpu_properties.total_memory
            
            # Memory optimization
            if self.config.memory_efficiency:
                torch.backends.cudnn.benchmark = True
                optimizations.append("CUDNN benchmark enabled")
            
            # Multi-stream processing
            if self.config.enable_multi_stream:
                gpu_info['streams'] = self.config.max_concurrent_streams
                optimizations.append(f"Multi-stream processing ({self.config.max_concurrent_streams} streams)")
            
            # Memory pool
            if self.config.enable_dynamic_memory_pool:
                self._setup_memory_pool()
                optimizations.append("Dynamic memory pool enabled")
            
            self.logger.info(f"GPU optimizations applied: {optimizations}")
            
        except Exception as e:
            self.logger.warning(f"GPU optimization failed: {e}")
        
        return {
            'gpu_info': gpu_info,
            'optimizations': optimizations
        }
    
    def _optimize_cpu(self) -> Dict[str, Any]:
        """CPU-specific optimizations."""
        optimizations = []
        cpu_info = {}
        
        # CPU information
        cpu_info['cores'] = psutil.cpu_count()
        cpu_info['memory'] = psutil.virtual_memory().total
        
        # Thread optimization
        if self.config.enable_async:
            torch.set_num_threads(min(4, psutil.cpu_count()))
            optimizations.append("CPU thread optimization")
        
        self.logger.info(f"CPU optimizations applied: {optimizations}")
        
        return {
            'cpu_info': cpu_info,
            'optimizations': optimizations
        }
    
    def _setup_memory_pool(self) -> None:
        """Setup GPU memory pool."""
        if torch.cuda.is_available():
            # Set memory fraction
            memory_fraction = min(0.8, self.config.memory_pool_size / 16.0)  # Assume 16GB max
            torch.cuda.set_per_process_memory_fraction(memory_fraction)
            
            self.logger.info(f"GPU memory pool configured: {memory_fraction:.2f} fraction")
    
    def monitor_performance(self, operation: str) -> 'PerformanceContext':
        """Context manager for performance monitoring."""
        return PerformanceContext(self, operation)
    
    def log_system_stats(self) -> Dict[str, Any]:
        """Log current system statistics."""
        stats = {
            'timestamp': time.time(),
            'cpu_usage': psutil.cpu_percent(),
            'memory_usage': psutil.virtual_memory().percent,
            'available_memory': psutil.virtual_memory().available
        }
        
        if torch.cuda.is_available():
            stats['gpu_memory_used'] = torch.cuda.memory_allocated()
            stats['gpu_memory_cached'] = torch.cuda.memory_reserved()
            stats['gpu_utilization'] = self._get_gpu_utilization()
        
        self.perf_logger.log_metric("system_stats", stats)
        return stats
    
    def _get_gpu_utilization(self) -> float:
        """Get GPU utilization percentage."""
        try:
            import nvidia_ml_py3 as nvml
            nvml.nvmlInit()
            handle = nvml.nvmlDeviceGetHandleByIndex(0)
            utilization = nvml.nvmlDeviceGetUtilizationRates(handle)
            return utilization.gpu
        except:
            return 0.0
    
    def optimize_batch_processing(self, audio_chunks: List[Any]) -> List[List[Any]]:
        """Optimize batch processing based on device capabilities."""
        if not audio_chunks:
            return []
        
        batch_size = self._calculate_optimal_batch_size(len(audio_chunks))
        
        batches = []
        for i in range(0, len(audio_chunks), batch_size):
            batch = audio_chunks[i:i + batch_size]
            batches.append(batch)
        
        self.logger.info(f"Optimized batching: {len(batches)} batches of size ~{batch_size}")
        return batches
    
    def _calculate_optimal_batch_size(self, total_items: int) -> int:
        """Calculate optimal batch size based on system resources."""
        if self.config.device == "cuda" and torch.cuda.is_available():
            # GPU batch size optimization
            gpu_memory = torch.cuda.get_device_properties(0).total_memory
            
            if gpu_memory > 8 * 1024**3:  # > 8GB
                base_batch_size = self.config.optimal_batch_size
            else:
                base_batch_size = max(1, self.config.optimal_batch_size // 2)
        else:
            # CPU batch size optimization
            cpu_cores = psutil.cpu_count()
            base_batch_size = min(cpu_cores, 4)
        
        # Adjust based on total items
        return min(base_batch_size, max(1, total_items // 4))
    
    async def process_async_batches(self, batches: List[List[Any]], 
                                  process_func) -> List[Any]:
        """Process batches asynchronously."""
        if not self.config.enable_async:
            # Fallback to sequential processing
            results = []
            for batch in batches:
                results.extend(process_func(batch))
            return results
        
        # Async processing
        tasks = []
        for batch in batches:
            task = asyncio.create_task(self._process_batch_async(batch, process_func))
            tasks.append(task)
        
        batch_results = await asyncio.gather(*tasks)
        
        # Flatten results
        results = []
        for batch_result in batch_results:
            results.extend(batch_result)
        
        return results
    
    async def _process_batch_async(self, batch: List[Any], process_func) -> List[Any]:
        """Process a single batch asynchronously."""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=2) as executor:
            result = await loop.run_in_executor(executor, process_func, batch)
        return result
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary statistics."""
        if not self.processing_times:
            return {'message': 'No performance data available'}
        
        return {
            'total_operations': len(self.processing_times),
            'avg_processing_time': sum(self.processing_times) / len(self.processing_times),
            'min_processing_time': min(self.processing_times),
            'max_processing_time': max(self.processing_times),
            'total_processing_time': sum(self.processing_times),
            'memory_usage_avg': sum(self.memory_usage) / len(self.memory_usage) if self.memory_usage else 0,
            'gpu_usage_avg': sum(self.gpu_usage) / len(self.gpu_usage) if self.gpu_usage else 0
        }


class PerformanceContext:
    """Context manager for performance monitoring."""
    
    def __init__(self, optimizer: PerformanceOptimizer, operation: str):
        self.optimizer = optimizer
        self.operation = operation
        self.start_time = None
        self.start_memory = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.start_memory = psutil.virtual_memory().used
        
        self.optimizer.perf_logger.start_timing(self.operation)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        end_memory = psutil.virtual_memory().used
        
        processing_time = end_time - self.start_time
        memory_delta = end_memory - self.start_memory
        
        # Record metrics
        self.optimizer.processing_times.append(processing_time)
        self.optimizer.memory_usage.append(memory_delta)
        
        if torch.cuda.is_available():
            gpu_usage = self.optimizer._get_gpu_utilization()
            self.optimizer.gpu_usage.append(gpu_usage)
        
        self.optimizer.perf_logger.end_timing(self.operation)
        self.optimizer.perf_logger.log_metric("processing_time", processing_time, "seconds")
        self.optimizer.perf_logger.log_metric("memory_delta", memory_delta / 1024**2, "MB")