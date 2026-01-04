"""Book model for libgen search results."""


class Book:
    def __init__(
        self,
        id,
        title,
        author,
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
        self.publisher = publisher
        self.year = year
        self.language = language
        self.pages = pages
        self.size = size
        self.extension = extension
        self.md5 = md5
        self.mirrors = mirrors
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
