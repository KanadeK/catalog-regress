"""A baseline gate for usable gettext translations."""

__version__ = "0.1.0"

from .core import CatalogError, compare_catalogs

__all__ = ["CatalogError", "compare_catalogs", "__version__"]
