"""Selection heuristics for choosing the best Libgen result."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from enum import Enum
from typing import Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urljoin

from langdetect import DetectorFactory, LangDetectException, detect

from .book import Book

DetectorFactory.seed = 0


class Heuristic(Enum):
    EXACT_TITLE = "exact_title"
    TITLE_SUBSTRING = "title_substring"
    TITLE_SIMILARITY = "title_similarity"
    EXACT_YEAR = "exact_year"
    YEAR_DISTANCE = "year_distance"
    COMMON_YEAR = "common_year"
    FIRST_AUTHOR_EXACT = "first_author_exact"
    ANY_AUTHOR_EXACT = "any_author_exact"
    FIRST_AUTHOR_SIMILARITY = "first_author_similarity"
    EXTRA_AUTHOR_PENALTY = "extra_author_penalty"
    KEYWORD_PENALTY = "keyword_penalty"

    @property
    def key(self) -> str:
        return self.value


DEFAULT_WEIGHTS = {
    Heuristic.EXACT_TITLE.key: 5.0,
    Heuristic.TITLE_SUBSTRING.key: 3.0,
    Heuristic.TITLE_SIMILARITY.key: 2.0,
    Heuristic.EXACT_YEAR.key: 5.0,
    Heuristic.YEAR_DISTANCE.key: 0,
    Heuristic.COMMON_YEAR.key: 3.0,
    Heuristic.FIRST_AUTHOR_EXACT.key: 5.0,
    Heuristic.ANY_AUTHOR_EXACT.key: 3.0,
    Heuristic.FIRST_AUTHOR_SIMILARITY.key: 8.0,
    Heuristic.EXTRA_AUTHOR_PENALTY.key: -10.0,
    Heuristic.KEYWORD_PENALTY.key: -12.0,
}

DEFAULT_PENALTY_KEYWORDS = [
    "workbook",
    "study guide",
    "teacher",
    "instructor",
    "answer",
    "solutions",
    "test bank",
    "summary",
    "notes",
    "manual",
    "series",
]

DEFAULT_ENABLED_HEURISTICS = {heuristic.key for heuristic in Heuristic}

LANGUAGE_CODE_MAP = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "chinese": "zh-cn",
    "japanese": "ja",
    "korean": "ko",
    "dutch": "nl",
}


class Selector:
    def __init__(
        self,
        *,
        enabled_heuristics: Optional[Iterable[str]] = None,
        weights: Optional[dict[str, float]] = None,
        penalty_keywords: Optional[Iterable[str]] = None,
        use_llm: bool = False,
        count: int = 1,
        language: str = "English",
        mirror: Optional[str] = None,
    ) -> None:
        self.weights = DEFAULT_WEIGHTS.copy()
        if weights:
            self._validate_weight_keys(weights)
            self.weights.update(weights)
        if enabled_heuristics is None:
            self.enabled_heuristics = set(DEFAULT_ENABLED_HEURISTICS)
        else:
            enabled = set(enabled_heuristics)
            self._validate_heuristics(enabled)
            self.enabled_heuristics = enabled
        if penalty_keywords is None:
            penalty_keywords = DEFAULT_PENALTY_KEYWORDS
        self.penalty_keywords = [self._normalize_text(word) for word in penalty_keywords]
        self.use_llm = use_llm
        self._validate_count(count)
        self.count = count
        self.language = self._normalize_language(language)
        self.mirror = self._normalize_mirror(mirror)

    def select(
        self,
        title: str,
        authors: str | List[str],
        year: Optional[int],
        table: List[Book],
    ) -> List[Book]:
        self._validate_table(table)
        normalized_authors = self._normalize_authors(authors)
        if not table:
            return []
        table = self._filter_by_language(table)
        if not table:
            return []
        table = self._filter_by_title_language(table, title)
        if not table:
            return []
        if self.use_llm:
            llm_books = self._select_with_llm(
                title, normalized_authors, year, table, self.count
            )
            if llm_books:
                self._apply_download_links(llm_books)
                return llm_books
        context = self._build_context(title, normalized_authors, year, table)
        ranked = self._rank_books(table, context)
        selected = ranked[: self.count]
        self._apply_download_links(selected)
        return selected

    def _select_with_llm(
        self,
        title: str,
        authors: List[str],
        year: Optional[int],
        table: List[Book],
        count: int,
    ) -> Optional[List[Book]]:
        """Stub for an LLM-assisted selector."""
        return None

    def _build_context(
        self, title: str, authors: List[str], year: Optional[int], table: List[Book]
    ) -> dict:
        normalized_title = self._normalize_text(title)
        author_norms = [self._normalize_text(author) for author in authors]
        first_author = author_norms[0] if author_norms else None
        year_counts = {}
        max_year_count = 0
        for book in table:
            book_year = self._parse_year(book.year)
            if book_year is None:
                continue
            year_counts[book_year] = year_counts.get(book_year, 0) + 1
            max_year_count = max(max_year_count, year_counts[book_year])
        return {
            "title": normalized_title,
            "authors": author_norms,
            "first_author": first_author,
            "year": year,
            "year_counts": year_counts,
            "max_year_count": max_year_count,
        }

    def _score_book(self, book: Book, context: dict) -> float:
        score = 0.0
        book_title = self._normalize_text(book.title or "")
        query_title = context["title"]
        if self._enabled("exact_title") and query_title and book_title:
            if query_title == book_title:
                score += self.weights["exact_title"]
        if self._enabled("title_substring") and query_title and book_title:
            if query_title in book_title or book_title in query_title:
                score += self.weights["title_substring"]
        if self._enabled("title_similarity") and query_title and book_title:
            score += self.weights["title_similarity"] * self._similarity(
                query_title, book_title
            )
        score += self._score_years(book, context)
        score += self._score_authors(book, context)
        score += self._score_keywords(book, context)
        return score

    def _score_years(self, book: Book, context: dict) -> float:
        score = 0.0
        query_year = context["year"]
        book_year = self._parse_year(book.year)
        if query_year is not None and book_year is not None:
            if self._enabled("exact_year") and query_year == book_year:
                score += self.weights["exact_year"]
            if self._enabled("year_distance"):
                score += self.weights["year_distance"] * abs(query_year - book_year)
        if self._enabled("common_year") and book_year is not None:
            max_count = context["max_year_count"]
            if max_count:
                score += (
                    self.weights["common_year"]
                    * (context["year_counts"].get(book_year, 0) / max_count)
                )
        return score

    def _score_authors(self, book: Book, context: dict) -> float:
        score = 0.0
        query_authors = context["authors"]
        first_author = context["first_author"]
        book_authors = [self._normalize_text(author) for author in self._split_authors(book.author)]
        if not book_authors or not query_authors:
            return score
        if self._enabled("first_author_exact") and first_author:
            if first_author in book_authors:
                score += self.weights["first_author_exact"]
        if self._enabled("any_author_exact"):
            if set(query_authors) & set(book_authors):
                score += self.weights["any_author_exact"]
        if self._enabled("first_author_similarity") and first_author:
            best_similarity = max(
                (self._similarity(first_author, author) for author in book_authors),
                default=0.0,
            )
            score += self.weights["first_author_similarity"] * best_similarity
        if self._enabled("extra_author_penalty"):
            extras = [author for author in book_authors if author not in query_authors]
            if extras:
                score += self.weights["extra_author_penalty"] * len(extras)
        return score

    def _score_keywords(self, book: Book, context: dict) -> float:
        if not self._enabled("keyword_penalty"):
            return 0.0
        title_text = self._normalize_text(book.title or "")
        query_title = context["title"]
        series_text = self._normalize_text(book.series or "")
        hits = 0
        for keyword in self.penalty_keywords:
            if keyword in query_title:
                continue
            if keyword in title_text or keyword in series_text:
                hits += 1
        return self.weights["keyword_penalty"] * hits if hits else 0.0

    def _get_download_page_link(self, book: Book) -> Optional[str]:
        for link in book.mirrors or []:
            if "/ads.php?md5=" in link:
                if link.startswith("http"):
                    return link
                if not self.mirror:
                    raise ValueError("mirror must be set to build full download link")
                return urljoin(self.mirror, link)
        return None

    def _split_authors(self, authors_text: Optional[str]) -> List[str]:
        if not authors_text:
            return []
        parts = [part.strip() for part in authors_text.split(";") if part.strip()]
        if len(parts) == 1 and " and " in parts[0].lower():
            return [part.strip() for part in parts[0].split(" and ") if part.strip()]
        return parts

    def _normalize_text(self, text: str) -> str:
        normalized = text.lower()
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _parse_year(self, year_text: Optional[str]) -> Optional[int]:
        if year_text is None:
            return None
        match = re.search(r"(\d{4})", str(year_text))
        if not match:
            return None
        return int(match.group(1))

    def _similarity(self, left: str, right: str) -> float:
        return SequenceMatcher(None, left, right).ratio()

    def _enabled(self, heuristic: str) -> bool:
        return heuristic in self.enabled_heuristics and heuristic in self.weights

    def _rank_books(self, table: List[Book], context: dict) -> List[Book]:
        scored = []
        for index, book in enumerate(table):
            score = self._score_book(book, context)
            scored.append((score, index, book))
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [book for _, _, book in scored]

    def _filter_by_language(self, table: List[Book]) -> List[Book]:
        if not self.language:
            return table
        filtered = []
        for book in table:
            book_language = self._normalize_text(book.language or "")
            if book_language == self.language:
                filtered.append(book)
        return filtered

    def _filter_by_title_language(self, table: List[Book], query_title: str) -> List[Book]:
        if not self.language:
            return table
        target_lang = self._language_code()
        normalized_query = self._normalize_text(query_title or "")
        filtered = []
        for book in table:
            title_text = (book.title or "").strip()
            if not title_text:
                filtered.append(book)
                continue
            if self._title_matches_language(title_text, normalized_query, target_lang):
                filtered.append(book)
        return filtered

    def _title_matches_language(
        self,
        title_text: str,
        normalized_query: str,
        target_lang: str,
    ) -> bool:
        normalized_title = self._normalize_text(title_text)
        if not normalized_title or not target_lang:
            return True
        if self._is_short_title(normalized_title) and self._is_ascii_text(normalized_title):
            return True
        title_lang = self._detect_language(normalized_title)
        if title_lang == target_lang:
            return True
        if not normalized_query:
            return False
        query_tokens = set(normalized_query.split())
        remaining_tokens = [
            token for token in normalized_title.split() if token not in query_tokens
        ]
        if not remaining_tokens:
            return True
        remaining_lang = self._detect_language(" ".join(remaining_tokens))
        if remaining_lang is None:
            return False
        return remaining_lang == target_lang

    def _detect_language(self, text: str) -> Optional[str]:
        try:
            return detect(text)
        except LangDetectException:
            return None

    def _is_ascii_text(self, text: str) -> bool:
        return all(ord(char) < 128 for char in text)

    def _is_short_title(self, text: str) -> bool:
        stripped = text.replace(" ", "")
        return len(stripped) < 10 or len(text.split()) < 2

    def _language_code(self) -> str:
        if not self.language:
            return ""
        if self.language in LANGUAGE_CODE_MAP.values():
            return self.language
        return LANGUAGE_CODE_MAP.get(self.language, self.language)

    def _apply_download_links(self, books: List[Book]) -> None:
        for book in books:
            book.download_page_link = self._get_download_page_link(book)

    def _normalize_authors(self, authors: str | List[str]) -> List[str]:
        if isinstance(authors, str):
            if not authors.strip():
                return []
            return [authors.strip()]
        if isinstance(authors, list):
            if not all(isinstance(author, str) for author in authors):
                raise TypeError("authors must be a string or list of strings")
            return [author.strip() for author in authors if author.strip()]
        raise TypeError("authors must be a string or list of strings")

    def _validate_table(self, table: List[Book]) -> None:
        if not isinstance(table, list):
            raise TypeError("table must be a list of Book")
        if not all(isinstance(book, Book) for book in table):
            raise TypeError("table must be a list of Book")

    def _validate_count(self, count: int) -> None:
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError("count must be an integer")
        if count < 1:
            raise ValueError("count must be at least 1")

    def _normalize_language(self, language: str) -> str:
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must be a non-empty string")
        return self._normalize_text(language)

    def _normalize_mirror(self, mirror: Optional[str]) -> Optional[str]:
        if mirror is None:
            return None
        if not isinstance(mirror, str) or not mirror.strip():
            raise ValueError("mirror must be a non-empty string")
        parsed = urlparse(mirror)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("mirror must be a valid HTTP or HTTPS URL")
        return mirror.rstrip("/")

    def _validate_heuristics(self, heuristics: Iterable[str]) -> None:
        unknown = set(heuristics) - DEFAULT_ENABLED_HEURISTICS
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown heuristics: {unknown_list}")

    def _validate_weight_keys(self, weights: dict[str, float]) -> None:
        unknown = set(weights) - DEFAULT_ENABLED_HEURISTICS
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown heuristic weights: {unknown_list}")
