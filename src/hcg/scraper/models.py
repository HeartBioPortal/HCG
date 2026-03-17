from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class GuidelineCandidate:
    dataset: str
    title: str
    landing_url: str
    download_url: str | None = None
    year: int | None = None
    source_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DownloadRecord:
    candidate: GuidelineCandidate
    status: str
    pdf_path: Path | None = None
    bytes_written: int | None = None
    sha256: str | None = None
    error: str | None = None


@dataclass(slots=True)
class ScrapeResult:
    dataset: str
    records: list[DownloadRecord]
    manifest_path: Path

    @property
    def discovered_count(self) -> int:
        return len(self.records)

    @property
    def downloaded_paths(self) -> list[Path]:
        return [record.pdf_path for record in self.records if record.status == "downloaded" and record.pdf_path]

    @property
    def existing_paths(self) -> list[Path]:
        return [record.pdf_path for record in self.records if record.status == "existing" and record.pdf_path]

    @property
    def blocked_records(self) -> list[DownloadRecord]:
        return [record for record in self.records if record.status == "blocked"]

    @property
    def failed_records(self) -> list[DownloadRecord]:
        return [record for record in self.records if record.status == "failed"]
