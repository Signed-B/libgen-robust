from pathlib import Path
from types import SimpleNamespace

import pytest

import libgen_bulk.get as get_module
from libgen_bulk.book import Book
from libgen_bulk.get import GetQueryMethod, Getter, RetryableDownloadError
from libgen_bulk.search import SearchField


def _make_book(**overrides):
    md5 = overrides.get("md5", "a" * 32)
    data = {
        "id": "1",
        "title": "Example Title",
        "author": "Example Author",
        "series": None,
        "isbn": None,
        "file_id": "1",
        "edition_link": None,
        "publisher": None,
        "year": "2020",
        "language": "English",
        "pages": None,
        "size": 100,
        "extension": "pdf",
        "md5": md5,
        "mirrors": [f"/ads.php?md5={md5}"],
        "date_added": "2020-01-01",
        "date_last_modified": "2020-01-02",
    }
    data.update(overrides)
    return Book(**data)


def test_build_query_title_keyword_removes_stopwords():
    getter = Getter(score_threshold=1, search_order=[GetQueryMethod.TITLE])
    query, fields = getter._build_query(
        "The Rise-and-Fall of Z",
        "Author",
        GetQueryMethod.TITLEKEYWORD,
    )

    assert query == "rise fall z"
    assert fields == [SearchField.TITLE]


def test_get_uses_search_order_until_threshold(monkeypatch, tmp_path):
    getter = Getter(
        score_threshold=20,
        search_order=[GetQueryMethod.TITLE, GetQueryMethod.AUTHOR],
        mirror="https://libgen.example",
        output_dir=tmp_path,
    )
    low_book = _make_book(title="Wrong Title", author="Other Author", year="1999")
    good_book = _make_book(
        title="Think and Grow Rich",
        author="Napoleon Hill",
        year="2011",
    )
    calls = []

    def fake_execute(query, fields, mirror):
        calls.append((query, tuple(fields), mirror))
        return [low_book] if len(calls) == 1 else [good_book]

    def fake_get_links(self, cover=True, timeout=None):
        self.download_link = "https://libgen.example/get.php?md5=abc"

    monkeypatch.setattr(getter, "_execute_search", fake_execute)
    monkeypatch.setattr(Book, "get_download_links", fake_get_links)
    monkeypatch.setattr(getter, "download", lambda book, **kwargs: tmp_path / "ok.pdf")

    result = getter.get(
        title="Think and Grow Rich",
        author="Napoleon Hill",
        year=2011,
    )

    assert result == tmp_path / "ok.pdf"
    assert calls[0][1] == (SearchField.TITLE,)
    assert calls[1][1] == (SearchField.AUTHORS,)


def test_download_requires_download_link(tmp_path):
    getter = Getter(
        score_threshold=1,
        search_order=[GetQueryMethod.TITLE],
        output_dir=tmp_path,
    )
    book = _make_book()

    with pytest.raises(ValueError, match="download_link must be set"):
        getter.download(book, mirror="https://libgen.example")


def test_download_writes_file_and_uses_output_dir(monkeypatch, tmp_path):
    getter = Getter(
        score_threshold=1,
        search_order=[GetQueryMethod.TITLE],
        output_dir=tmp_path,
    )
    book = _make_book()
    book.download_link = "/get.php?md5=abc"

    response = SimpleNamespace(
        status_code=200,
        headers={},
        url="https://libgen.example/get.php?md5=abc",
    )

    def iter_content(chunk_size=8192):
        yield b"payload"

    response.iter_content = iter_content
    monkeypatch.setattr(get_module.requests, "get", lambda *args, **kwargs: response)

    target_dir = tmp_path / "out"
    result = getter.download(book, mirror="https://libgen.example", output_dir=target_dir)

    assert result.exists()
    assert result.read_bytes() == b"payload"
    assert result.parent == target_dir


def test_download_retries_on_retryable_error(monkeypatch, tmp_path):
    getter = Getter(
        score_threshold=1,
        search_order=[GetQueryMethod.TITLE],
        output_dir=tmp_path,
        max_attempts=3,
        backoff_base=0.01,
        backoff_factor=2.0,
        backoff_max=0.05,
        jitter=0.0,
    )
    book = _make_book()
    book.download_link = "https://libgen.example/get.php?md5=abc"

    attempts = {"count": 0}

    def fake_download(url, book, output_dir):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RetryableDownloadError("temporary")
        return output_dir / "ok.pdf"

    sleeps = []
    monkeypatch.setattr(getter, "_download_file", fake_download)
    monkeypatch.setattr(get_module.time, "sleep", lambda value: sleeps.append(value))

    result = getter.download(book)

    assert result == tmp_path / "ok.pdf"
    assert attempts["count"] == 3
    assert len(sleeps) == 2


def test_download_refuses_overwrite(monkeypatch, tmp_path):
    getter = Getter(
        score_threshold=1,
        search_order=[GetQueryMethod.TITLE],
        output_dir=tmp_path,
    )
    book = _make_book()
    book.download_link = "https://libgen.example/get.php?md5=abc"

    response = SimpleNamespace(
        status_code=200,
        headers={},
        url="https://libgen.example/get.php?md5=abc",
    )
    response.iter_content = lambda chunk_size=8192: [b"payload"]
    monkeypatch.setattr(get_module.requests, "get", lambda *args, **kwargs: response)

    existing = tmp_path / "Example_Title_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.pdf"
    existing.write_bytes(b"existing")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        getter.download(book)
