"""
Observer Pattern implementation for progress monitoring and event notifications.
Provides decoupled event system for transcription progress, errors, and status updates.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Union, Tuple, Protocol
from datetime import datetime
import logging
import threading
from enum import Enum


class EventType(Enum):
    """Types of events that can be observed."""
    PROGRESS_UPDATE = "progress_update"
    ERROR_OCCURRED = "error_occurred"
    MODEL_LOADED = "model_loaded"
    TRANSCRIPTION_STARTED = "transcription_started"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    BATCH_PROCESSED = "batch_processed"
    CHUNK_PROCESSED = "chunk_processed"
    MEMORY_WARNING = "memory_warning"
    CACHE_UPDATE = "cache_update"


@dataclass
class Event:
    """Event object containing event data."""
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    message: Optional[str] = None
    progress: Optional[float] = None  # 0.0 to 1.0


class Observer(ABC):
    """Abstract observer interface."""
    
    @abstractmethod
    def update(self, event: Event) -> None:
        """Handle event notification."""
        pass
    
    def get_observer_id(self) -> str:
        """Get unique identifier for this observer."""
        return f"{self.__class__.__name__}_{id(self)}"


class Subject(ABC):
    """Abstract subject interface for observable objects."""
    
    def __init__(self):
        self._observers: Dict[str, Observer] = {}
        self._observer_lock = threading.RLock()
    
    def attach_observer(self, observer: Observer) -> None:
        """Attach an observer."""
        with self._observer_lock:
            observer_id = observer.get_observer_id()
            self._observers[observer_id] = observer
    
    def detach_observer(self, observer: Observer) -> None:
        """Detach an observer."""
        with self._observer_lock:
            observer_id = observer.get_observer_id()
            if observer_id in self._observers:
                del self._observers[observer_id]
    
    def notify_observers(self, event: Event) -> None:
        """Notify all observers of an event."""
        with self._observer_lock:
            for observer in self._observers.values():
                try:
                    observer.update(event)
                except Exception as e:
                    # Don't let observer errors break the subject
                    logging.getLogger(self.__class__.__name__).error(
                        f"Observer {observer.get_observer_id()} failed to handle event: {e}"
                    )
    
    def get_observer_count(self) -> int:
        """Get number of attached observers."""
        with self._observer_lock:
            return len(self._observers)


class ProgressObserver(Observer):
    """Observer for progress updates."""
    
    def __init__(self, progress_callback: Optional[Callable[[float, str], None]] = None):
        self.progress_callback = progress_callback
        self.current_progress = 0.0
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def update(self, event: Event) -> None:
        """Handle progress update events."""
        if event.event_type == EventType.PROGRESS_UPDATE:
            progress = event.progress or 0.0
            message = event.message or ""
            self.current_progress = progress
            
            self.logger.info(f"Progress: {progress:.1%} - {message}")
            
            if self.progress_callback:
                self.progress_callback(progress, message)
    
    def get_current_progress(self) -> float:
        """Get current progress value."""
        return self.current_progress


class ConsoleProgressObserver(ProgressObserver):
    """Console-based progress observer with progress bar."""
    
    def __init__(self, bar_width: int = 50):
        super().__init__()
        self.bar_width = bar_width
        self.last_progress = -1
    
    def update(self, event: Event) -> None:
        """Handle progress with console output."""
        if event.event_type == EventType.PROGRESS_UPDATE:
            progress = event.progress or 0.0
            message = event.message or ""
            
            # Only update if progress changed significantly
            if abs(progress - self.last_progress) >= 0.01:
                self._print_progress_bar(progress, message)
                self.last_progress = progress
    
    def _print_progress_bar(self, progress: float, message: str) -> None:
        """Print progress bar to console."""
        filled_width = int(progress * self.bar_width)
        bar = '█' * filled_width + '░' * (self.bar_width - filled_width)
        percentage = progress * 100
        
        print(f'\r[{bar}] {percentage:.1f}% - {message}', end='', flush=True)
        
        if progress >= 1.0:
            print()  # New line when complete


class LoggingObserver(Observer):
    """Observer that logs all events."""
    
    def __init__(self, log_level: int = logging.INFO):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
    
    def update(self, event: Event) -> None:
        """Log event information."""
        timestamp = event.timestamp.strftime("%H:%M:%S")
        source = event.source or "Unknown"
        message = event.message or "No message"
        
        if event.event_type == EventType.ERROR_OCCURRED:
            self.logger.error(f"[{timestamp}] {source}: {message}")
        elif event.event_type == EventType.PROGRESS_UPDATE:
            progress_str = f" ({event.progress:.1%})" if event.progress else ""
            self.logger.info(f"[{timestamp}] {source}: {message}{progress_str}")
        else:
            self.logger.info(f"[{timestamp}] {source}: {event.event_type.value} - {message}")


class MetricsObserver(Observer):
    """Observer that collects metrics and statistics."""
    
    def __init__(self):
        self.metrics: Dict[str, Any] = {
            'events_processed': 0,
            'errors_count': 0,
            'start_time': None,
            'end_time': None,
            'progress_updates': [],
            'processing_times': {},
            'memory_warnings': 0
        }
        self._metrics_lock = threading.RLock()
    
    def update(self, event: Event) -> None:
        """Collect metrics from events."""
        with self._metrics_lock:
            self.metrics['events_processed'] += 1
            
            if event.event_type == EventType.ERROR_OCCURRED:
                self.metrics['errors_count'] += 1
            
            elif event.event_type == EventType.TRANSCRIPTION_STARTED:
                self.metrics['start_time'] = event.timestamp
            
            elif event.event_type == EventType.TRANSCRIPTION_COMPLETED:
                self.metrics['end_time'] = event.timestamp
                if self.metrics['start_time']:
                    duration = (event.timestamp - self.metrics['start_time']).total_seconds()
                    self.metrics['total_duration'] = duration
            
            elif event.event_type == EventType.PROGRESS_UPDATE and event.progress:
                self.metrics['progress_updates'].append({
                    'timestamp': event.timestamp,
                    'progress': event.progress,
                    'message': event.message
                })
            
            elif event.event_type == EventType.BATCH_PROCESSED:
                batch_time = event.data.get('processing_time', 0)
                batch_id = event.data.get('batch_id', 'unknown')
                self.metrics['processing_times'][batch_id] = batch_time
            
            elif event.event_type == EventType.MEMORY_WARNING:
                self.metrics['memory_warnings'] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics."""
        with self._metrics_lock:
            return self.metrics.copy()
    
    def reset_metrics(self) -> None:
        """Reset all metrics."""
        with self._metrics_lock:
            self.metrics = {
                'events_processed': 0,
                'errors_count': 0,
                'start_time': None,
                'end_time': None,
                'progress_updates': [],
                'processing_times': {},
                'memory_warnings': 0
            }


class FileObserver(Observer):
    """Observer that writes events to a file."""
    
    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path
        self._file_lock = threading.RLock()
    
    def update(self, event: Event) -> None:
        """Write event to file."""
        with self._file_lock:
            try:
                with open(self.log_file_path, 'a', encoding='utf-8') as f:
                    timestamp = event.timestamp.isoformat()
                    line = f"{timestamp} | {event.event_type.value} | {event.source} | {event.message}\n"
                    f.write(line)
            except Exception as e:
                logging.getLogger(self.__class__.__name__).error(
                    f"Failed to write to log file: {e}"
                )


class CallbackObserver(Observer):
    """Observer that calls custom callback functions."""
    
    def __init__(self, callbacks: Dict[EventType, Callable[[Event], None]]):
        self.callbacks = callbacks
    
    def update(self, event: Event) -> None:
        """Call appropriate callback for event type."""
        if event.event_type in self.callbacks:
            try:
                self.callbacks[event.event_type](event)
            except Exception as e:
                logging.getLogger(self.__class__.__name__).error(
                    f"Callback failed for {event.event_type}: {e}"
                )


class ObservableTranscriber(Subject):
    """Example observable transcriber that emits events."""
    
    def __init__(self, transcriber):
        super().__init__()
        self.transcriber = transcriber
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def transcribe(self, audio_path: str, **kwargs) -> str:
        """Transcribe with event notifications."""
        try:
            # Notify start
            self.notify_observers(Event(
                event_type=EventType.TRANSCRIPTION_STARTED,
                source=self.__class__.__name__,
                message=f"Starting transcription of {audio_path}",
                data={'audio_path': audio_path, 'kwargs': kwargs}
            ))
            
            # Simulate progress updates during transcription
            self._emit_progress_updates()
            
            # Perform actual transcription
            result = self.transcriber.transcribe(audio_path, **kwargs)
            
            # Notify completion
            self.notify_observers(Event(
                event_type=EventType.TRANSCRIPTION_COMPLETED,
                source=self.__class__.__name__,
                message="Transcription completed successfully",
                progress=1.0,
                data={'result_length': len(result)}
            ))
            
            return result
            
        except Exception as e:
            # Notify error
            self.notify_observers(Event(
                event_type=EventType.ERROR_OCCURRED,
                source=self.__class__.__name__,
                message=f"Transcription failed: {str(e)}",
                data={'error': str(e), 'error_type': type(e).__name__}
            ))
            raise
    
    def _emit_progress_updates(self):
        """Emit simulated progress updates."""
        import time
        
        progress_points = [0.1, 0.3, 0.5, 0.7, 0.9]
        messages = [
            "Loading model...",
            "Processing audio...",
            "Transcribing chunks...",
            "Formatting results...",
            "Finalizing..."
        ]
        
        for progress, message in zip(progress_points, messages):
            self.notify_observers(Event(
                event_type=EventType.PROGRESS_UPDATE,
                source=self.__class__.__name__,
                message=message,
                progress=progress
            ))
            time.sleep(0.1)  # Simulate processing time


class EventBus:
    """Global event bus for decoupled communication."""
    
    _instance: Optional['EventBus'] = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
            self._subscriber_lock = threading.RLock()
            self.initialized = True
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """Subscribe to events of a specific type."""
        with self._subscriber_lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
    
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """Unsubscribe from events."""
        with self._subscriber_lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass
    
    def publish(self, event: Event):
        """Publish event to all subscribers."""
        with self._subscriber_lock:
            if event.event_type in self._subscribers:
                for callback in self._subscribers[event.event_type]:
                    try:
                        callback(event)
                    except Exception as e:
                        logging.getLogger(self.__class__.__name__).error(
                            f"Event subscriber failed: {e}"
                        )
    
    def clear_subscribers(self):
        """Clear all subscribers."""
        with self._subscriber_lock:
            self._subscribers.clear()


class ObserverManager:
    """Manager for creating and configuring observers."""
    
    @staticmethod
    def create_console_observer() -> ConsoleProgressObserver:
        """Create console progress observer."""
        return ConsoleProgressObserver()
    
    @staticmethod
    def create_logging_observer(log_level: int = logging.INFO) -> LoggingObserver:
        """Create logging observer."""
        return LoggingObserver(log_level)
    
    @staticmethod
    def create_metrics_observer() -> MetricsObserver:
        """Create metrics collection observer."""
        return MetricsObserver()
    
    @staticmethod
    def create_file_observer(log_file_path: str) -> FileObserver:
        """Create file logging observer."""
        return FileObserver(log_file_path)
    
    @staticmethod
    def create_standard_observer_set() -> List[Observer]:
        """Create standard set of observers for transcription."""
        return [
            ObserverManager.create_console_observer(),
            ObserverManager.create_logging_observer(),
            ObserverManager.create_metrics_observer()
        ]
    
    @staticmethod
    def attach_observers_to_subject(subject: Subject, observers: List[Observer]):
        """Attach multiple observers to a subject."""
        for observer in observers:
            subject.attach_observer(observer)


# Convenience functions
def create_observable_transcriber(transcriber) -> ObservableTranscriber:
    """Create observable wrapper for any transcriber."""
    return ObservableTranscriber(transcriber)


def setup_standard_monitoring(transcriber) -> Tuple[ObservableTranscriber, List[Observer]]:
    """Setup standard monitoring for a transcriber."""
    observable_transcriber = create_observable_transcriber(transcriber)
    observers = ObserverManager.create_standard_observer_set()
    
    for observer in observers:
        observable_transcriber.attach_observer(observer)
    
    return observable_transcriber, observers


def get_metrics_from_observers(observers: List[Observer]) -> Dict[str, Any]:
    """Extract metrics from metrics observers."""
    all_metrics = {}
    
    for observer in observers:
        if isinstance(observer, MetricsObserver):
            all_metrics.update(observer.get_metrics())
    
    return all_metrics