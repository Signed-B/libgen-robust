from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from libgen_bulk.book import Book


def _load_fixture(name: str) -> str:
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    return (fixtures_dir / name).read_text(encoding="utf-8")


def _make_book(md5: str | None = None) -> Book:
    return Book(
        id="1",
        title="Title",
        author=None,
        series=None,
        isbn=None,
        file_id=None,
        edition_link=None,
        publisher=None,
        year=None,
        language=None,
        pages=None,
        size=None,
        extension=None,
        md5=md5,
        mirrors=[],
        date_added=None,
        date_last_modified=None,
    )


def test_get_download_links_parses_fixture(monkeypatch):
    response = SimpleNamespace(text=_load_fixture("libgen_download.html"))
    response.raise_for_status = Mock()
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    book = _make_book(md5="5eb0c68d269dc6962d92784b6b5b927c")
    book.download_page_link = (
        "https://libgen.example/ads.php?md5=5eb0c68d269dc6962d92784b6b5b927c"
    )

    book.get_download_links()

    assert (
        book.download_link
        == "https://libgen.example/get.php?md5=5eb0c68d269dc6962d92784b6b5b927c&key=GM4CD8GVIFX6XH6A"
    )
    assert (
        book.cover_download_link
        == "https://libgen.example/fictioncovers/2492000/5eb0c68d269dc6962d92784b6b5b927c.jpg"
    )
    requests.get.assert_called_once_with(book.download_page_link)


def test_get_download_links_cover_false(monkeypatch):
    response = SimpleNamespace(text=_load_fixture("libgen_download.html"))
    response.raise_for_status = Mock()
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    book = _make_book(md5="5eb0c68d269dc6962d92784b6b5b927c")
    book.download_page_link = (
        "https://libgen.example/ads.php?md5=5eb0c68d269dc6962d92784b6b5b927c"
    )

    book.get_download_links(cover=False)

    assert (
        book.download_link
        == "https://libgen.example/get.php?md5=5eb0c68d269dc6962d92784b6b5b927c&key=GM4CD8GVIFX6XH6A"
    )
    assert book.cover_download_link is None


def test_get_download_links_rejects_invalid_download_page_link():
    book = _make_book()
    book.download_page_link = "https://libgen.example/file.php?md5=abc"

    with pytest.raises(
        ValueError, match="download_page_link must contain /ads.php\\?md5="
    ):
        book.get_download_links()


def test_get_download_links_raises_without_get_link(monkeypatch):
    response = SimpleNamespace(text="<html><body>missing</body></html>")
    response.raise_for_status = Mock()
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    book = _make_book()
    book.download_page_link = "https://libgen.example/ads.php?md5=abc"

    with pytest.raises(RuntimeError, match="unique GET download link"):
        book.get_download_links()


def test_get_download_links_raises_without_cover_link(monkeypatch):
    response = SimpleNamespace(
        text="<html><body><a href='get.php?md5=abc'><h2>GET</h2></a></body></html>"
    )
    response.raise_for_status = Mock()
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    book = _make_book()
    book.download_page_link = "https://libgen.example/ads.php?md5=abc"

    with pytest.raises(RuntimeError, match="unique cover image link"):
        book.get_download_links()
