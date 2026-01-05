from libgen_bulk.book import Book
import pytest

from libgen_bulk.select import Heuristic, Selector


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


def test_select_prefers_exact_title_year_author():
    selector = Selector(mirror="https://libgen.test")
    book_exact = _make_book(
        id="1",
        title="Think and Grow Rich",
        author="Napoleon Hill",
        year="2011",
    )
    book_wrong_year = _make_book(
        id="2",
        title="Think and Grow Rich",
        author="Napoleon Hill",
        year="2001",
    )
    book_workbook = _make_book(
        id="3",
        title="Think and Grow Rich Workbook",
        author="Napoleon Hill",
        year="2011",
    )

    selected = selector.select(
        title="Think and Grow Rich",
        authors=["Napoleon Hill"],
        year=2011,
        table=[book_wrong_year, book_workbook, book_exact],
    )

    assert selected == [book_exact]
    assert (
        book_exact.download_page_link
        == f"https://libgen.test/ads.php?md5={book_exact.md5}"
    )


def test_select_prefers_common_year_when_no_query_year():
    selector = Selector(mirror="https://libgen.test")
    book_2019 = _make_book(id="1", title="Some Book", year="2019")
    book_2019_second = _make_book(id="2", title="Some Book", year="2019")
    book_2018 = _make_book(id="3", title="Some Book", year="2018")

    selected = selector.select(
        title="Some Book",
        authors=["Example Author"],
        year=None,
        table=[book_2018, book_2019, book_2019_second],
    )

    assert selected[0].year == "2019"


def test_select_penalizes_extra_authors():
    selector = Selector(mirror="https://libgen.test")
    book_exact = _make_book(
        id="1",
        title="Focused Book",
        author="Alice",
    )
    book_extra = _make_book(
        id="2",
        title="Focused Book",
        author="Alice; Bob",
    )

    selected = selector.select(
        title="Focused Book",
        authors=["Alice"],
        year=2020,
        table=[book_extra, book_exact],
    )

    assert selected == [book_exact]


def test_select_handles_empty_table():
    selector = Selector(mirror="https://libgen.test")

    selected = selector.select(
        title="Missing",
        authors=["Nobody"],
        year=2020,
        table=[],
    )

    assert selected == []


def test_selector_rejects_unknown_enabled_heuristics():
    with pytest.raises(ValueError, match="Unknown heuristics:"):
        Selector(enabled_heuristics=["made_up"])


def test_selector_rejects_unknown_weight_keys():
    with pytest.raises(ValueError, match="Unknown heuristic weights:"):
        Selector(weights={"made_up": 1.0})


def test_selector_accepts_enum_keys():
    selector = Selector(enabled_heuristics=[Heuristic.EXACT_TITLE.key])
    assert selector.enabled_heuristics == {Heuristic.EXACT_TITLE.key}


def test_select_rejects_non_list_table():
    selector = Selector(mirror="https://libgen.test")
    with pytest.raises(TypeError, match="table must be a list of Book"):
        selector.select(
            title="Title",
            authors=["Author"],
            year=2020,
            table="not a list",
        )


def test_select_rejects_invalid_table_contents():
    selector = Selector(mirror="https://libgen.test")
    with pytest.raises(TypeError, match="table must be a list of Book"):
        selector.select(
            title="Title",
            authors=["Author"],
            year=2020,
            table=[object()],
        )


def test_select_accepts_authors_string():
    selector = Selector(mirror="https://libgen.test")
    book = _make_book(title="Single Author Book", author="Alice")

    selected = selector.select(
        title="Single Author Book",
        authors="Alice",
        year=2020,
        table=[book],
    )

    assert selected == [book]


def test_select_returns_count_and_sets_links():
    selector = Selector(count=2, mirror="https://libgen.test")
    book_first = _make_book(id="1", title="Alpha")
    book_second = _make_book(id="2", title="Beta")

    selected = selector.select(
        title="Alpha",
        authors="Example Author",
        year=2020,
        table=[book_second, book_first],
    )

    assert selected == [book_first, book_second]
    assert (
        book_first.download_page_link
        == f"https://libgen.test/ads.php?md5={book_first.md5}"
    )
    assert (
        book_second.download_page_link
        == f"https://libgen.test/ads.php?md5={book_second.md5}"
    )


def test_select_rejects_invalid_count():
    with pytest.raises(ValueError, match="count must be at least 1"):
        Selector(count=0)


def test_select_filters_language():
    selector = Selector(language="English", mirror="https://libgen.test")
    book_english = _make_book(id="1", title="Alpha", language="English")
    book_spanish = _make_book(id="2", title="Alpha", language="Spanish")

    selected = selector.select(
        title="Alpha",
        authors="Example Author",
        year=2020,
        table=[book_spanish, book_english],
    )

    assert selected == [book_english]


def test_selector_rejects_invalid_language():
    with pytest.raises(ValueError, match="language must be a non-empty string"):
        Selector(language=" ")


def test_normalize_text_preserves_non_ascii_letters():
    selector = Selector(mirror="https://libgen.test")
    assert selector._normalize_text("中文 标题 123") == "中文 标题 123"


def test_select_filters_title_language_mismatch():
    selector = Selector(language="English", mirror="https://libgen.test")
    book = _make_book(title="中文 标题", language="English")

    selected = selector.select(
        title="English Title",
        authors="Example Author",
        year=2020,
        table=[book],
    )

    assert selected == []


def test_select_allows_title_language_mismatch_when_in_query():
    selector = Selector(language="English", mirror="https://libgen.test")
    book = _make_book(title="ABC 中文", language="English")

    selected = selector.select(
        title="ABC 中文",
        authors="Example Author",
        year=2020,
        table=[book],
    )

    assert selected == [book]


def test_select_rejects_title_language_mismatch_not_in_query():
    selector = Selector(language="English", mirror="https://libgen.test")
    book = _make_book(title="ABC 中文", language="English")

    selected = selector.select(
        title="ABC",
        authors="Example Author",
        year=2020,
        table=[book],
    )

    assert selected == []
