"""
Demonstration of the performance monitoring system.
Shows how to use the monitoring capabilities with the transcription system.
"""

import sys
import time
import logging
from pathlib import Path

# Add patterns to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from patterns.monitoring import (
    PerformanceProfiler, 
    create_console_bottleneck_callback,
    create_metrics_logger_callback,
    monitor_transcription_performance
)
from patterns.performance_integration import (
    PerformanceAwareConfig,
    PerformanceOptimizedTranscriber,
    create_performance_aware_transcriber,
    performance_monitoring_context,
    monitor_function_performance
)
from patterns.refactored_components import RefactoredWhisperTranscriber
from patterns.observers import setup_standard_monitoring


def demo_basic_monitoring():
    """Demonstrate basic performance monitoring."""
    print("\n" + "="*60)
    print("BASIC PERFORMANCE MONITORING DEMO")
    print("="*60)
    
    # Create profiler with console output
    profiler = PerformanceProfiler(
        monitoring_interval=0.5,
        enable_bottleneck_detection=True
    )
    
    # Add console callbacks
    profiler.add_bottleneck_callback(create_console_bottleneck_callback())
    profiler.add_metrics_callback(create_metrics_logger_callback())
    
    print("📊 Starting performance monitoring...")
    
    try:
        profiler.start_monitoring()
        
        # Simulate some work
        print("🔄 Simulating CPU-intensive work...")
        start_time = time.time()
        
        # Simulate processing
        for i in range(10):
            # Simulate CPU work
            sum([j**2 for j in range(100000)])
            time.sleep(0.5)
            print(f"   Progress: {(i+1)*10}%")
        
        processing_time = time.time() - start_time
        
        # Generate performance report
        print("📈 Generating performance report...")
        report = profiler.generate_performance_report(duration_minutes=1)
        
        # Display summary
        if 'system_performance' in report:
            perf = report['system_performance']
            print(f"\n📊 Performance Summary:")
            print(f"   CPU Average: {perf['cpu']['average']:.1f}%")
            print(f"   Memory Average: {perf['memory']['average']:.1f}%")
            print(f"   GPU Available: {perf['gpu']['available']}")
            if perf['gpu']['available']:
                print(f"   GPU Utilization: {perf['gpu']['average_utilization']:.1f}%")
        
        if 'bottlenecks' in report:
            bottlenecks = report['bottlenecks']
            print(f"   Total Bottlenecks: {bottlenecks['total_count']}")
            if bottlenecks['total_count'] > 0:
                print(f"   By Severity: {bottlenecks['by_severity']}")
        
        # Save report
        profiler.save_report(report, "demo_performance_report.json")
        print("💾 Report saved to demo_performance_report.json")
        
    finally:
        profiler.stop_monitoring()
        print("⏹️  Monitoring stopped")


def demo_adaptive_strategies():
    """Demonstrate adaptive batch size strategy."""
    print("\n" + "="*60)
    print("ADAPTIVE STRATEGY DEMO")
    print("="*60)
    
    from patterns.strategies import AdaptiveBatchSizeStrategy, create_device_info, create_audio_info
    from patterns.performance_integration import AdaptiveBatchSizeStrategy as PerfAdaptiveBatchSizeStrategy
    
    # Create profiler
    profiler = PerformanceProfiler()
    profiler.start_monitoring()
    
    try:
        # Create base strategy
        base_strategy = AdaptiveBatchSizeStrategy()
        
        # Create performance-aware adaptive strategy
        adaptive_strategy = PerfAdaptiveBatchSizeStrategy(profiler, base_strategy)
        
        # Simulate audio processing with different scenarios
        device_info = create_device_info()
        
        print("🎯 Testing adaptive batch size calculation...")
        
        # Test with different audio configurations
        test_scenarios = [
            {"duration": 30, "chunks": 10, "name": "Short Audio"},
            {"duration": 300, "chunks": 50, "name": "Medium Audio"},
            {"duration": 1800, "chunks": 200, "name": "Long Audio"}
        ]
        
        for scenario in test_scenarios:
            # Create mock audio info
            audio_info_dict = {
                'duration': scenario['duration'],
                'sample_rate': 16000,
                'channels': 1,
                'file_size': scenario['duration'] * 32000,  # Estimate
                'num_chunks': scenario['chunks']
            }
            
            # Create audio info object
            from patterns.strategies import AudioInfo
            audio_info = AudioInfo(**audio_info_dict)
            
            # Calculate batch size
            batch_size = adaptive_strategy.calculate_batch_size(audio_info, device_info)
            
            print(f"   {scenario['name']}: {scenario['chunks']} chunks → batch size {batch_size}")
            
            # Simulate some processing to trigger adaptation
            time.sleep(1)
    
    finally:
        profiler.stop_monitoring()


def demo_performance_aware_transcriber():
    """Demonstrate performance-aware transcriber (mock)."""
    print("\n" + "="*60)
    print("PERFORMANCE-AWARE TRANSCRIBER DEMO")
    print("="*60)
    
    # Create a mock transcriber for demonstration
    class MockTranscriber:
        def __init__(self):
            self.model_name = "mock-whisper-model"
        
        def transcribe(self, audio_path: str, **kwargs) -> str:
            print(f"🎙️  Mock transcribing: {audio_path}")
            
            # Simulate transcription work with varying intensity
            for i in range(5):
                # Simulate CPU/memory intensive work
                if i < 2:
                    # Light work
                    time.sleep(0.5)
                elif i < 4:
                    # Heavy work (simulate high resource usage)
                    sum([j**2 for j in range(200000)])
                    time.sleep(0.3)
                else:
                    # Normal work
                    time.sleep(0.4)
                
                print(f"   Processing chunk {i+1}/5...")
            
            return f"Mock transcription result for {Path(audio_path).name}"
    
    # Create base transcriber
    base_transcriber = MockTranscriber()
    
    # Create performance-aware wrapper
    perf_transcriber = create_performance_aware_transcriber(
        base_transcriber,
        enable_monitoring=True,
        enable_adaptation=True,
        monitoring_interval=0.5
    )
    
    print("🚀 Starting performance-aware transcription...")
    
    # Perform transcription with monitoring
    result = perf_transcriber.transcribe("mock_audio_file.wav")
    
    print(f"✅ Transcription completed: {result}")
    
    # Get performance statistics
    stats = perf_transcriber.get_performance_stats()
    if 'error' not in stats:
        print(f"\n📊 Current Performance Stats:")
        current = stats['current_metrics']
        print(f"   CPU: {current['cpu_percent']:.1f}%")
        print(f"   Memory: {current['memory_percent']:.1f}%")
        print(f"   GPU Utilization: {current['gpu_utilization']:.1f}%")
        
        if stats['recent_bottlenecks']:
            print(f"   Recent Bottlenecks: {len(stats['recent_bottlenecks'])}")


def demo_context_manager():
    """Demonstrate performance monitoring context manager."""
    print("\n" + "="*60)
    print("CONTEXT MANAGER DEMO")
    print("="*60)
    
    config = PerformanceAwareConfig(
        enable_monitoring=True,
        monitoring_interval=0.5,
        bottleneck_detection=True,
        performance_logging=True,
        report_generation=True
    )
    
    print("🔄 Using performance monitoring context manager...")
    
    with performance_monitoring_context(config) as profiler:
        print("   📊 Monitoring active")
        
        # Simulate some processing work
        for i in range(3):
            print(f"   Processing step {i+1}/3...")
            
            # Simulate different types of work
            if i == 0:
                # CPU intensive
                sum([j**3 for j in range(150000)])
            elif i == 1:
                # Memory allocation
                data = [list(range(10000)) for _ in range(100)]
                del data
            else:
                # I/O simulation
                time.sleep(1)
    
    print("✅ Context manager completed - report saved automatically")


def demo_function_monitoring():
    """Demonstrate function performance monitoring."""
    print("\n" + "="*60)
    print("FUNCTION MONITORING DEMO")
    print("="*60)
    
    def sample_processing_function(iterations: int, work_intensity: int):
        """Sample function to monitor."""
        print(f"🔄 Processing {iterations} iterations with intensity {work_intensity}")
        
        results = []
        for i in range(iterations):
            # Simulate work based on intensity
            work_result = sum([j**2 for j in range(work_intensity * 10000)])
            results.append(work_result)
            
            if i % max(1, iterations // 5) == 0:
                print(f"   Progress: {i+1}/{iterations}")
        
        return f"Processed {len(results)} items"
    
    print("📊 Monitoring function performance...")
    
    # Monitor function execution
    result, performance_data = monitor_function_performance(
        sample_processing_function, 
        iterations=10, 
        work_intensity=50
    )
    
    print(f"✅ Function result: {result}")
    print(f"⏱️  Execution time: {performance_data['execution_time']:.2f} seconds")
    
    if performance_data['performance_report']:
        report = performance_data['performance_report']
        if 'system_performance' in report:
            perf = report['system_performance']
            print(f"📈 Performance during execution:")
            print(f"   Average CPU: {perf['cpu']['average']:.1f}%")
            print(f"   Peak CPU: {perf['cpu']['maximum']:.1f}%")
            print(f"   Average Memory: {perf['memory']['average']:.1f}%")


def demo_integration_with_observers():
    """Demonstrate integration with observer pattern."""
    print("\n" + "="*60)
    print("OBSERVER INTEGRATION DEMO")
    print("="*60)
    
    from patterns.observers import ObservableTranscriber
    from patterns.performance_integration import PerformanceObserver
    
    # Create mock transcriber
    class MockTranscriber:
        def transcribe(self, audio_path: str) -> str:
            # Simulate transcription with performance impact
            for i in range(3):
                sum([j**2 for j in range(100000)])
                time.sleep(0.5)
            return f"Transcribed: {audio_path}"
    
    # Create observable wrapper
    base_transcriber = MockTranscriber()
    observable_transcriber = ObservableTranscriber(base_transcriber)
    
    # Create performance profiler and observer
    profiler = PerformanceProfiler()
    performance_observer = PerformanceObserver(profiler)
    
    # Attach observer
    observable_transcriber.attach_observer(performance_observer)
    
    print("🔗 Performance observer attached to transcriber")
    print("🚀 Starting monitored transcription...")
    
    # Perform transcription - this will trigger events
    result = observable_transcriber.transcribe("test_audio.wav")
    
    print(f"✅ Integration demo completed: {result}")


def main():
    """Run all performance monitoring demonstrations."""
    print("🎯 PERFORMANCE MONITORING SYSTEM DEMONSTRATIONS")
    print("=" * 80)
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Run all demos
        demo_basic_monitoring()
        demo_adaptive_strategies()
        demo_performance_aware_transcriber()
        demo_context_manager()
        demo_function_monitoring()
        demo_integration_with_observers()
        
        print("\n" + "="*80)
        print("🎉 ALL PERFORMANCE MONITORING DEMOS COMPLETED SUCCESSFULLY!")
        print("="*80)
        
        print("\n📋 Generated Files:")
        print("   📄 demo_performance_report.json - Basic monitoring report")
        print("   📄 performance_report_*.json - Context manager reports")
        
        print("\n💡 Next Steps:")
        print("   1. Integrate monitoring with your transcription pipeline")
        print("   2. Customize bottleneck detection thresholds")
        print("   3. Add custom performance observers")
        print("   4. Enable adaptive batch size strategies")
        
    except KeyboardInterrupt:
        print("\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()