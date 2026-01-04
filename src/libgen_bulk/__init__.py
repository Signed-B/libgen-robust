"""libgen-bulk package."""

from .book import Book
from .search import LibgenSearch, SearchField, SearchObject, SearchTopic

__all__ = [
    "__version__",
    "Book",
    "LibgenSearch",
    "SearchField",
    "SearchObject",
    "SearchTopic",
]
__version__ = "0.1.0"
