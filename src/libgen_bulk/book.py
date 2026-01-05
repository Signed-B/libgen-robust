"""Book model for libgen search results."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class Book:
    def __init__(
        self,
        id,
        title,
        author,
        series,
        isbn,
        file_id,
        edition_link,
        publisher,
        year,
        language,
        pages,
        size,
        extension,
        md5,
        mirrors,
        date_added,
        date_last_modified,
    ):
        self.id = id
        self.title = title
        self.author = author
        self.series = series
        self.isbn = isbn
        self.file_id = file_id
        self.edition_link = edition_link
        self.publisher = publisher
        self.year = year
        self.language = language
        self.pages = pages
        self.size = size
        self.extension = extension
        self.md5 = md5
        self.mirrors = mirrors
        self.download_page_link = None
        self.download_link = None
        self.cover_download_link = None
        self.tor_download_link = None
        self.resolved_download_link = None
        self.date_added = date_added
        self.date_last_modified = date_last_modified

    def __repr__(self):
        return (
            f"Book(id='{self.id}', title='{self.title}', "
            f"author='{self.author}', year='{self.year}', "
            f"extension='{self.extension}', "
            f"date_added='{self.date_added}', "
            f"date_last_modified='{self.date_last_modified}')"
        )

    def get_download_links(self, cover: bool = True, timeout: int | None = None) -> None:
        if not self.download_page_link:
            raise ValueError("download_page_link must be set")
        parsed = urlparse(self.download_page_link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("download_page_link must be a valid HTTP or HTTPS URL")
        if "/ads.php" not in parsed.path or "md5=" not in parsed.query:
            raise ValueError("download_page_link must contain /ads.php?md5=")

        if timeout is None:
            response = requests.get(self.download_page_link)
        else:
            response = requests.get(self.download_page_link, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        self.download_link = self._extract_get_link(soup, base_url)
        if cover:
            self.cover_download_link = self._extract_cover_link(soup, base_url)

    def _extract_get_link(self, soup: BeautifulSoup, base_url: str) -> str:
        candidates = []
        for link in soup.find_all("a", href=True):
            text = link.get_text(" ", strip=True)
            if text and text.strip().upper() == "GET":
                candidates.append(link)
        if not candidates:
            candidates = [
                link
                for link in soup.find_all("a", href=True)
                if "get.php?md5=" in link["href"]
            ]
        if len(candidates) != 1:
            raise RuntimeError("Could not identify a unique GET download link")
        href = candidates[0]["href"]
        return urljoin(base_url, href)

    def _extract_cover_link(self, soup: BeautifulSoup, base_url: str) -> str:
        candidates = []
        for link in soup.find_all("a", href=True):
            if link.find("img") and self._is_image_link(link["href"]):
                candidates.append(link["href"])
        if not candidates:
            for image in soup.find_all("img", src=True):
                if self._is_image_link(image["src"]):
                    candidates.append(image["src"])
        candidates = self._filter_cover_candidates(candidates)
        if len(candidates) != 1:
            raise RuntimeError("Could not identify a unique cover image link")
        return urljoin(base_url, candidates[0])

    def _filter_cover_candidates(self, candidates: list[str]) -> list[str]:
        if not candidates:
            return []
        md5 = self.md5
        if not md5 and self.download_page_link:
            parsed = urlparse(self.download_page_link)
            md5_values = parse_qs(parsed.query).get("md5", [])
            if md5_values:
                md5 = md5_values[0]
        if md5:
            filtered = [link for link in candidates if md5.lower() in link.lower()]
            if filtered:
                return filtered
        return candidates

    def _is_image_link(self, link: str) -> bool:
        return bool(re.search(r"\.(jpg|jpeg|png|gif)(\?|$)", link, re.IGNORECASE))
