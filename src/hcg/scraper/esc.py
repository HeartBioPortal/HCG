from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from tqdm import tqdm

from hcg.paths import ESC_DATASET, PROJECT_ROOT, DatasetPaths
from hcg.scraper.models import DownloadRecord, GuidelineCandidate, ScrapeResult
from hcg.scraper.utils import (
    build_logger,
    build_session,
    download_file,
    existing_pdf_index,
    manifest_lookup,
    match_existing_pdf_from_index,
    normalize_title,
    relative_to_project,
    resolve_url,
    sha256_file,
    slugify,
    text_tokens,
    write_manifest,
    read_manifest,
    year_from_text,
)

ESC_GUIDELINES_URL = "https://www.escardio.org/Guidelines/Clinical-Practice-Guidelines"
ESC_ALL_GUIDELINES_URL = (
    "https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/"
)


def parse_esc_detail_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = resolve_url(ESC_ALL_GUIDELINES_URL, anchor.get("href"))
        if not href:
            continue
        lowered = href.lower()
        if "/all-esc-practice-guidelines/" not in lowered:
            continue
        if lowered.rstrip("/") == ESC_ALL_GUIDELINES_URL.rstrip("/").lower():
            continue
        urls.add(href)
    return sorted(urls)


def parse_esc_detail_candidate(html: str, detail_url: str) -> GuidelineCandidate | None:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.find("h1")
    if title_node is None:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title is not None:
            title_text = og_title.get("content", "")
        else:
            title_text = ""
    else:
        title_text = title_node.get_text(" ", strip=True)

    title = normalize_title(title_text)
    if not title:
        return None

    download_url = None
    for anchor in soup.find_all("a", href=True):
        href = resolve_url(detail_url, anchor.get("href"))
        if not href:
            continue
        text = anchor.get_text(" ", strip=True).lower()
        if "files.cmp.optimizely.com/download/" in href.lower():
            download_url = href
            break
        if "download the doi" in text or ("download" in text and href.lower().endswith(".pdf")):
            download_url = href
            break

    if download_url is None:
        return None

    return GuidelineCandidate(
        dataset=ESC_DATASET,
        title=title,
        landing_url=detail_url,
        download_url=download_url,
        year=year_from_text(title),
        metadata={"publisher": "ESC"},
    )


class EscGuidelineScraper:
    def __init__(
        self,
        paths: DatasetPaths,
        *,
        timeout_seconds: float = 60.0,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> None:
        self.paths = paths
        self.timeout_seconds = timeout_seconds
        self.limit = limit
        self.dry_run = dry_run
        self.paths.ensure_directories()
        self.logger = build_logger("hcg.scraper.esc", self.paths.scraper_log_path)

    def discover(self) -> list[GuidelineCandidate]:
        session = build_session()
        candidates: list[GuidelineCandidate] = []
        try:
            self.logger.info("Fetching ESC guideline index from %s", ESC_ALL_GUIDELINES_URL)
            index_response = session.get(ESC_ALL_GUIDELINES_URL, timeout=self.timeout_seconds)
            index_response.raise_for_status()
            detail_urls = parse_esc_detail_urls(index_response.text)
            if self.limit is not None:
                detail_urls = detail_urls[: self.limit]

            for detail_url in tqdm(detail_urls, desc="ESC detail pages", unit="page"):
                try:
                    response = session.get(detail_url, timeout=self.timeout_seconds)
                    response.raise_for_status()
                    candidate = parse_esc_detail_candidate(response.text, detail_url)
                    if candidate is None:
                        self.logger.warning("No downloadable PDF found on %s", detail_url)
                        continue
                    candidates.append(candidate)
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Failed to inspect ESC detail page %s", detail_url)
                    self.logger.warning("Skipping %s after error: %s", detail_url, exc)

            self.logger.info("Discovered %s ESC guideline candidates", len(candidates))
            return candidates
        finally:
            session.close()

    def scrape(self) -> ScrapeResult:
        manifest = read_manifest(self.paths.scraper_manifest_path)
        pdf_index = existing_pdf_index(self.paths.source_pdf_dir, self.paths.raw_output_dir)
        session = build_session()
        records: list[DownloadRecord] = []
        try:
            candidates = self.discover()
            for candidate in tqdm(candidates, desc="ESC downloads", unit="pdf"):
                existing_path = manifest_lookup(manifest, candidate.landing_url, PROJECT_ROOT)
                if existing_path is None:
                    existing_path = match_existing_pdf_from_index(candidate.title, pdf_index)

                if existing_path is not None:
                    records.append(
                        DownloadRecord(
                            candidate=candidate,
                            status="existing",
                            pdf_path=existing_path,
                            sha256=sha256_file(existing_path),
                        )
                    )
                    continue

                if self.dry_run:
                    records.append(DownloadRecord(candidate=candidate, status="missing"))
                    continue

                destination = self.paths.source_pdf_dir / slugify(candidate.title) / f"{slugify(candidate.title)}.pdf"
                try:
                    bytes_written = download_file(
                        session,
                        candidate.download_url or candidate.landing_url,
                        destination,
                        logger=self.logger,
                        description=f"ESC {destination.stem}",
                        timeout_seconds=self.timeout_seconds,
                    )
                    pdf_index.append(
                        {
                            "path": destination,
                            "tokens": text_tokens(candidate.title),
                            "year": candidate.year,
                        }
                    )
                    records.append(
                        DownloadRecord(
                            candidate=candidate,
                            status="downloaded",
                            pdf_path=destination,
                            bytes_written=bytes_written,
                            sha256=sha256_file(destination),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Failed to download ESC guideline '%s'", candidate.title)
                    records.append(DownloadRecord(candidate=candidate, status="failed", error=str(exc)))
        finally:
            session.close()

        if not self.dry_run:
            self._write_manifest(records)
        return ScrapeResult(dataset=ESC_DATASET, records=records, manifest_path=self.paths.scraper_manifest_path)

    def _write_manifest(self, records: list[DownloadRecord]) -> None:
        existing_payload = read_manifest(self.paths.scraper_manifest_path)
        documents_by_url = {
            document.get("landing_url"): document
            for document in existing_payload.get("documents", [])
            if document.get("landing_url")
        }
        payload = {
            "dataset": ESC_DATASET,
            "catalog_url": ESC_ALL_GUIDELINES_URL,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "documents": [],
        }
        for record in records:
            documents_by_url[record.candidate.landing_url] = {
                "title": record.candidate.title,
                "year": record.candidate.year,
                "landing_url": record.candidate.landing_url,
                "download_url": record.candidate.download_url,
                "status": record.status,
                "local_pdf": None
                if record.pdf_path is None
                else relative_to_project(record.pdf_path, PROJECT_ROOT),
                "sha256": record.sha256,
                "bytes_written": record.bytes_written,
                "error": record.error,
                "metadata": record.candidate.metadata,
            }

        payload["documents"] = sorted(
            documents_by_url.values(),
            key=lambda document: str(document.get("title", "")).lower(),
        )

        write_manifest(self.paths.scraper_manifest_path, payload)
