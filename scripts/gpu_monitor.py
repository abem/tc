#!/usr/bin/env -S uv run python3
"""
GPU monitoring script for transcribe_audio execution.
Shows real-time GPU utilization during processing.
"""

import sys
import time
import threading
import signal
from typing import Optional, Dict, Any

# Check for required dependencies
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import pynvml as nvml
    nvml.nvmlInit()
    NVIDIA_ML_AVAILABLE = True
except ImportError:
    NVIDIA_ML_AVAILABLE = False
except Exception:
    NVIDIA_ML_AVAILABLE = False


def _nvml_str(value):
    """nvidia-ml-py returns str in recent versions, bytes in older pynvml."""
    return value.decode("utf-8") if isinstance(value, bytes) else value

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class GPUMonitor:
    """Real-time GPU monitoring with console output."""
    
    def __init__(self, update_interval: float = 1.0):
        self.update_interval = update_interval
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.gpu_count = 0
        
        # Initialize GPU monitoring
        global NVIDIA_ML_AVAILABLE
        if NVIDIA_ML_AVAILABLE:
            try:
                self.gpu_count = nvml.nvmlDeviceGetCount()
                print(f"🚀 NVIDIA GPU monitoring initialized: {self.gpu_count} GPU(s) detected")
            except Exception as e:
                print(f"⚠️  GPU monitoring initialization failed: {e}")
                NVIDIA_ML_AVAILABLE = False
        else:
            print("⚠️  NVIDIA ML library not available - GPU monitoring disabled")
        
        # Check PyTorch CUDA
        if TORCH_AVAILABLE and torch.cuda.is_available():
            torch_gpu_count = torch.cuda.device_count()
            current_device = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(current_device)
            print(f"🔥 PyTorch CUDA available: {torch_gpu_count} GPU(s), current: {device_name}")
        elif TORCH_AVAILABLE:
            print("⚠️  PyTorch available but CUDA not detected")
        
        # System info
        if PSUTIL_AVAILABLE:
            cpu_count = psutil.cpu_count()
            memory_gb = psutil.virtual_memory().total / (1024**3)
            print(f"💻 System: {cpu_count} CPUs, {memory_gb:.1f}GB RAM")
    
    def get_gpu_metrics(self, gpu_index: int = 0) -> Dict[str, Any]:
        """Get GPU metrics for specified GPU."""
        if not NVIDIA_ML_AVAILABLE:
            return {"error": "NVIDIA ML not available"}
        
        try:
            handle = nvml.nvmlDeviceGetHandleByIndex(gpu_index)
            
            # GPU utilization
            util = nvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_util = util.gpu
            memory_util = util.memory
            
            # Memory info
            mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)
            memory_used_gb = mem_info.used / (1024**3)
            memory_total_gb = mem_info.total / (1024**3)
            memory_percent = (mem_info.used / mem_info.total) * 100
            
            # Temperature
            try:
                temp = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
            except Exception:
                temp = 0
            
            # Power (if available)
            try:
                power = nvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # Convert to watts
            except Exception:
                power = 0
            
            # Clock speeds
            try:
                graphics_clock = nvml.nvmlDeviceGetClockInfo(handle, nvml.NVML_CLOCK_GRAPHICS)
                memory_clock = nvml.nvmlDeviceGetClockInfo(handle, nvml.NVML_CLOCK_MEM)
            except Exception:
                graphics_clock = 0
                memory_clock = 0
            
            return {
                "gpu_utilization": gpu_util,
                "memory_utilization": memory_util,
                "memory_used_gb": memory_used_gb,
                "memory_total_gb": memory_total_gb,
                "memory_percent": memory_percent,
                "temperature": temp,
                "power_watts": power,
                "graphics_clock_mhz": graphics_clock,
                "memory_clock_mhz": memory_clock
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system metrics."""
        if not PSUTIL_AVAILABLE:
            return {"error": "psutil not available"}
        
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = memory.used / (1024**3)
            memory_total_gb = memory.total / (1024**3)
            
            # PyTorch memory if available
            torch_memory_allocated = 0
            torch_memory_reserved = 0
            if TORCH_AVAILABLE and torch.cuda.is_available():
                try:
                    torch_memory_allocated = torch.cuda.memory_allocated() / (1024**3)
                    torch_memory_reserved = torch.cuda.memory_reserved() / (1024**3)
                except Exception:
                    pass
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_used_gb": memory_used_gb,
                "memory_total_gb": memory_total_gb,
                "torch_memory_allocated_gb": torch_memory_allocated,
                "torch_memory_reserved_gb": torch_memory_reserved
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def format_metrics_line(self, gpu_metrics: Dict, sys_metrics: Dict) -> str:
        """Format metrics into a single line for display."""
        if "error" in gpu_metrics and "error" in sys_metrics:
            return "❌ Monitoring unavailable"
        
        parts = []
        
        # GPU metrics first (most important)
        if "error" not in gpu_metrics:
            parts.append(f"GPU:{gpu_metrics['gpu_utilization']:3.0f}%")
            parts.append(f"VRAM:{gpu_metrics['memory_percent']:4.1f}%({gpu_metrics['memory_used_gb']:4.1f}GB)")
            
            if gpu_metrics['temperature'] > 0:
                temp_icon = "🔥" if gpu_metrics['temperature'] > 80 else "🌡️"
                parts.append(f"{temp_icon}{gpu_metrics['temperature']:2.0f}°C")
        
        # System metrics
        if "error" not in sys_metrics:
            parts.append(f"CPU:{sys_metrics['cpu_percent']:3.1f}%")
            parts.append(f"RAM:{sys_metrics['memory_percent']:3.1f}%")
        
        return " | ".join(parts)
    
    def print_static_info(self):
        """Print static system information."""
        print("\n" + "="*80)
        print("🖥️  SYSTEM INFORMATION")
        print("="*80)
        
        # System info
        if PSUTIL_AVAILABLE:
            cpu_info = f"{psutil.cpu_count(logical=False)} cores ({psutil.cpu_count()} threads)"
            memory_gb = psutil.virtual_memory().total / (1024**3)
            print(f"💻 CPU: {cpu_info}")
            print(f"🧠 System RAM: {memory_gb:.1f} GB")
        
        # GPU info
        if NVIDIA_ML_AVAILABLE and self.gpu_count > 0:
            print(f"🎮 GPUs detected: {self.gpu_count}")
            
            for i in range(self.gpu_count):
                try:
                    handle = nvml.nvmlDeviceGetHandleByIndex(i)
                    name = _nvml_str(nvml.nvmlDeviceGetName(handle))
                    mem_info = nvml.nvmlDeviceGetMemoryInfo(handle)
                    memory_gb = mem_info.total / (1024**3)

                    # Driver version
                    try:
                        driver_version = _nvml_str(nvml.nvmlSystemGetDriverVersion())
                    except Exception:
                        driver_version = "Unknown"
                    
                    print(f"   GPU {i}: {name} ({memory_gb:.1f}GB VRAM)")
                    if i == 0:  # Only show driver once
                        print(f"   Driver: {driver_version}")
                        
                except Exception as e:
                    print(f"   GPU {i}: Error getting info - {e}")
        else:
            print("⚠️  No NVIDIA GPUs detected or monitoring unavailable")
        
        # PyTorch info
        if TORCH_AVAILABLE:
            print(f"🔥 PyTorch: {torch.__version__}")
            if torch.cuda.is_available():
                cuda_version = torch.version.cuda
                print(f"🚀 CUDA: {cuda_version} (PyTorch detected)")
                
                for i in range(torch.cuda.device_count()):
                    device_name = torch.cuda.get_device_name(i)
                    print(f"   CUDA Device {i}: {device_name}")
            else:
                print("⚠️  CUDA not available in PyTorch")
        else:
            print("⚠️  PyTorch not available")
        
        print("="*80)
    
    def start_monitoring(self):
        """Start monitoring in a separate thread."""
        if self.monitoring:
            print("⚠️  Monitoring already running")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        print(f"\n📊 Real-time monitoring started (updates every {self.update_interval:.1f}s)")
        print("Press Ctrl+C to stop monitoring\n")
    
    def stop_monitoring(self):
        """Stop monitoring."""
        if not self.monitoring:
            return
        
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        
        print("\n⏹️  Monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            while self.monitoring:
                # Get metrics
                gpu_metrics = self.get_gpu_metrics(0) if self.gpu_count > 0 else {"error": "No GPU"}
                sys_metrics = self.get_system_metrics()
                
                # Format and display
                metrics_line = self.format_metrics_line(gpu_metrics, sys_metrics)
                timestamp = time.strftime("%H:%M:%S")
                
                # Clear line and print new metrics with consistent width
                line_length = 100  # Fixed line width
                output = f"[{timestamp}] {metrics_line}"
                if len(output) > line_length:
                    output = output[:line_length-3] + "..."
                else:
                    output = output.ljust(line_length)
                
                print(f"\r{output}", end="", flush=True)
                
                time.sleep(self.update_interval)
                
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"\n❌ Monitoring error: {e}")


def signal_handler(signum, frame):
    """Handle interrupt signals."""
    print("\n🛑 Monitoring interrupted by user")
    sys.exit(0)


def main():
    """Main function."""
    # Setup signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse arguments
    update_interval = 1.0
    show_static_only = False
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--fast":
            update_interval = 0.5
        elif sys.argv[1] == "--slow":
            update_interval = 2.0
        elif sys.argv[1] == "--info":
            show_static_only = True
        elif sys.argv[1] == "--help":
            print("GPU Monitor Usage:")
            print("  python3 gpu_monitor.py           # Normal monitoring (1s updates)")
            print("  python3 gpu_monitor.py --fast    # Fast monitoring (0.5s updates)")
            print("  python3 gpu_monitor.py --slow    # Slow monitoring (2s updates)")
            print("  python3 gpu_monitor.py --info    # Show system info only")
            return
    
    # Create monitor
    monitor = GPUMonitor(update_interval=update_interval)
    
    # Show static information
    monitor.print_static_info()
    
    if show_static_only:
        return
    
    # Start monitoring
    try:
        monitor.start_monitoring()
        
        # Keep main thread alive
        while monitor.monitoring:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        monitor.stop_monitoring()
        print("👋 Goodbye!")


if __name__ == "__main__":
    main()