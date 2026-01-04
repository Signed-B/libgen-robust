"""Search functionality for libgen."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Iterable, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .book import Book


class SearchField(Enum):
    TITLE = "title"
    AUTHORS = "author"
    SERIES = "series"
    YEAR = "year"
    PUBLISHER = "publisher"
    ISBN = "isbn"

    @property
    def columns(self) -> List[str]:
        return [self.value]


class SearchObject(Enum):
    FILES = "f"
    EDITIONS = "e"
    SERIES = "s"
    AUTHORS = "a"
    PUBLISHERS = "p"
    WORKS = "w"

    @property
    def code(self) -> str:
        return self.value


class SearchTopic(Enum):
    LIBGEN = "libgen"
    COMICS = "comics"
    FICTION = "fiction"
    SCIENTIFIC_ARTICLES = "scientific_articles"
    MAGAZINES = "magazines"
    FICTION_RUS = "fiction_rus"
    STANDARDS = "standards"

    @property
    def code(self) -> str:
        return self.value


class LibgenSearch:
    def __init__(
        self,
        query: str,
        mirror: str,
        search_field: SearchField,
        search_objects: Iterable[SearchObject] | SearchObject,
        search_topics: Iterable[SearchTopic] | SearchTopic,
    ):
        self._logger = logging.getLogger(__name__)
        self.query = self._validate_query(query)
        self.mirror = self._validate_mirror(mirror)
        self.search_field = self._validate_enum(search_field, SearchField, "search_field")
        self.search_objects = self._normalize_enum_list(
            search_objects, SearchObject, "search_objects"
        )
        self.search_topics = self._normalize_enum_list(
            search_topics, SearchTopic, "search_topics"
        )

    def _validate_query(self, query: str) -> str:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        return query

    def _validate_mirror(self, mirror: str) -> str:
        if not isinstance(mirror, str) or not mirror.strip():
            raise ValueError("mirror must be a non-empty string")
        parsed = urlparse(mirror)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("mirror must be a valid HTTP or HTTPS URL")
        return mirror.rstrip("/")

    def _validate_enum(self, value, enum_type, field_name: str):
        if not isinstance(value, enum_type):
            raise TypeError(f"{field_name} must be a {enum_type.__name__}")
        return value

    def _normalize_enum_list(self, value, enum_type, field_name: str):
        if isinstance(value, enum_type):
            enum_list = [value]
        elif isinstance(value, Iterable):
            enum_list = list(value)
        else:
            raise TypeError(f"{field_name} must be a {enum_type.__name__} or iterable")
        if not enum_list:
            raise ValueError(f"{field_name} must not be empty")
        for item in enum_list:
            if not isinstance(item, enum_type):
                raise TypeError(f"{field_name} must contain {enum_type.__name__} values")
        return enum_list

    def get_search_page(self):
        params = {
            "req": self.query,
            "columns[]": self.search_field.columns,
            "objects[]": [obj.code for obj in self.search_objects],
            "topics[]": [topic.code for topic in self.search_topics],
            "res": "100",
            "filesuns": "all",
        }
        try:
            search_page = requests.get(
                f"{self.mirror}/index.php",
                params=params,
            )

            search_page.raise_for_status()
            return search_page
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException(
                f"Request to {self.mirror} timed out"
            )
        except requests.exceptions.ConnectionError:
            raise requests.exceptions.RequestException(
                f"Failed to connect to {self.mirror}"
            )
        except requests.exceptions.HTTPError as e:
            raise requests.exceptions.RequestException(
                f"HTTP error {e.response.status_code}: {e.response.reason}"
            )

    def strip_i_tag_from_soup(self, soup: BeautifulSoup) -> None:
        for i_tag in soup.find_all("i"):
            i_tag.unwrap()

    def get_search_table(self):
        try:
            search_page = self.get_search_page()
            soup = BeautifulSoup(search_page.text, "html.parser")
            self.strip_i_tag_from_soup(soup)
            table = soup.find("table", {"id": "tablelibgen"})
            if table is None:
                self._logger.warning("No results table found on search page")
            return table
        except Exception as e:
            self._logger.error(f"Error during search page retrieval: {str(e)}")
            raise

    def execute(self) -> List[Book]:
        table = self.get_search_table()
        return self._parse_table_to_books(table)

    def _parse_table_to_books(self, table) -> List[Book]:
        if table is None:
            return []
        rows = table.find_all("tr")
        if not rows:
            return []
        header_cells = rows[0].find_all(["th", "td"])
        header_labels = [cell.get_text(" ", strip=True).lower() for cell in header_cells]
        header_map = self._build_header_map(header_labels)
        books = []
        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            books.append(self._build_book_from_cells(cells, header_map))
        return books

    def _build_header_map(self, labels: List[str]) -> dict:
        mapping = {}
        canonical = {
            "id": "id",
            "author(s)": "author",
            "authors": "author",
            "author": "author",
            "title": "title",
            "publisher": "publisher",
            "year": "year",
            "language": "language",
            "pages": "pages",
            "size": "size",
            "extension": "extension",
            "md5": "md5",
            "mirror": "mirrors",
            "mirrors": "mirrors",
            "date added": "date_added",
            "date last modified": "date_last_modified",
        }
        for idx, label in enumerate(labels):
            normalized = canonical.get(label)
            if normalized:
                mapping[normalized] = idx
        return mapping

    def _get_cell_text(self, cells, index):
        if index is None or index >= len(cells):
            return None
        return cells[index].get_text(" ", strip=True) or None

    def _get_mirrors(self, cells, index):
        if index is None or index >= len(cells):
            return []
        return [link.get("href") for link in cells[index].find_all("a") if link.get("href")]

    def _build_book_from_cells(self, cells, header_map) -> Book:
        return Book(
            id=self._get_cell_text(cells, header_map.get("id")),
            title=self._get_cell_text(cells, header_map.get("title")),
            author=self._get_cell_text(cells, header_map.get("author")),
            publisher=self._get_cell_text(cells, header_map.get("publisher")),
            year=self._get_cell_text(cells, header_map.get("year")),
            language=self._get_cell_text(cells, header_map.get("language")),
            pages=self._get_cell_text(cells, header_map.get("pages")),
            size=self._get_cell_text(cells, header_map.get("size")),
            extension=self._get_cell_text(cells, header_map.get("extension")),
            md5=self._get_cell_text(cells, header_map.get("md5")),
            mirrors=self._get_mirrors(cells, header_map.get("mirrors")),
            date_added=self._get_cell_text(cells, header_map.get("date_added")),
            date_last_modified=self._get_cell_text(
                cells, header_map.get("date_last_modified")
            ),
        )
