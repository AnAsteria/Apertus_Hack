from dataclasses import dataclass, field
from app.contracts import SourceConfig


class IngestError(Exception):
    """Safe machine-readable reason; never includes response bodies or credentials."""
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Source:
    config: SourceConfig
    labels: list[str]
    tier: str
    profile: str
    sitemaps: list[str] = field(default_factory=list)
    max_sitemaps: int = 2
    max_bytes: int = 10_000_000
    max_discovered: int = 1000


@dataclass
class Fetched:
    requested_url: str
    url: str
    body: bytes
    media_type: str
    fetched_at: str
    last_modified: str | None = None
    redirects: list[str] = field(default_factory=list)


@dataclass
class Section:
    heading: str
    text: str
    page_number: int | None = None


@dataclass
class Parsed:
    title: str
    sections: list[Section]
    language: str | None
    page_type: str
    links: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    content_date: str | None = None
    last_modified: str | None = None

    @property
    def text(self) -> str:
        # A PDF form-feed preserves page boundaries in the canonical cleaned text.
        # Changing PDF pagination must never reuse citations with new page numbers.
        separator = '\f' if any(s.page_number is not None for s in self.sections) else '\n\n'
        return separator.join(s.text for s in self.sections)
