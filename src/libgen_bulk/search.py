"""Search functionality for libgen."""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Iterable, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .book import Book


class SearchField(Enum):
    TITLE = "t"
    AUTHORS = "a"
    SERIES = "s"
    YEAR = "y"
    PUBLISHER = "p"
    ISBN = "i"

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
    LIBGEN = "l"
    COMICS = "c"
    FICTION = "f"
    SCIENTIFIC_ARTICLES = "a"
    MAGAZINES = "m"
    FICTION_RUS = "r"
    STANDARDS = "s"

    @property
    def code(self) -> str:
        return self.value


class LibgenSearch:
    def __init__(
        self,
        query: str,
        mirror: str,
        search_field: SearchField | Iterable[SearchField],
        search_objects: Iterable[SearchObject] | SearchObject,
        search_topics: Iterable[SearchTopic] | SearchTopic,
        timeout: int | None = None,
        verbose_print_links: bool = False,
    ):
        self._logger = logging.getLogger(__name__)
        self.query = self._validate_query(query)
        self.mirror = self._validate_mirror(mirror)
        self.search_fields = self._normalize_enum_list(
            search_field, SearchField, "search_field"
        )
        self.search_field = self.search_fields[0]
        self.search_objects = self._normalize_enum_list(
            search_objects, SearchObject, "search_objects"
        )
        self.search_topics = self._normalize_enum_list(
            search_topics, SearchTopic, "search_topics"
        )
        self.timeout = timeout
        self.verbose_print_links = self._validate_verbose_print_links(verbose_print_links)

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

    def _validate_verbose_print_links(self, value: bool) -> bool:
        if not isinstance(value, bool):
            raise TypeError("verbose_print_links must be a boolean")
        return value

    def build_search_params(self, results_per_page: int = 100):
        params = [
            ("req", self.query),
        ]
        for field in self.search_fields:
            params.append(("columns[]", field.value))
        for obj in self.search_objects:
            params.append(("objects[]", obj.code))
        for topic in self.search_topics:
            params.append(("topics[]", topic.code))
        params.extend(
            [
                ("res", str(results_per_page)),
                ("filesuns", "all"),
            ]
        )
        return params

    def build_search_url(self, results_per_page: int = 100) -> str:
        params = self.build_search_params(results_per_page=results_per_page)
        request = requests.Request(
            "GET",
            f"{self.mirror}/index.php",
            params=params,
        )
        return request.prepare().url

    def get_search_page(self):
        params = self.build_search_params(results_per_page=100)
        try:
            request_kwargs = {
                "params": params,
            }
            if self.timeout is not None:
                request_kwargs["timeout"] = self.timeout
            search_page = requests.get(
                f"{self.mirror}/index.php",
                **request_kwargs,
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
            db_error = soup.find("div", {"class": "alert alert-danger"})
            if db_error:
                error_text = db_error.get_text(" ", strip=True).lower()
                if "libgen_read" in error_text and "max_user_connections" in error_text:
                    raise LibgenReadConnectionLimitError(
                        "User libgen_read has exceeded max_user_connections"
                    )
                if "could not connect to the database" in error_text:
                    raise LibgenDatabaseConnectionError(
                        "Could not connect to the database"
                    )
            table = soup.find("table", {"id": "tablelibgen"})
            if table is None:
                if self.verbose_print_links:
                    print(self.build_search_url(results_per_page=100))
                raise RuntimeError("Couldn't find table: unknown reason")
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
            book = self._build_book_from_cells(cells, header_map)
            if book and self._should_include_book(book):
                books.append(book)
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
            "ext.": "extension",
            "ext": "extension",
            "md5": "md5",
            "mirror": "mirrors",
            "mirrors": "mirrors",
            "date added": "date_added",
            "date last modified": "date_last_modified",
            "time add.": "date_added",
        }
        for idx, label in enumerate(labels):
            cleaned = label.replace("\u2197", "").replace("\u2195", "")
            normalized_label = re.sub(r"\s+", " ", cleaned).strip().lower()
            normalized = canonical.get(normalized_label)
            if normalized:
                mapping[normalized] = idx
                continue
            for key, normalized_key in canonical.items():
                if key in normalized_label:
                    mapping.setdefault(normalized_key, idx)
        return mapping

    def _get_cell_text(self, cells, index):
        if index is None or index >= len(cells):
            return None
        return cells[index].get_text(" ", strip=True) or None

    def _get_mirrors(self, cells, index):
        if index is None or index >= len(cells):
            return []
        return [link.get("href") for link in cells[index].find_all("a") if link.get("href")]

    def _parse_title_from_cell(self, cell) -> str | None:
        for link in cell.find_all("a"):
            href = link.get("href") or ""
            link_text = link.get_text(" ", strip=True)
            if link.find_parent("b"):
                continue
            if href.startswith("edition.php?id=") and link_text:
                return link_text
        for link in cell.find_all("a"):
            link_text = link.get_text(" ", strip=True)
            if link.find_parent("b"):
                continue
            if link_text and link_text.lower() != "b":
                return link_text
        cell_copy = BeautifulSoup(str(cell), "html.parser")
        for bold in cell_copy.find_all("b"):
            bold.decompose()
        return cell_copy.get_text(" ", strip=True) or None

    def _parse_add_edit_metadata(self, cell):
        tooltip = None
        for link in cell.find_all("a"):
            title_text = link.get("title")
            if title_text and "Add/Edit" in title_text:
                tooltip = title_text
                break
        if not tooltip:
            return None, None, None
        match = re.search(
            r"Add/Edit\s*:\s*([^/;]+)\s*/\s*([^;]+);\s*ID:\s*(\d+)",
            tooltip,
        )
        if not match:
            return None, None, None
        date_added, date_last_modified, identifier = match.groups()
        return identifier, date_added, date_last_modified

    def _parse_edition_link(self, cell) -> str | None:
        for link in cell.find_all("a"):
            href = link.get("href")
            if href and href.startswith("edition.php?id="):
                return href
        return None

    def _parse_series(self, cell, title_text: str | None) -> str | None:
        bold = cell.find("b")
        if not bold:
            return None
        bold_text = bold.get_text(" ", strip=True)
        if not bold_text:
            return None
        if "series" in bold_text.lower():
            return bold_text
        return None

    def _parse_isbn(self, cell) -> list[str] | None:
        for font in cell.find_all("font"):
            isbn_text = font.get_text(" ", strip=True)
            if isbn_text:
                return [part.strip() for part in isbn_text.split(";") if part.strip()]
        return None

    def _parse_file_id(self, cell) -> str | None:
        for link in cell.find_all("a"):
            href = link.get("href")
            if href and href.startswith("/file.php?id="):
                return href.split("=", 1)[1]
        return None

    def _parse_md5_from_mirrors(self, mirrors: List[str]) -> str | None:
        for link in mirrors:
            match = re.search(r"md5=([0-9a-fA-F]+)", link)
            if match:
                return match.group(1).lower()
        return None

    def _normalize_size_kb(self, size_text: str | None):
        if not size_text:
            return None
        match = re.search(r"([\d.]+)\s*([kKmM][bB])", size_text)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit == "kb":
            return int(value)
        if unit == "mb":
            return int(value * 1000)
        return None

    def _is_valid_md5(self, md5: str | None) -> bool:
        if not md5:
            return False
        return bool(re.fullmatch(r"[0-9a-f]{32}", md5))

    def _should_include_book(self, book: Book) -> bool:
        if not book.mirrors:
            return False
        if not book.mirrors[0].startswith("/ads.php"):
            return False
        if not self._is_valid_md5(book.md5):
            return False
        return True

    def _build_book_from_cells(self, cells, header_map) -> Book:
        id_from_meta, date_added_meta, date_modified_meta = self._parse_add_edit_metadata(
            cells[0]
        )
        mirrors = self._get_mirrors(cells, header_map.get("mirrors"))
        md5 = self._parse_md5_from_mirrors(mirrors)
        size_text = self._get_cell_text(cells, header_map.get("size"))
        normalized_size = self._normalize_size_kb(size_text)
        title_index = header_map.get("title")
        if title_index is None:
            title_index = 0
        title_text = self._parse_title_from_cell(cells[title_index])
        series = self._parse_series(cells[0], title_text)
        isbn = self._parse_isbn(cells[0])
        edition_link = self._parse_edition_link(cells[0])
        file_id = None
        size_index = header_map.get("size")
        if size_index is not None and size_index < len(cells):
            file_id = self._parse_file_id(cells[size_index])
        return Book(
            id=id_from_meta or self._get_cell_text(cells, header_map.get("id")),
            title=title_text,
            author=self._get_cell_text(cells, header_map.get("author")),
            series=series,
            isbn=isbn,
            file_id=file_id,
            edition_link=edition_link,
            publisher=self._get_cell_text(cells, header_map.get("publisher")),
            year=self._get_cell_text(cells, header_map.get("year")),
            language=self._get_cell_text(cells, header_map.get("language")),
            pages=self._get_cell_text(cells, header_map.get("pages")),
            size=normalized_size,
            extension=self._get_cell_text(cells, header_map.get("extension")),
            md5=md5 or self._get_cell_text(cells, header_map.get("md5")),
            mirrors=mirrors,
            date_added=date_added_meta
            or self._get_cell_text(cells, header_map.get("date_added")),
            date_last_modified=date_modified_meta
            or self._get_cell_text(cells, header_map.get("date_last_modified")),
        )


class LibgenDatabaseConnectionError(RuntimeError):
    pass


class LibgenReadConnectionLimitError(RuntimeError):
    pass
