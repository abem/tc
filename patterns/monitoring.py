"""
Performance monitoring and profiling system for transcription operations.
Provides real-time GPU/CPU monitoring, memory profiling, and bottleneck detection.
"""

import time
import threading
import psutil
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from collections import deque
import json
from pathlib import Path

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import nvidia_ml_py3 as nvml
    NVIDIA_ML_AVAILABLE = True
    nvml.nvmlInit()
except ImportError:
    NVIDIA_ML_AVAILABLE = False


@dataclass
class SystemMetrics:
    """System performance metrics at a point in time."""
    timestamp: datetime = field(default_factory=datetime.now)
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    gpu_utilization: float = 0.0
    gpu_memory_used_gb: float = 0.0
    gpu_memory_total_gb: float = 0.0
    gpu_temperature: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0


@dataclass
class ProcessMetrics:
    """Process-specific performance metrics."""
    timestamp: datetime = field(default_factory=datetime.now)
    process_name: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    thread_count: int = 0
    file_descriptors: int = 0
    gpu_memory_allocated_mb: float = 0.0
    gpu_memory_reserved_mb: float = 0.0


@dataclass
class BottleneckInfo:
    """Information about detected performance bottlenecks."""
    timestamp: datetime = field(default_factory=datetime.now)
    bottleneck_type: str = ""  # cpu, memory, gpu, io
    severity: str = ""  # low, medium, high, critical
    current_value: float = 0.0
    threshold: float = 0.0
    description: str = ""
    recommendation: str = ""


class PerformanceMetricsCollector:
    """Collects system and process performance metrics."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.process = psutil.Process()
        self.gpu_device_count = 0
        
        # Initialize GPU monitoring if available
        if NVIDIA_ML_AVAILABLE:
            try:
                self.gpu_device_count = nvml.nvmlDeviceGetCount()
                self.logger.info(f"NVIDIA GPU monitoring initialized: {self.gpu_device_count} devices")
            except Exception as e:
                self.logger.warning(f"Failed to initialize NVIDIA GPU monitoring: {e}")
                NVIDIA_ML_AVAILABLE = False
    
    def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system performance metrics."""
        metrics = SystemMetrics()
        
        try:
            # CPU metrics
            metrics.cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            metrics.memory_percent = memory.percent
            metrics.memory_used_gb = memory.used / (1024**3)
            metrics.memory_total_gb = memory.total / (1024**3)
            
            # Disk I/O metrics
            disk_io = psutil.disk_io_counters()
            if disk_io:
                metrics.disk_io_read_mb = disk_io.read_bytes / (1024**2)
                metrics.disk_io_write_mb = disk_io.write_bytes / (1024**2)
            
            # Network metrics
            net_io = psutil.net_io_counters()
            if net_io:
                metrics.network_sent_mb = net_io.bytes_sent / (1024**2)
                metrics.network_recv_mb = net_io.bytes_recv / (1024**2)
            
            # GPU metrics
            if NVIDIA_ML_AVAILABLE and self.gpu_device_count > 0:
                gpu_metrics = self._collect_gpu_metrics()
                metrics.gpu_utilization = gpu_metrics.get('utilization', 0.0)
                metrics.gpu_memory_used_gb = gpu_metrics.get('memory_used_gb', 0.0)
                metrics.gpu_memory_total_gb = gpu_metrics.get('memory_total_gb', 0.0)
                metrics.gpu_temperature = gpu_metrics.get('temperature', 0.0)
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")
        
        return metrics
    
    def collect_process_metrics(self) -> ProcessMetrics:
        """Collect current process performance metrics."""
        metrics = ProcessMetrics()
        
        try:
            metrics.process_name = self.process.name()
            metrics.cpu_percent = self.process.cpu_percent()
            metrics.memory_mb = self.process.memory_info().rss / (1024**2)
            metrics.thread_count = self.process.num_threads()
            
            try:
                metrics.file_descriptors = self.process.num_fds()
            except (AttributeError, psutil.AccessDenied):
                metrics.file_descriptors = 0
            
            # PyTorch GPU memory metrics
            if TORCH_AVAILABLE and torch.cuda.is_available():
                metrics.gpu_memory_allocated_mb = torch.cuda.memory_allocated() / (1024**2)
                metrics.gpu_memory_reserved_mb = torch.cuda.memory_reserved() / (1024**2)
            
        except Exception as e:
            self.logger.error(f"Error collecting process metrics: {e}")
        
        return metrics
    
    def _collect_gpu_metrics(self) -> Dict[str, float]:
        """Collect GPU metrics from NVIDIA Management Library."""
        gpu_metrics = {}
        
        try:
            # Use first GPU for primary metrics
            handle = nvml.nvmlDeviceGetHandleByIndex(0)
            
            # GPU utilization
            util = nvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_metrics['utilization'] = float(util.gpu)
            
            # GPU memory
            mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_metrics['memory_used_gb'] = mem_info.used / (1024**3)
            gpu_metrics['memory_total_gb'] = mem_info.total / (1024**3)
            
            # GPU temperature
            temp = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
            gpu_metrics['temperature'] = float(temp)
            
        except Exception as e:
            self.logger.error(f"Error collecting GPU metrics: {e}")
        
        return gpu_metrics


class BottleneckDetector:
    """Detects performance bottlenecks based on metrics."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Configurable thresholds
        self.thresholds = {
            'cpu_high': 80.0,
            'cpu_critical': 95.0,
            'memory_high': 85.0,
            'memory_critical': 95.0,
            'gpu_utilization_low': 30.0,
            'gpu_memory_high': 85.0,
            'gpu_memory_critical': 95.0,
            'gpu_temperature_high': 80.0,
            'gpu_temperature_critical': 90.0,
        }
    
    def detect_bottlenecks(
        self,
        system_metrics: SystemMetrics,
        process_metrics: ProcessMetrics
    ) -> List[BottleneckInfo]:
        """Detect performance bottlenecks from current metrics."""
        bottlenecks = []
        
        # CPU bottleneck detection
        if system_metrics.cpu_percent > self.thresholds['cpu_critical']:
            bottlenecks.append(BottleneckInfo(
                bottleneck_type='cpu',
                severity='critical',
                current_value=system_metrics.cpu_percent,
                threshold=self.thresholds['cpu_critical'],
                description=f"Critical CPU usage: {system_metrics.cpu_percent:.1f}%",
                recommendation="Consider reducing batch size or enabling CPU-specific optimizations"
            ))
        elif system_metrics.cpu_percent > self.thresholds['cpu_high']:
            bottlenecks.append(BottleneckInfo(
                bottleneck_type='cpu',
                severity='high',
                current_value=system_metrics.cpu_percent,
                threshold=self.thresholds['cpu_high'],
                description=f"High CPU usage: {system_metrics.cpu_percent:.1f}%",
                recommendation="Monitor CPU usage and consider optimizing processing strategies"
            ))
        
        # Memory bottleneck detection
        if system_metrics.memory_percent > self.thresholds['memory_critical']:
            bottlenecks.append(BottleneckInfo(
                bottleneck_type='memory',
                severity='critical',
                current_value=system_metrics.memory_percent,
                threshold=self.thresholds['memory_critical'],
                description=f"Critical memory usage: {system_metrics.memory_percent:.1f}%",
                recommendation="Reduce model cache size or enable memory cleanup strategies"
            ))
        elif system_metrics.memory_percent > self.thresholds['memory_high']:
            bottlenecks.append(BottleneckInfo(
                bottleneck_type='memory',
                severity='high',
                current_value=system_metrics.memory_percent,
                threshold=self.thresholds['memory_high'],
                description=f"High memory usage: {system_metrics.memory_percent:.1f}%",
                recommendation="Consider reducing batch size or clearing unnecessary caches"
            ))
        
        # GPU bottleneck detection
        if system_metrics.gpu_utilization > 0:  # Only if GPU is available
            # Low GPU utilization (potential underutilization)
            if system_metrics.gpu_utilization < self.thresholds['gpu_utilization_low']:
                bottlenecks.append(BottleneckInfo(
                    bottleneck_type='gpu',
                    severity='medium',
                    current_value=system_metrics.gpu_utilization,
                    threshold=self.thresholds['gpu_utilization_low'],
                    description=f"Low GPU utilization: {system_metrics.gpu_utilization:.1f}%",
                    recommendation="Consider increasing batch size or using GPU-optimized strategies"
                ))
            
            # High GPU memory usage
            gpu_memory_percent = (system_metrics.gpu_memory_used_gb / system_metrics.gpu_memory_total_gb) * 100 if system_metrics.gpu_memory_total_gb > 0 else 0
            
            if gpu_memory_percent > self.thresholds['gpu_memory_critical']:
                bottlenecks.append(BottleneckInfo(
                    bottleneck_type='gpu_memory',
                    severity='critical',
                    current_value=gpu_memory_percent,
                    threshold=self.thresholds['gpu_memory_critical'],
                    description=f"Critical GPU memory usage: {gpu_memory_percent:.1f}%",
                    recommendation="Reduce batch size immediately to prevent OOM errors"
                ))
            elif gpu_memory_percent > self.thresholds['gpu_memory_high']:
                bottlenecks.append(BottleneckInfo(
                    bottleneck_type='gpu_memory',
                    severity='high',
                    current_value=gpu_memory_percent,
                    threshold=self.thresholds['gpu_memory_high'],
                    description=f"High GPU memory usage: {gpu_memory_percent:.1f}%",
                    recommendation="Consider reducing batch size or clearing GPU cache"
                ))
            
            # GPU temperature
            if system_metrics.gpu_temperature > self.thresholds['gpu_temperature_critical']:
                bottlenecks.append(BottleneckInfo(
                    bottleneck_type='gpu_temperature',
                    severity='critical',
                    current_value=system_metrics.gpu_temperature,
                    threshold=self.thresholds['gpu_temperature_critical'],
                    description=f"Critical GPU temperature: {system_metrics.gpu_temperature:.1f}°C",
                    recommendation="Reduce processing load immediately to prevent thermal throttling"
                ))
            elif system_metrics.gpu_temperature > self.thresholds['gpu_temperature_high']:
                bottlenecks.append(BottleneckInfo(
                    bottleneck_type='gpu_temperature',
                    severity='high',
                    current_value=system_metrics.gpu_temperature,
                    threshold=self.thresholds['gpu_temperature_high'],
                    description=f"High GPU temperature: {system_metrics.gpu_temperature:.1f}°C",
                    recommendation="Monitor GPU temperature and consider reducing batch size"
                ))
        
        return bottlenecks
    
    def update_thresholds(self, new_thresholds: Dict[str, float]):
        """Update detection thresholds."""
        self.thresholds.update(new_thresholds)
        self.logger.info(f"Updated bottleneck detection thresholds: {new_thresholds}")


class PerformanceProfiler:
    """Main performance profiler with real-time monitoring."""
    
    def __init__(
        self,
        monitoring_interval: float = 1.0,
        history_size: int = 1000,
        enable_bottleneck_detection: bool = True
    ):
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size
        self.enable_bottleneck_detection = enable_bottleneck_detection
        
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Components
        self.metrics_collector = PerformanceMetricsCollector()
        self.bottleneck_detector = BottleneckDetector() if enable_bottleneck_detection else None
        
        # Data storage
        self.system_metrics_history = deque(maxlen=history_size)
        self.process_metrics_history = deque(maxlen=history_size)
        self.bottlenecks_history = deque(maxlen=history_size)
        
        # Monitoring thread
        self._monitoring_thread = None
        self._stop_monitoring = threading.Event()
        self._monitoring_lock = threading.RLock()
        
        # Callbacks
        self.bottleneck_callbacks: List[Callable[[BottleneckInfo], None]] = []
        self.metrics_callbacks: List[Callable[[SystemMetrics, ProcessMetrics], None]] = []
    
    def start_monitoring(self):
        """Start real-time performance monitoring."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self.logger.warning("Monitoring is already running")
            return
        
        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="PerformanceMonitor"
        )
        self._monitoring_thread.start()
        self.logger.info("Performance monitoring started")
    
    def stop_monitoring(self):
        """Stop real-time performance monitoring."""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._stop_monitoring.set()
            self._monitoring_thread.join(timeout=5.0)
            self.logger.info("Performance monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop running in separate thread."""
        self.logger.info("Performance monitoring loop started")
        
        while not self._stop_monitoring.wait(self.monitoring_interval):
            try:
                # Collect metrics
                system_metrics = self.metrics_collector.collect_system_metrics()
                process_metrics = self.metrics_collector.collect_process_metrics()
                
                with self._monitoring_lock:
                    # Store metrics
                    self.system_metrics_history.append(system_metrics)
                    self.process_metrics_history.append(process_metrics)
                    
                    # Detect bottlenecks
                    if self.bottleneck_detector:
                        bottlenecks = self.bottleneck_detector.detect_bottlenecks(
                            system_metrics, process_metrics
                        )
                        
                        for bottleneck in bottlenecks:
                            self.bottlenecks_history.append(bottleneck)
                            
                            # Call bottleneck callbacks
                            for callback in self.bottleneck_callbacks:
                                try:
                                    callback(bottleneck)
                                except Exception as e:
                                    self.logger.error(f"Error in bottleneck callback: {e}")
                    
                    # Call metrics callbacks
                    for callback in self.metrics_callbacks:
                        try:
                            callback(system_metrics, process_metrics)
                        except Exception as e:
                            self.logger.error(f"Error in metrics callback: {e}")
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
        
        self.logger.info("Performance monitoring loop ended")
    
    def get_current_metrics(self) -> tuple[SystemMetrics, ProcessMetrics]:
        """Get current system and process metrics."""
        system_metrics = self.metrics_collector.collect_system_metrics()
        process_metrics = self.metrics_collector.collect_process_metrics()
        return system_metrics, process_metrics
    
    def get_metrics_history(
        self,
        duration_minutes: Optional[int] = None
    ) -> tuple[List[SystemMetrics], List[ProcessMetrics]]:
        """Get metrics history for specified duration."""
        with self._monitoring_lock:
            system_history = list(self.system_metrics_history)
            process_history = list(self.process_metrics_history)
        
        if duration_minutes is not None:
            cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
            system_history = [m for m in system_history if m.timestamp >= cutoff_time]
            process_history = [m for m in process_history if m.timestamp >= cutoff_time]
        
        return system_history, process_history
    
    def get_recent_bottlenecks(
        self,
        duration_minutes: int = 10,
        severity_filter: Optional[str] = None
    ) -> List[BottleneckInfo]:
        """Get recent bottlenecks within specified duration."""
        with self._monitoring_lock:
            bottlenecks = list(self.bottlenecks_history)
        
        cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
        recent_bottlenecks = [b for b in bottlenecks if b.timestamp >= cutoff_time]
        
        if severity_filter:
            recent_bottlenecks = [b for b in recent_bottlenecks if b.severity == severity_filter]
        
        return recent_bottlenecks
    
    def add_bottleneck_callback(self, callback: Callable[[BottleneckInfo], None]):
        """Add callback for bottleneck notifications."""
        self.bottleneck_callbacks.append(callback)
    
    def add_metrics_callback(self, callback: Callable[[SystemMetrics, ProcessMetrics], None]):
        """Add callback for metrics updates."""
        self.metrics_callbacks.append(callback)
    
    def generate_performance_report(self, duration_minutes: int = 60) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        system_history, process_history = self.get_metrics_history(duration_minutes)
        recent_bottlenecks = self.get_recent_bottlenecks(duration_minutes)
        
        if not system_history:
            return {"error": "No metrics data available"}
        
        # Calculate statistics
        cpu_values = [m.cpu_percent for m in system_history]
        memory_values = [m.memory_percent for m in system_history]
        gpu_util_values = [m.gpu_utilization for m in system_history if m.gpu_utilization > 0]
        
        report = {
            "report_period": {
                "duration_minutes": duration_minutes,
                "start_time": system_history[0].timestamp.isoformat(),
                "end_time": system_history[-1].timestamp.isoformat(),
                "data_points": len(system_history)
            },
            "system_performance": {
                "cpu": {
                    "average": sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                    "maximum": max(cpu_values) if cpu_values else 0,
                    "minimum": min(cpu_values) if cpu_values else 0
                },
                "memory": {
                    "average": sum(memory_values) / len(memory_values) if memory_values else 0,
                    "maximum": max(memory_values) if memory_values else 0,
                    "minimum": min(memory_values) if memory_values else 0
                },
                "gpu": {
                    "available": len(gpu_util_values) > 0,
                    "average_utilization": sum(gpu_util_values) / len(gpu_util_values) if gpu_util_values else 0,
                    "maximum_utilization": max(gpu_util_values) if gpu_util_values else 0,
                    "minimum_utilization": min(gpu_util_values) if gpu_util_values else 0
                }
            },
            "bottlenecks": {
                "total_count": len(recent_bottlenecks),
                "by_severity": {
                    "critical": len([b for b in recent_bottlenecks if b.severity == "critical"]),
                    "high": len([b for b in recent_bottlenecks if b.severity == "high"]),
                    "medium": len([b for b in recent_bottlenecks if b.severity == "medium"]),
                    "low": len([b for b in recent_bottlenecks if b.severity == "low"])
                },
                "by_type": {}
            },
            "recommendations": []
        }
        
        # Bottleneck analysis by type
        bottleneck_types = {}
        for bottleneck in recent_bottlenecks:
            if bottleneck.bottleneck_type not in bottleneck_types:
                bottleneck_types[bottleneck.bottleneck_type] = []
            bottleneck_types[bottleneck.bottleneck_type].append(bottleneck)
        
        report["bottlenecks"]["by_type"] = {
            bt: len(bottlenecks) for bt, bottlenecks in bottleneck_types.items()
        }
        
        # Generate recommendations
        if report["system_performance"]["cpu"]["average"] > 80:
            report["recommendations"].append("High CPU usage detected. Consider reducing batch size or optimizing CPU-intensive operations.")
        
        if report["system_performance"]["memory"]["average"] > 80:
            report["recommendations"].append("High memory usage detected. Consider reducing model cache size or enabling memory cleanup strategies.")
        
        if report["system_performance"]["gpu"]["available"] and report["system_performance"]["gpu"]["average_utilization"] < 50:
            report["recommendations"].append("Low GPU utilization detected. Consider increasing batch size or using GPU-optimized processing strategies.")
        
        if report["bottlenecks"]["by_severity"]["critical"] > 0:
            report["recommendations"].append("Critical bottlenecks detected. Immediate action required to prevent system instability.")
        
        return report
    
    def save_report(self, report: Dict[str, Any], filepath: str):
        """Save performance report to file."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            self.logger.info(f"Performance report saved to {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save performance report: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.start_monitoring()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_monitoring()


# Convenience functions and integration helpers

def create_console_bottleneck_callback() -> Callable[[BottleneckInfo], None]:
    """Create a callback that prints bottlenecks to console."""
    def callback(bottleneck: BottleneckInfo):
        severity_emoji = {
            'low': '🟡',
            'medium': '🟠', 
            'high': '🔴',
            'critical': '🚨'
        }
        emoji = severity_emoji.get(bottleneck.severity, '⚠️')
        
        print(f"{emoji} {bottleneck.severity.upper()} {bottleneck.bottleneck_type.upper()}: {bottleneck.description}")
        if bottleneck.recommendation:
            print(f"   💡 Recommendation: {bottleneck.recommendation}")
    
    return callback


def create_metrics_logger_callback(logger: Optional[logging.Logger] = None) -> Callable[[SystemMetrics, ProcessMetrics], None]:
    """Create a callback that logs metrics periodically."""
    if logger is None:
        logger = logging.getLogger("PerformanceMonitor")
    
    last_log_time = [time.time()]  # Use list for mutable reference
    
    def callback(system_metrics: SystemMetrics, process_metrics: ProcessMetrics):
        current_time = time.time()
        if current_time - last_log_time[0] >= 30.0:  # Log every 30 seconds
            logger.info(
                f"Performance: CPU {system_metrics.cpu_percent:.1f}%, "
                f"Memory {system_metrics.memory_percent:.1f}%, "
                f"GPU {system_metrics.gpu_utilization:.1f}%"
            )
            last_log_time[0] = current_time
    
    return callback


def monitor_transcription_performance(transcriber_func: Callable, *args, **kwargs):
    """Decorator/context manager to monitor transcription performance."""
    with PerformanceProfiler(monitoring_interval=0.5, enable_bottleneck_detection=True) as profiler:
        # Add console bottleneck alerts
        profiler.add_bottleneck_callback(create_console_bottleneck_callback())
        
        # Add metrics logging
        profiler.add_metrics_callback(create_metrics_logger_callback())
        
        start_time = time.time()
        
        try:
            # Execute transcription
            result = transcriber_func(*args, **kwargs)
            
            # Generate report
            duration_minutes = max(1, int((time.time() - start_time) / 60))
            report = profiler.generate_performance_report(duration_minutes)
            
            # Save report with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = f"performance_report_{timestamp}.json"
            profiler.save_report(report, report_path)
            
            print(f"📊 Performance report saved: {report_path}")
            
            return result
            
        except Exception as e:
            print(f"❌ Error during monitored transcription: {e}")
            raise


# Integration with existing patterns
def create_observable_performance_profiler() -> PerformanceProfiler:
    """Create a profiler integrated with observer pattern."""
    from .observers import EventBus, Event, EventType
    
    profiler = PerformanceProfiler()
    event_bus = EventBus()
    
    def bottleneck_to_event(bottleneck: BottleneckInfo):
        event = Event(
            event_type=EventType.ERROR_OCCURRED if bottleneck.severity in ['high', 'critical'] else EventType.PROGRESS_UPDATE,
            message=bottleneck.description,
            data={
                'bottleneck_type': bottleneck.bottleneck_type,
                'severity': bottleneck.severity,
                'current_value': bottleneck.current_value,
                'threshold': bottleneck.threshold,
                'recommendation': bottleneck.recommendation
            },
            source='PerformanceProfiler'
        )
        event_bus.publish(event)
    
    profiler.add_bottleneck_callback(bottleneck_to_event)
    
    return profiler