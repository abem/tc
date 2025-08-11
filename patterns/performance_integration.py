"""
Integration of performance monitoring with existing OOP patterns.
Demonstrates how to integrate the monitoring system with transcription operations.
"""

import time
import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass

from .monitoring import PerformanceProfiler, create_console_bottleneck_callback, create_metrics_logger_callback
from .observers import Observer, Event, EventType
from .commands import Command, CommandResult
from .strategies import BatchSizeStrategy, DeviceInfo, AudioInfo


@dataclass
class PerformanceAwareConfig:
    """Configuration for performance-aware processing."""
    enable_monitoring: bool = True
    monitoring_interval: float = 1.0
    bottleneck_detection: bool = True
    auto_adjustment: bool = True
    performance_logging: bool = True
    report_generation: bool = True


class PerformanceObserver(Observer):
    """Observer that monitors performance metrics and bottlenecks."""
    
    def __init__(self, profiler: PerformanceProfiler):
        self.profiler = profiler
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Add callbacks to profiler
        self.profiler.add_bottleneck_callback(self._handle_bottleneck)
        self.profiler.add_metrics_callback(self._handle_metrics)
        
        # Performance thresholds
        self.performance_thresholds = {
            'cpu_warning': 75.0,
            'memory_warning': 80.0,
            'gpu_low_utilization': 30.0
        }
    
    def update(self, event: Event) -> None:
        """Handle transcription events and correlate with performance data."""
        if event.event_type == EventType.TRANSCRIPTION_STARTED:
            self.profiler.start_monitoring()
            self.logger.info("Performance monitoring started for transcription")
        
        elif event.event_type == EventType.TRANSCRIPTION_COMPLETED:
            # Generate performance report
            report = self.profiler.generate_performance_report(duration_minutes=10)
            
            # Log summary
            if 'system_performance' in report:
                perf = report['system_performance']
                self.logger.info(
                    f"Transcription performance summary: "
                    f"CPU {perf['cpu']['average']:.1f}%, "
                    f"Memory {perf['memory']['average']:.1f}%, "
                    f"GPU {perf['gpu']['average_utilization']:.1f}%"
                )
            
            self.profiler.stop_monitoring()
    
    def _handle_bottleneck(self, bottleneck):
        """Handle detected bottlenecks."""
        self.logger.warning(
            f"Performance bottleneck detected: {bottleneck.bottleneck_type} "
            f"({bottleneck.severity}) - {bottleneck.description}"
        )
    
    def _handle_metrics(self, system_metrics, process_metrics):
        """Handle periodic metrics updates."""
        # Could implement custom logic here
        pass


class AdaptiveBatchSizeStrategy(BatchSizeStrategy):
    """Batch size strategy that adapts based on real-time performance monitoring."""
    
    def __init__(self, profiler: PerformanceProfiler, base_strategy: BatchSizeStrategy):
        self.profiler = profiler
        self.base_strategy = base_strategy
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Adaptation settings
        self.adaptation_enabled = True
        self.last_adjustment_time = 0
        self.adjustment_cooldown = 30.0  # seconds
        self.batch_size_history = []
        self.max_batch_size = 64
        self.min_batch_size = 1
    
    def calculate_batch_size(self, audio_info: AudioInfo, device_info: DeviceInfo) -> int:
        """Calculate batch size with real-time performance adaptation."""
        # Get base batch size
        base_batch_size = self.base_strategy.calculate_batch_size(audio_info, device_info)
        
        if not self.adaptation_enabled:
            return base_batch_size
        
        # Check if we should adapt based on current performance
        current_time = time.time()
        if current_time - self.last_adjustment_time < self.adjustment_cooldown:
            return base_batch_size
        
        # Get current performance metrics
        try:
            system_metrics, process_metrics = self.profiler.get_current_metrics()
            
            # Get recent bottlenecks
            recent_bottlenecks = self.profiler.get_recent_bottlenecks(duration_minutes=2)
            
            # Adapt batch size based on performance
            adapted_batch_size = self._adapt_batch_size(
                base_batch_size, system_metrics, process_metrics, recent_bottlenecks
            )
            
            if adapted_batch_size != base_batch_size:
                self.logger.info(
                    f"Adapted batch size from {base_batch_size} to {adapted_batch_size} "
                    f"based on performance metrics"
                )
                self.last_adjustment_time = current_time
            
            # Track batch size history
            self.batch_size_history.append({
                'timestamp': current_time,
                'base_size': base_batch_size,
                'adapted_size': adapted_batch_size,
                'cpu_percent': system_metrics.cpu_percent,
                'memory_percent': system_metrics.memory_percent,
                'gpu_utilization': system_metrics.gpu_utilization
            })
            
            # Keep only recent history
            cutoff_time = current_time - 300  # 5 minutes
            self.batch_size_history = [
                h for h in self.batch_size_history 
                if h['timestamp'] > cutoff_time
            ]
            
            return adapted_batch_size
            
        except Exception as e:
            self.logger.error(f"Error in adaptive batch size calculation: {e}")
            return base_batch_size
    
    def _adapt_batch_size(self, base_size, system_metrics, process_metrics, bottlenecks):
        """Adapt batch size based on performance indicators."""
        adapted_size = base_size
        
        # Check for critical bottlenecks - reduce immediately
        critical_bottlenecks = [b for b in bottlenecks if b.severity == 'critical']
        if critical_bottlenecks:
            for bottleneck in critical_bottlenecks:
                if bottleneck.bottleneck_type in ['memory', 'gpu_memory']:
                    adapted_size = max(self.min_batch_size, adapted_size // 2)
                elif bottleneck.bottleneck_type == 'gpu_temperature':
                    adapted_size = max(self.min_batch_size, adapted_size // 2)
        
        # Check for high resource usage
        if system_metrics.memory_percent > 90:
            adapted_size = max(self.min_batch_size, adapted_size // 2)
        elif system_metrics.memory_percent > 85:
            adapted_size = max(self.min_batch_size, int(adapted_size * 0.8))
        
        # Check GPU memory if available
        if system_metrics.gpu_memory_total_gb > 0:
            gpu_memory_percent = (system_metrics.gpu_memory_used_gb / system_metrics.gpu_memory_total_gb) * 100
            if gpu_memory_percent > 90:
                adapted_size = max(self.min_batch_size, adapted_size // 2)
            elif gpu_memory_percent > 85:
                adapted_size = max(self.min_batch_size, int(adapted_size * 0.8))
        
        # Check for underutilization - increase batch size
        if (system_metrics.memory_percent < 60 and 
            system_metrics.cpu_percent < 70 and
            system_metrics.gpu_utilization > 0 and system_metrics.gpu_utilization < 60):
            
            # Only increase if no recent bottlenecks
            if not bottlenecks:
                adapted_size = min(self.max_batch_size, int(adapted_size * 1.2))
        
        return adapted_size
    
    def get_memory_threshold(self) -> float:
        """Get memory threshold from base strategy."""
        return self.base_strategy.get_memory_threshold()


class PerformanceAwareTranscribeCommand(Command):
    """Command that integrates performance monitoring with transcription."""
    
    def __init__(
        self,
        audio_path: str,
        transcriber: Any,
        config: PerformanceAwareConfig,
        profiler: Optional[PerformanceProfiler] = None
    ):
        super().__init__()
        self.audio_path = audio_path
        self.transcriber = transcriber
        self.config = config
        self.profiler = profiler or PerformanceProfiler(
            monitoring_interval=config.monitoring_interval,
            enable_bottleneck_detection=config.bottleneck_detection
        )
        
        # Setup callbacks if enabled
        if config.performance_logging:
            self.profiler.add_bottleneck_callback(create_console_bottleneck_callback())
            self.profiler.add_metrics_callback(create_metrics_logger_callback())
    
    def execute(self) -> CommandResult:
        """Execute transcription with performance monitoring."""
        self._start_timing()
        
        try:
            if self.config.enable_monitoring:
                self.profiler.start_monitoring()
            
            # Execute transcription
            result = self.transcriber.transcribe(self.audio_path)
            
            # Collect performance data
            performance_data = None
            if self.config.enable_monitoring:
                duration_minutes = max(1, int(self.get_duration() / 60))
                performance_data = self.profiler.generate_performance_report(duration_minutes)
                
                if self.config.report_generation:
                    # Save detailed report
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    report_path = f"performance_report_{timestamp}.json"
                    self.profiler.save_report(performance_data, report_path)
                
                self.profiler.stop_monitoring()
            
            return self._create_result(
                success=True,
                data=result,
                message="Transcription completed with performance monitoring",
                metadata={
                    'performance_report': performance_data,
                    'monitoring_enabled': self.config.enable_monitoring
                }
            )
            
        except Exception as e:
            if self.config.enable_monitoring:
                self.profiler.stop_monitoring()
            
            return self._create_result(
                success=False,
                error=e,
                message=f"Transcription failed: {str(e)}"
            )


@contextmanager
def performance_monitoring_context(
    config: PerformanceAwareConfig,
    profiler: Optional[PerformanceProfiler] = None
):
    """Context manager for performance monitoring during transcription operations."""
    if not config.enable_monitoring:
        yield None
        return
    
    monitoring_profiler = profiler or PerformanceProfiler(
        monitoring_interval=config.monitoring_interval,
        enable_bottleneck_detection=config.bottleneck_detection
    )
    
    try:
        monitoring_profiler.start_monitoring()
        
        if config.performance_logging:
            monitoring_profiler.add_bottleneck_callback(create_console_bottleneck_callback())
            monitoring_profiler.add_metrics_callback(create_metrics_logger_callback())
        
        yield monitoring_profiler
        
    finally:
        if config.report_generation:
            report = monitoring_profiler.generate_performance_report()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            report_path = f"performance_report_{timestamp}.json"
            monitoring_profiler.save_report(report, report_path)
            print(f"📊 Performance report saved: {report_path}")
        
        monitoring_profiler.stop_monitoring()


class PerformanceOptimizedTranscriber:
    """Enhanced transcriber with integrated performance monitoring and optimization."""
    
    def __init__(self, base_transcriber: Any, config: PerformanceAwareConfig):
        self.base_transcriber = base_transcriber
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize performance monitoring
        self.profiler = PerformanceProfiler(
            monitoring_interval=config.monitoring_interval,
            enable_bottleneck_detection=config.bottleneck_detection
        )
        
        # Setup adaptive strategies if base transcriber supports them
        if hasattr(base_transcriber, 'batch_processor') and hasattr(base_transcriber.batch_processor, 'batch_strategy'):
            original_strategy = base_transcriber.batch_processor.batch_strategy
            adaptive_strategy = AdaptiveBatchSizeStrategy(self.profiler, original_strategy)
            base_transcriber.batch_processor.batch_strategy = adaptive_strategy
            self.logger.info("Enabled adaptive batch size strategy")
    
    def transcribe(self, audio_path: str, **kwargs) -> str:
        """Transcribe with performance monitoring and optimization."""
        with performance_monitoring_context(self.config, self.profiler) as monitoring_profiler:
            try:
                # Execute transcription
                result = self.base_transcriber.transcribe(audio_path, **kwargs)
                
                if monitoring_profiler:
                    # Log final performance summary
                    report = monitoring_profiler.generate_performance_report(duration_minutes=5)
                    if 'system_performance' in report:
                        perf = report['system_performance']
                        self.logger.info(
                            f"Transcription completed - Performance summary: "
                            f"CPU {perf['cpu']['average']:.1f}%, "
                            f"Memory {perf['memory']['average']:.1f}%, "
                            f"GPU {perf['gpu']['average_utilization']:.1f}%"
                        )
                
                return result
                
            except Exception as e:
                self.logger.error(f"Performance-optimized transcription failed: {e}")
                raise
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics."""
        try:
            system_metrics, process_metrics = self.profiler.get_current_metrics()
            recent_bottlenecks = self.profiler.get_recent_bottlenecks(duration_minutes=10)
            
            return {
                'current_metrics': {
                    'cpu_percent': system_metrics.cpu_percent,
                    'memory_percent': system_metrics.memory_percent,
                    'memory_used_gb': system_metrics.memory_used_gb,
                    'gpu_utilization': system_metrics.gpu_utilization,
                    'gpu_memory_used_gb': system_metrics.gpu_memory_used_gb,
                    'gpu_temperature': system_metrics.gpu_temperature
                },
                'process_metrics': {
                    'cpu_percent': process_metrics.cpu_percent,
                    'memory_mb': process_metrics.memory_mb,
                    'thread_count': process_metrics.thread_count,
                    'gpu_memory_allocated_mb': process_metrics.gpu_memory_allocated_mb
                },
                'recent_bottlenecks': [
                    {
                        'type': b.bottleneck_type,
                        'severity': b.severity,
                        'description': b.description
                    }
                    for b in recent_bottlenecks
                ],
                'performance_monitoring': {
                    'enabled': self.config.enable_monitoring,
                    'monitoring_interval': self.config.monitoring_interval,
                    'bottleneck_detection': self.config.bottleneck_detection
                }
            }
        except Exception as e:
            self.logger.error(f"Error getting performance stats: {e}")
            return {'error': str(e)}


# Convenience functions
def create_performance_aware_transcriber(
    base_transcriber: Any,
    enable_monitoring: bool = True,
    enable_adaptation: bool = True,
    monitoring_interval: float = 1.0
) -> PerformanceOptimizedTranscriber:
    """Create a performance-aware transcriber with monitoring and optimization."""
    config = PerformanceAwareConfig(
        enable_monitoring=enable_monitoring,
        monitoring_interval=monitoring_interval,
        bottleneck_detection=True,
        auto_adjustment=enable_adaptation,
        performance_logging=True,
        report_generation=True
    )
    
    return PerformanceOptimizedTranscriber(base_transcriber, config)


def monitor_function_performance(func: Callable, *args, **kwargs) -> tuple[Any, Dict[str, Any]]:
    """Monitor the performance of any function execution."""
    config = PerformanceAwareConfig(enable_monitoring=True, performance_logging=False)
    
    with performance_monitoring_context(config) as profiler:
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            performance_data = None
            if profiler:
                duration_minutes = max(1, int(execution_time / 60))
                performance_data = profiler.generate_performance_report(duration_minutes)
            
            return result, {
                'execution_time': execution_time,
                'performance_report': performance_data
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            raise e