"""
Dependency Injection container and related patterns for decoupling dependencies.
Provides flexible dependency management with support for singletons, factories, and configuration-based injection.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Type, TypeVar, Callable, Optional, Union, get_type_hints
from dataclasses import dataclass, field
import inspect
import logging
from pathlib import Path

T = TypeVar('T')


class DIContainer:
    """Dependency Injection container with support for different registration types."""
    
    def __init__(self):
        self._services: Dict[Type, Any] = {}
        self._singletons: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}
        self._configurations: Dict[str, Any] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register_singleton(self, interface: Type[T], implementation: Union[Type[T], T]) -> None:
        """Register a singleton service."""
        if inspect.isclass(implementation):
            # Store class, instantiate on first access
            self._services[interface] = implementation
        else:
            # Store instance directly
            self._singletons[interface] = implementation
        
        self.logger.debug(f"Registered singleton: {interface.__name__}")
    
    def register_transient(self, interface: Type[T], implementation: Type[T]) -> None:
        """Register a transient service (new instance each time)."""
        self._services[interface] = implementation
        self.logger.debug(f"Registered transient: {interface.__name__}")
    
    def register_factory(self, interface: Type[T], factory: Callable[[], T]) -> None:
        """Register a factory function for service creation."""
        self._factories[interface] = factory
        self.logger.debug(f"Registered factory: {interface.__name__}")
    
    def register_instance(self, interface: Type[T], instance: T) -> None:
        """Register an existing instance."""
        self._singletons[interface] = instance
        self.logger.debug(f"Registered instance: {interface.__name__}")
    
    def register_configuration(self, key: str, value: Any) -> None:
        """Register configuration value."""
        self._configurations[key] = value
        self.logger.debug(f"Registered configuration: {key}")
    
    def resolve(self, interface: Type[T]) -> T:
        """Resolve service by interface type."""
        # Check if already instantiated singleton
        if interface in self._singletons:
            return self._singletons[interface]
        
        # Check if factory exists
        if interface in self._factories:
            instance = self._factories[interface]()
            return instance
        
        # Check if service is registered
        if interface in self._services:
            service_class = self._services[interface]
            instance = self._create_instance(service_class)
            
            # Store as singleton if it was registered as singleton
            if self._is_singleton_registration(interface):
                self._singletons[interface] = instance
            
            return instance
        
        raise ValueError(f"Service not registered: {interface.__name__}")
    
    def resolve_configuration(self, key: str, default: Any = None) -> Any:
        """Resolve configuration value."""
        return self._configurations.get(key, default)
    
    def _create_instance(self, service_class: Type[T]) -> T:
        """Create instance with dependency injection."""
        try:
            # Get constructor signature
            signature = inspect.signature(service_class.__init__)
            type_hints = get_type_hints(service_class.__init__)
            
            # Build constructor arguments
            kwargs = {}
            for param_name, param in signature.parameters.items():
                if param_name == 'self':
                    continue
                
                # Try to resolve parameter type
                param_type = type_hints.get(param_name)
                if param_type and param_type in self._services or param_type in self._singletons:
                    kwargs[param_name] = self.resolve(param_type)
                elif param.default != inspect.Parameter.empty:
                    # Use default value if available
                    continue
                else:
                    # Try to resolve by parameter name from configuration
                    config_value = self.resolve_configuration(param_name)
                    if config_value is not None:
                        kwargs[param_name] = config_value
            
            return service_class(**kwargs)
            
        except Exception as e:
            self.logger.error(f"Failed to create instance of {service_class.__name__}: {str(e)}")
            raise
    
    def _is_singleton_registration(self, interface: Type) -> bool:
        """Check if service was registered as singleton."""
        # This is a simplified check - in a full implementation,
        # we might track registration types separately
        return True  # Default to singleton for simplicity
    
    def clear(self):
        """Clear all registrations."""
        self._services.clear()
        self._singletons.clear()
        self._factories.clear()
        self._configurations.clear()


@dataclass
class ServiceConfiguration:
    """Configuration for service registration."""
    interface: Type
    implementation: Optional[Type] = None
    instance: Optional[Any] = None
    factory: Optional[Callable] = None
    scope: str = 'singleton'  # 'singleton', 'transient'
    configuration: Dict[str, Any] = field(default_factory=dict)


class ConfigurationLoader:
    """Load dependency injection configuration from various sources."""
    
    @staticmethod
    def from_yaml(config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    @staticmethod
    def from_dict(config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Load configuration from dictionary."""
        return config_dict.copy()


class ServiceRegistry:
    """Registry for managing service configurations."""
    
    def __init__(self):
        self.configurations: List[ServiceConfiguration] = []
    
    def add_service(self, config: ServiceConfiguration):
        """Add service configuration."""
        self.configurations.append(config)
    
    def configure_container(self, container: DIContainer):
        """Configure DI container with registered services."""
        for config in self.configurations:
            if config.instance is not None:
                container.register_instance(config.interface, config.instance)
            elif config.factory is not None:
                container.register_factory(config.interface, config.factory)
            elif config.scope == 'singleton':
                container.register_singleton(config.interface, config.implementation)
            elif config.scope == 'transient':
                container.register_transient(config.interface, config.implementation)
            
            # Register configuration values
            for key, value in config.configuration.items():
                container.register_configuration(key, value)


# Abstract interfaces for common services
class StorageHandler(ABC):
    """Abstract storage handler interface."""
    
    @abstractmethod
    def download(self, file_id: str) -> str:
        pass
    
    @abstractmethod
    def upload(self, file_path: str) -> dict:
        pass


class LoggingHandler(ABC):
    """Abstract logging handler interface."""
    
    @abstractmethod
    def get_logger(self, name: str) -> logging.Logger:
        pass


class ConfigurationProvider(ABC):
    """Abstract configuration provider interface."""
    
    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any:
        pass


# Concrete implementations
class GDriveStorageHandler(StorageHandler):
    """Google Drive storage handler implementation."""
    
    def __init__(self, gdrive_handler: Optional[Any] = None):
        if gdrive_handler is None:
            from gdrive_handler import GDriveHandler
            self.gdrive_handler = GDriveHandler()
        else:
            self.gdrive_handler = gdrive_handler
    
    def download(self, file_id: str) -> str:
        return self.gdrive_handler.download_file(file_id)
    
    def upload(self, file_path: str) -> dict:
        return self.gdrive_handler.upload_file(file_path)


class StandardLoggingHandler(LoggingHandler):
    """Standard Python logging handler implementation."""
    
    def __init__(self, log_level: str = 'INFO'):
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
    
    def get_logger(self, name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(self.log_level)
        return logger


class YAMLConfigurationProvider(ConfigurationProvider):
    """YAML file-based configuration provider."""
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        self.config_path = Path(config_path)
        self._config_cache: Optional[Dict[str, Any]] = None
    
    def get_config(self, key: str, default: Any = None) -> Any:
        if self._config_cache is None:
            self._load_config()
        
        keys = key.split('.')
        value = self._config_cache
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def _load_config(self):
        """Load configuration from YAML file."""
        if self.config_path.exists():
            import yaml
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config_cache = yaml.safe_load(f)
        else:
            self._config_cache = {}


class TranscriberService:
    """Example service that uses dependency injection."""
    
    def __init__(
        self,
        storage_handler: StorageHandler,
        logging_handler: LoggingHandler,
        config_provider: ConfigurationProvider
    ):
        self.storage = storage_handler
        self.logger = logging_handler.get_logger(self.__class__.__name__)
        self.config = config_provider
    
    def process_audio(self, file_id: str) -> str:
        """Process audio file using injected dependencies."""
        try:
            # Download file using storage handler
            local_path = self.storage.download(file_id)
            self.logger.info(f"Downloaded file to: {local_path}")
            
            # Get processing configuration
            model_name = self.config.get_config('models.default', 'whisper-large-v3')
            self.logger.info(f"Using model: {model_name}")
            
            # Process audio (placeholder)
            result = f"Processed {local_path} with {model_name}"
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing audio: {str(e)}")
            raise


def create_default_container() -> DIContainer:
    """Create DI container with default service registrations."""
    container = DIContainer()
    
    # Register core services
    container.register_singleton(StorageHandler, GDriveStorageHandler)
    container.register_singleton(LoggingHandler, StandardLoggingHandler)
    container.register_singleton(ConfigurationProvider, YAMLConfigurationProvider)
    
    # Register application services
    container.register_transient(TranscriberService, TranscriberService)
    
    # Register configurations
    container.register_configuration('log_level', 'INFO')
    container.register_configuration('config_path', 'config/config.yaml')
    
    return container


def create_container_from_config(config_path: str) -> DIContainer:
    """Create DI container from configuration file."""
    config_data = ConfigurationLoader.from_yaml(config_path)
    container = DIContainer()
    
    # Register services based on configuration
    services_config = config_data.get('dependency_injection', {}).get('services', {})
    
    for service_name, service_config in services_config.items():
        # This would be expanded to handle more complex configurations
        interface_name = service_config.get('interface')
        implementation_name = service_config.get('implementation')
        scope = service_config.get('scope', 'singleton')
        
        # Dynamic class loading would be implemented here
        # For now, this is a placeholder
    
    return container


class ServiceLocator:
    """Service locator pattern as an alternative to pure DI."""
    
    _instance: Optional['ServiceLocator'] = None
    _container: Optional[DIContainer] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def initialize(cls, container: DIContainer):
        """Initialize service locator with DI container."""
        cls._container = container
    
    @classmethod
    def get_service(cls, interface: Type[T]) -> T:
        """Get service from container."""
        if cls._container is None:
            raise RuntimeError("Service locator not initialized")
        return cls._container.resolve(interface)
    
    @classmethod
    def get_configuration(cls, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        if cls._container is None:
            raise RuntimeError("Service locator not initialized")
        return cls._container.resolve_configuration(key, default)


# Decorator for automatic dependency injection
def inject(**dependencies):
    """Decorator for automatic dependency injection."""
    def decorator(cls):
        original_init = cls.__init__
        
        def new_init(self, **kwargs):
            # Resolve dependencies if not provided
            for dep_name, dep_type in dependencies.items():
                if dep_name not in kwargs:
                    try:
                        kwargs[dep_name] = ServiceLocator.get_service(dep_type)
                    except Exception:
                        # If service locator fails, skip injection
                        pass
            
            original_init(self, **kwargs)
        
        cls.__init__ = new_init
        return cls
    
    return decorator


# Example usage with decorator
@inject(
    storage_handler=StorageHandler,
    logging_handler=LoggingHandler,
    config_provider=ConfigurationProvider
)
class DecoratedTranscriberService:
    """Example service using injection decorator."""
    
    def __init__(
        self,
        storage_handler: StorageHandler,
        logging_handler: LoggingHandler,
        config_provider: ConfigurationProvider
    ):
        self.storage = storage_handler
        self.logger = logging_handler.get_logger(self.__class__.__name__)
        self.config = config_provider