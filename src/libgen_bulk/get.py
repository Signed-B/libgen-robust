"""Resilient download workflow for Libgen results."""

from __future__ import annotations

import logging
import random
import re
import time
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import requests

from .book import Book
from .search import (
    LibgenDatabaseConnectionError,
    LibgenReadConnectionLimitError,
    LibgenSearch,
    SearchField,
    SearchObject,
    SearchTopic,
)
from .select import Selector


class GetError(RuntimeError):
    """Raised when a download request cannot be completed."""


class NoResultsError(GetError):
    """Raised when no candidate results are found."""


class ScoreThresholdError(GetError):
    """Raised when no result meets the score threshold."""


class DownloadError(GetError):
    """Raised for non-retryable download failures."""


class RetryableDownloadError(GetError):
    """Raised for retryable download failures."""


class GetQueryMethod(Enum):
    TITLE = "title"
    TITLEKEYWORD = "title_keyword"
    AUTHOR = "author"
    AUTHORLAST = "author_last"
    TITLEAUTHOR = "title_author"
    TITLEKEYWORDAUTHORLAST = "title_keyword_author_last"


GetType = GetQueryMethod


DEFAULT_SEARCH_ORDER = [
    GetQueryMethod.TITLE,
    GetQueryMethod.TITLEKEYWORD,
    GetQueryMethod.TITLEAUTHOR,
    GetQueryMethod.TITLEKEYWORDAUTHORLAST,
    GetQueryMethod.AUTHOR,
    GetQueryMethod.AUTHORLAST,
]

DEFAULT_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


class Getter:
    def __init__(
        self,
        score_threshold: int,
        search_order: Optional[Iterable[GetQueryMethod]] = None,
        *,
        timeout: int = 20,
        max_attempts: int = 5,
        backoff_base: float = 1.0,
        backoff_factor: float = 2.0,
        backoff_max: float = 60.0,
        jitter: float = 0.2,
        mirror: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
        search_objects: Optional[Iterable[SearchObject]] = None,
        search_topics: Optional[Iterable[SearchTopic]] = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self.score_threshold = self._validate_score_threshold(score_threshold)
        self.search_order = self._normalize_search_order(search_order)
        self.timeout = self._validate_timeout(timeout)
        self.max_attempts = self._validate_max_attempts(max_attempts)
        self.backoff_base = self._validate_backoff_base(backoff_base)
        self.backoff_factor = self._validate_backoff_factor(backoff_factor)
        self.backoff_max = self._validate_backoff_max(backoff_max)
        self.jitter = self._validate_jitter(jitter)
        self.mirror = self._normalize_mirror(mirror)
        self.output_dir = self._normalize_output_dir(output_dir)
        self.search_objects = list(search_objects) if search_objects else [SearchObject.FILES]
        self.search_topics = list(search_topics) if search_topics else [SearchTopic.LIBGEN]

    def get(
        self,
        title: str,
        author: str | List[str],
        year: Optional[int],
        type: Optional[GetType] = None,
        *,
        mirror: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
    ) -> Path:
        mirror = self._normalize_mirror(mirror) if mirror else self.mirror
        if not mirror:
            raise ValueError("mirror must be set for search")
        output_dir = self._normalize_output_dir(output_dir) if output_dir else self.output_dir
        selector = Selector(mirror=mirror)
        search_methods = self._resolve_search_methods(type)
        errors = []
        for method in search_methods:
            query, fields = self._build_query(title, author, method)
            try:
                books = self._with_backoff(
                    lambda: self._execute_search(query, fields, mirror),
                    self._is_retryable_search_error,
                    f"search:{method.value}",
                )
            except Exception as exc:
                errors.append(exc)
                continue
            if not books:
                errors.append(NoResultsError(f"No results for {method.value}"))
                continue
            best_book, best_score = self._select_best_book(
                selector, title, author, year, books
            )
            if best_score < self.score_threshold:
                errors.append(
                    ScoreThresholdError(
                        f"Best score {best_score:.2f} below threshold {self.score_threshold}"
                    )
                )
                continue
            self._with_backoff(
                lambda: best_book.get_download_links(timeout=self.timeout),
                self._is_retryable_search_error,
                "download-links",
            )
            return self.download(best_book, mirror=mirror, output_dir=output_dir)
        if errors:
            raise errors[-1]
        raise NoResultsError("No results found")

    def download(
        self,
        book: Book,
        *,
        mirror: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
    ) -> Path:
        if not book.download_link:
            raise ValueError("book.download_link must be set before downloading")
        resolved = self._resolve_download_link(book.download_link, mirror)
        output_dir = self._normalize_output_dir(output_dir) if output_dir else self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        return self._with_backoff(
            lambda: self._download_file(resolved, book, output_dir),
            self._is_retryable_download_error,
            "download-file",
        )

    def _execute_search(
        self,
        query: str,
        fields: List[SearchField],
        mirror: str,
    ) -> List[Book]:
        search = LibgenSearch(
            query=query,
            mirror=mirror,
            search_field=fields,
            search_objects=self.search_objects,
            search_topics=self.search_topics,
            timeout=self.timeout,
        )
        return search.execute()

    def _select_best_book(
        self,
        selector: Selector,
        title: str,
        author: str | List[str],
        year: Optional[int],
        books: List[Book],
    ) -> tuple[Book, float]:
        context = selector._build_context(
            title,
            selector._normalize_authors(author),
            year,
            books,
        )
        ranked = selector._rank_books(books, context)
        best = ranked[0]
        best_score = selector._score_book(best, context)
        selector._apply_download_links([best])
        return best, best_score

    def _download_file(self, url: str, book: Book, output_dir: Path) -> Path:
        response = requests.get(url, stream=True, timeout=self.timeout)
        if response.status_code in {429} or response.status_code >= 500:
            raise RetryableDownloadError(f"HTTP {response.status_code} for {url}")
        if response.status_code >= 400:
            raise DownloadError(f"HTTP {response.status_code} for {url}")
        filename = self._build_filename(book, response)
        target = output_dir / filename
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {target}")
        temp_target = target.with_suffix(target.suffix + ".part")
        try:
            with temp_target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
        except Exception:
            if temp_target.exists():
                temp_target.unlink()
            raise
        temp_target.replace(target)
        return target

    def _build_filename(self, book: Book, response: requests.Response) -> str:
        header = response.headers.get("Content-Disposition", "")
        match = re.search(r'filename="?([^";]+)"?', header)
        if match:
            return self._sanitize_filename(match.group(1))
        base = book.title or "libgen"
        ext = ""
        if book.extension:
            ext = f".{book.extension.lstrip('.')}"
        else:
            parsed = urlparse(response.url)
            if "." in Path(parsed.path).name:
                ext = f".{Path(parsed.path).name.split('.')[-1]}"
        slug = self._sanitize_filename(base)
        suffix = f"_{book.md5}" if book.md5 else ""
        return f"{slug}{suffix}{ext}"

    def _sanitize_filename(self, name: str) -> str:
        cleaned = re.sub(r"[^\w.-]+", "_", name.strip())
        cleaned = re.sub(r"_+", "_", cleaned).strip("._")
        return cleaned or "libgen"

    def _build_query(
        self,
        title: str,
        author: str | List[str],
        method: GetQueryMethod,
    ) -> tuple[str, List[SearchField]]:
        title = title.strip()
        authors = self._split_authors(author)
        if method == GetQueryMethod.TITLE:
            query = title
            fields = [SearchField.TITLE]
        elif method == GetQueryMethod.TITLEKEYWORD:
            query = " ".join(self._title_keywords(title))
            fields = [SearchField.TITLE]
        elif method == GetQueryMethod.AUTHOR:
            query = " ".join(authors)
            fields = [SearchField.AUTHORS]
        elif method == GetQueryMethod.AUTHORLAST:
            query = " ".join(self._author_last_names(authors))
            fields = [SearchField.AUTHORS]
        elif method == GetQueryMethod.TITLEAUTHOR:
            query = " ".join(part for part in [title, authors[0] if authors else ""] if part)
            fields = [SearchField.TITLE, SearchField.AUTHORS]
        elif method == GetQueryMethod.TITLEKEYWORDAUTHORLAST:
            keywords = " ".join(self._title_keywords(title))
            last = self._author_last_names(authors)
            query = " ".join(part for part in [keywords, last[0] if last else ""] if part)
            fields = [SearchField.TITLE, SearchField.AUTHORS]
        else:
            raise ValueError(f"Unsupported method {method}")
        if not query:
            raise ValueError(f"Query is empty for method {method.value}")
        return query, fields

    def _split_authors(self, authors: str | List[str]) -> List[str]:
        if isinstance(authors, str):
            parts = [authors]
        elif isinstance(authors, list):
            parts = authors
        else:
            raise TypeError("author must be a string or list of strings")
        results: List[str] = []
        for part in parts:
            if not isinstance(part, str):
                raise TypeError("author must be a string or list of strings")
            for chunk in part.split(";"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                if " and " in chunk.lower():
                    results.extend(
                        piece.strip()
                        for piece in chunk.split(" and ")
                        if piece.strip()
                    )
                else:
                    results.append(chunk)
        return results

    def _author_last_names(self, authors: List[str]) -> List[str]:
        last_names = []
        for author in authors:
            tokens = [token for token in author.split() if token]
            if tokens:
                last_names.append(tokens[-1])
        return last_names

    def _title_keywords(self, title: str) -> List[str]:
        normalized = self._normalize_text(title)
        tokens = [token for token in normalized.split() if token]
        return [token for token in tokens if token not in DEFAULT_STOPWORDS]

    def _normalize_text(self, text: str) -> str:
        normalized = text.lower()
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _resolve_search_methods(self, type: Optional[GetType]) -> List[GetQueryMethod]:
        if type is None:
            return list(self.search_order)
        if not isinstance(type, GetQueryMethod):
            raise TypeError("type must be a GetQueryMethod or None")
        return [type]

    def _resolve_download_link(self, link: str, mirror: Optional[str]) -> str:
        parsed = urlparse(link)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return link
        if not mirror:
            raise ValueError("mirror must be set to resolve download_link")
        return urljoin(mirror, link)

    def _with_backoff(self, action, retryable, label: str):
        for attempt in range(1, self.max_attempts + 1):
            try:
                return action()
            except Exception as exc:
                if not retryable(exc) or attempt == self.max_attempts:
                    raise
                wait = min(
                    self.backoff_base * (self.backoff_factor ** (attempt - 1)),
                    self.backoff_max,
                )
                wait += random.uniform(0, self.jitter * wait)
                self._logger.warning(
                    "Retryable error during %s (attempt %s/%s): %s; waiting %.2fs",
                    label,
                    attempt,
                    self.max_attempts,
                    exc,
                    wait,
                )
                time.sleep(wait)

    def _is_retryable_search_error(self, exc: Exception) -> bool:
        retryables = (
            requests.exceptions.RequestException,
            LibgenDatabaseConnectionError,
            LibgenReadConnectionLimitError,
            RuntimeError,
        )
        return isinstance(exc, retryables)

    def _is_retryable_download_error(self, exc: Exception) -> bool:
        return isinstance(
            exc, (RetryableDownloadError, requests.exceptions.RequestException)
        )

    def _validate_score_threshold(self, threshold: int) -> int:
        if not isinstance(threshold, int) or isinstance(threshold, bool):
            raise TypeError("score_threshold must be an integer")
        return threshold

    def _normalize_search_order(
        self, search_order: Optional[Iterable[GetQueryMethod]]
    ) -> List[GetQueryMethod]:
        if search_order is None:
            return list(DEFAULT_SEARCH_ORDER)
        order = list(search_order)
        if not order:
            raise ValueError("search_order must not be empty")
        for method in order:
            if not isinstance(method, GetQueryMethod):
                raise TypeError("search_order must contain GetQueryMethod values")
        return order

    def _validate_timeout(self, timeout: int) -> int:
        if not isinstance(timeout, int) or isinstance(timeout, bool):
            raise TypeError("timeout must be an integer")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        return timeout

    def _validate_max_attempts(self, max_attempts: int) -> int:
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
            raise TypeError("max_attempts must be an integer")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        return max_attempts

    def _validate_backoff_base(self, backoff_base: float) -> float:
        if backoff_base <= 0:
            raise ValueError("backoff_base must be positive")
        return float(backoff_base)

    def _validate_backoff_factor(self, backoff_factor: float) -> float:
        if backoff_factor <= 1:
            raise ValueError("backoff_factor must be greater than 1")
        return float(backoff_factor)

    def _validate_backoff_max(self, backoff_max: float) -> float:
        if backoff_max <= 0:
            raise ValueError("backoff_max must be positive")
        return float(backoff_max)

    def _validate_jitter(self, jitter: float) -> float:
        if jitter < 0:
            raise ValueError("jitter must be non-negative")
        return float(jitter)

    def _normalize_mirror(self, mirror: Optional[str]) -> Optional[str]:
        if mirror is None:
            return None
        if not isinstance(mirror, str) or not mirror.strip():
            raise ValueError("mirror must be a non-empty string")
        parsed = urlparse(mirror)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("mirror must be a valid HTTP or HTTPS URL")
        return mirror.rstrip("/")

    def _normalize_output_dir(self, output_dir: Optional[str | Path]) -> Path:
        if output_dir is None:
            return Path.cwd()
        if isinstance(output_dir, (str, Path)):
            return Path(output_dir)
        raise TypeError("output_dir must be a path or string")
