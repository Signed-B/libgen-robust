import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from libgen_bulk.book import Book
from libgen_bulk.search import LibgenSearch, SearchField, SearchObject, SearchTopic


def _make_search():
    return LibgenSearch(
        query="test",
        mirror="https://example.com",
        search_field=SearchField.TITLE,
        search_objects=[SearchObject.FILES],
        search_topics=[SearchTopic.LIBGEN],
    )


def test_book_repr():
    book = Book(
        id="1",
        title="Title",
        author="Author",
        publisher="Publisher",
        year="2020",
        language="EN",
        pages="100",
        size="1 MB",
        extension="pdf",
        md5="abc",
        mirrors=["http://m1"],
        date_added="2020-01-01",
        date_last_modified="2020-02-02",
    )
    assert "Book(id='1'" in repr(book)


def test_libgen_search_validates_query():
    with pytest.raises(ValueError, match="query must be a non-empty string"):
        LibgenSearch(
            query="",
            mirror="https://example.com",
            search_field=SearchField.TITLE,
            search_objects=[SearchObject.FILES],
            search_topics=[SearchTopic.LIBGEN],
        )


def test_libgen_search_validates_mirror():
    with pytest.raises(ValueError, match="mirror must be a valid HTTP or HTTPS URL"):
        LibgenSearch(
            query="test",
            mirror="ftp://example.com",
            search_field=SearchField.TITLE,
            search_objects=[SearchObject.FILES],
            search_topics=[SearchTopic.LIBGEN],
        )


def test_libgen_search_validates_enums():
    with pytest.raises(TypeError, match="search_field must be a SearchField"):
        LibgenSearch(
            query="test",
            mirror="https://example.com",
            search_field="title",
            search_objects=[SearchObject.FILES],
            search_topics=[SearchTopic.LIBGEN],
        )


def test_get_search_page_success(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text="ok")
    response.raise_for_status = Mock()
    mock_get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", mock_get)

    result = search.get_search_page()

    assert result is response
    mock_get.assert_called_once()
    url, = mock_get.call_args[0]
    params = mock_get.call_args.kwargs["params"]
    assert url == "https://example.com/index.php"
    assert params["req"] == "test"
    assert params["columns[]"] == ["title"]
    assert params["objects[]"] == ["f"]
    assert params["topics[]"] == ["libgen"]


def test_get_search_page_timeout(monkeypatch):
    search = _make_search()
    mock_get = Mock(side_effect=requests.exceptions.Timeout)
    monkeypatch.setattr(requests, "get", mock_get)

    with pytest.raises(requests.exceptions.RequestException, match="timed out"):
        search.get_search_page()


def test_get_search_page_connection_error(monkeypatch):
    search = _make_search()
    mock_get = Mock(side_effect=requests.exceptions.ConnectionError)
    monkeypatch.setattr(requests, "get", mock_get)

    with pytest.raises(requests.exceptions.RequestException, match="Failed to connect"):
        search.get_search_page()


def test_get_search_page_http_error(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(status_code=500, reason="Server Error")
    http_error = requests.exceptions.HTTPError(response=response)
    mock_response = SimpleNamespace(raise_for_status=Mock(side_effect=http_error))
    mock_get = Mock(return_value=mock_response)
    monkeypatch.setattr(requests, "get", mock_get)

    with pytest.raises(
        requests.exceptions.RequestException, match="HTTP error 500: Server Error"
    ):
        search.get_search_page()


def test_get_search_table_no_table_logs_warning(caplog, monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text="<html></html>")
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    with caplog.at_level(logging.WARNING):
        table = search.get_search_table()

    assert table is None
    assert "No results table found on search page" in caplog.text


def test_execute_parses_books(monkeypatch):
    search = _make_search()
    html = """
    <table id="tablelibgen">
        <tr>
            <th>ID</th>
            <th>Author(s)</th>
            <th>Title</th>
            <th>Publisher</th>
            <th>Year</th>
            <th>Language</th>
            <th>Pages</th>
            <th>Size</th>
            <th>Extension</th>
            <th>MD5</th>
            <th>Mirrors</th>
            <th>Date Added</th>
            <th>Date Last Modified</th>
        </tr>
        <tr>
            <td>123</td>
            <td>Test Author</td>
            <td><i>Test Title</i></td>
            <td>Test Publisher</td>
            <td>2020</td>
            <td>EN</td>
            <td>100</td>
            <td>1 MB</td>
            <td>pdf</td>
            <td>abc123</td>
            <td>
                <a href="http://m1">m1</a>
                <a href="http://m2">m2</a>
            </td>
            <td>2020-01-01</td>
            <td>2020-02-02</td>
        </tr>
    </table>
    """
    response = SimpleNamespace(text=html)
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    results = search.execute()

    assert len(results) == 1
    book = results[0]
    assert book.id == "123"
    assert book.title == "Test Title"
    assert book.author == "Test Author"
    assert book.publisher == "Test Publisher"
    assert book.year == "2020"
    assert book.language == "EN"
    assert book.pages == "100"
    assert book.size == "1 MB"
    assert book.extension == "pdf"
    assert book.md5 == "abc123"
    assert book.mirrors == ["http://m1", "http://m2"]
    assert book.date_added == "2020-01-01"
    assert book.date_last_modified == "2020-02-02"
