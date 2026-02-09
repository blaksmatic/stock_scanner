import importlib
import pkgutil
from typing import Dict, Type

from scanners.base import BaseScanner

_registry: Dict[str, Type[BaseScanner]] = {}


def register(scanner_cls: Type[BaseScanner]) -> Type[BaseScanner]:
    """Decorator to register a scanner class."""
    instance = scanner_cls()
    _registry[instance.name] = scanner_cls
    return scanner_cls


def get_scanner(name: str) -> BaseScanner:
    """Look up a scanner by name, return an instance."""
    if name not in _registry:
        available = ", ".join(_registry.keys()) or "(none)"
        raise ValueError(f"Unknown scanner '{name}'. Available: {available}")
    return _registry[name]()


def list_scanners() -> Dict[str, str]:
    """Return {name: description} for all registered scanners."""
    return {name: cls().description for name, cls in _registry.items()}


def auto_discover():
    """Import all modules in scanners/ to trigger @register decorators."""
    import scanners

    for _importer, modname, _ispkg in pkgutil.iter_modules(scanners.__path__):
        if modname not in ("base", "registry", "__init__"):
            importlib.import_module(f"scanners.{modname}")
