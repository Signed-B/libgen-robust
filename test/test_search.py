from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from libgen_bulk.book import Book
from libgen_bulk.search import (
    LibgenDatabaseConnectionError,
    LibgenSearch,
    LibgenReadConnectionLimitError,
    SearchField,
    SearchObject,
    SearchTopic,
)


def _make_search():
    return LibgenSearch(
        query="test",
        mirror="https://example.com",
        search_field=SearchField.TITLE,
        search_objects=[SearchObject.FILES],
        search_topics=[SearchTopic.LIBGEN],
    )


def _load_fixture(name: str) -> str:
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    return (fixtures_dir / name).read_text(encoding="utf-8")


def _index_by_id(books):
    return {book.id: book for book in books if book.id}


def test_book_repr():
    book = Book(
        id="1",
        title="Title",
        author="Author",
        series="Series",
        isbn=["123"],
        file_id="10",
        edition_link="edition.php?id=10",
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
    with pytest.raises(TypeError, match="search_field must contain SearchField values"):
        LibgenSearch(
            query="test",
            mirror="https://example.com",
            search_field="title",
            search_objects=[SearchObject.FILES],
            search_topics=[SearchTopic.LIBGEN],
        )


def test_build_search_url_matches_fixture():
    search = LibgenSearch(
        query="Think and Grow Rich",
        mirror="https://libgen.testmirror",
        search_field=[
            SearchField.TITLE,
            SearchField.AUTHORS,
            SearchField.SERIES,
            SearchField.YEAR,
            SearchField.PUBLISHER,
            SearchField.ISBN,
        ],
        search_objects=[
            SearchObject.FILES,
            SearchObject.EDITIONS,
            SearchObject.SERIES,
            SearchObject.AUTHORS,
            SearchObject.PUBLISHERS,
            SearchObject.WORKS,
        ],
        search_topics=[
            SearchTopic.LIBGEN,
            SearchTopic.COMICS,
            SearchTopic.FICTION,
            SearchTopic.SCIENTIFIC_ARTICLES,
            SearchTopic.MAGAZINES,
            SearchTopic.FICTION_RUS,
            SearchTopic.STANDARDS,
        ],
    )

    url = search.build_search_url(results_per_page=25)

    assert (
        url
        == "https://libgen.testmirror/index.php?req=Think+and+Grow+Rich&columns%5B%5D=t&columns%5B%5D=a&columns%5B%5D=s&columns%5B%5D=y&columns%5B%5D=p&columns%5B%5D=i&objects%5B%5D=f&objects%5B%5D=e&objects%5B%5D=s&objects%5B%5D=a&objects%5B%5D=p&objects%5B%5D=w&topics%5B%5D=l&topics%5B%5D=c&topics%5B%5D=f&topics%5B%5D=a&topics%5B%5D=m&topics%5B%5D=r&topics%5B%5D=s&res=25&filesuns=all"
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
    assert params == [
        ("req", "test"),
        ("columns[]", "t"),
        ("objects[]", "f"),
        ("topics[]", "l"),
        ("res", "100"),
        ("filesuns", "all"),
    ]


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


def test_get_search_table_no_table_raises(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text="<html></html>")
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    with pytest.raises(RuntimeError, match="Couldn't find table: unknown reason"):
        search.get_search_table()


def test_get_search_table_prints_link_when_verbose(monkeypatch, capsys):
    search = LibgenSearch(
        query="test",
        mirror="https://example.com",
        search_field=SearchField.TITLE,
        search_objects=[SearchObject.FILES],
        search_topics=[SearchTopic.LIBGEN],
        verbose_print_links=True,
    )
    response = SimpleNamespace(text="<html></html>")
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    with pytest.raises(RuntimeError, match="Couldn't find table: unknown reason"):
        search.get_search_table()

    output = capsys.readouterr().out.strip()
    assert output == search.build_search_url(results_per_page=100)

def test_get_search_table_db_error(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text=_load_fixture("libgen_search_error_cant_connect_to_db.html"))
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    with pytest.raises(
        LibgenDatabaseConnectionError, match="Could not connect to the database"
    ):
        search.get_search_table()


def test_get_search_table_read_connection_limit(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text=_load_fixture("libgen_error_user_libgen_read.html"))
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    with pytest.raises(
        LibgenReadConnectionLimitError,
        match="User libgen_read has exceeded max_user_connections",
    ):
        search.get_search_table()


def test_execute_parses_books(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text=_load_fixture("libgen_search_success.html"))
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    results = search.execute()
    by_id = _index_by_id(results)

    assert len(results) >= 20
    book = by_id["93098871"]
    assert book.title == "Think and grow rich on Brilliance Audio"
    assert book.author == "Stella, Fred; Gitomer, Jeffrey H.; Hill, Napoleon"
    assert book.series is None
    assert book.isbn == ["9781455810031", "1455810037"]
    assert book.file_id == "93098871"
    assert book.edition_link == "edition.php?id=137866771"
    assert book.publisher == "Think and Grow Rich on Brilliance Audio"
    assert book.year == "2011"
    assert book.language == "English"
    assert book.pages == "0 / 6"
    assert book.size == 320
    assert book.extension == "epub"
    assert book.md5 == "96f071d706747da515aa042d0cf7cd89"
    assert len(book.mirrors) == 4
    assert book.mirrors[0].startswith("/ads.php?md5=")
    assert book.date_added == "2017-08-15"
    assert book.date_last_modified == "2024-12-16"

    second_book = by_id["93098872"]
    assert second_book.size == 437
    assert second_book.extension == "mobi"
    assert second_book.md5 == "11d7ff2c089d82e41f64101e8f11db3c"

    third_book = by_id["93238019"]
    assert third_book.size == 22000
    assert third_book.extension == "pdf"
    assert third_book.md5 == "987f731269600de29b2b17031d8b05f2"

    series_book = by_id["98044506"]
    assert series_book.series == "Think and Grow Rich Series"
    assert series_book.isbn == ["9780698160750", "0698160754"]


def test_execute_skips_invalid_md5(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text=_load_fixture("libgen_search_success_invalid_md5.html"))
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    results = search.execute()
    by_id = _index_by_id(results)

    assert "93098871" not in by_id
    assert "93098872" in by_id


def test_execute_skips_invalid_mirror(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text=_load_fixture("libgen_search_success_invalid_mirror.html"))
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    results = search.execute()
    by_id = _index_by_id(results)

    assert "93098871" not in by_id
    assert "93098872" in by_id


def test_execute_skips_no_mirrors(monkeypatch):
    search = _make_search()
    response = SimpleNamespace(text=_load_fixture("libgen_search_success_no_mirrors.html"))
    monkeypatch.setattr(search, "get_search_page", Mock(return_value=response))

    results = search.execute()
    by_id = _index_by_id(results)

    assert "93098871" not in by_id
    assert "93098872" in by_id
