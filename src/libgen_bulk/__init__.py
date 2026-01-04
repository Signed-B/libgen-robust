"""libgen-bulk package."""

from .book import Book
from .search import (
    LibgenDatabaseConnectionError,
    LibgenSearch,
    SearchField,
    SearchObject,
    SearchTopic,
)

__all__ = [
    "__version__",
    "Book",
    "LibgenDatabaseConnectionError",
    "LibgenSearch",
    "SearchField",
    "SearchObject",
    "SearchTopic",
]
__version__ = "0.1.0"
