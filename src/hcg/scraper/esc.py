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
    USER_AGENT,
    write_manifest,
    read_manifest,
    year_from_text,
)

ESC_GUIDELINES_URL = "https://www.escardio.org/Guidelines/Clinical-Practice-Guidelines"
ESC_ALL_GUIDELINES_URL = (
    "https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/"
)
DOI_TEXT_MARKERS = (
    "declaration of interest report",
    "declarations of interest",
    "conflict of interest policy",
    "for esc guidelines: the report below lists declarations of interest",
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

    article_url = None
    direct_pdf_url = None
    for anchor in soup.find_all("a", href=True):
        href = resolve_url(detail_url, anchor.get("href"))
        if not href:
            continue
        text = anchor.get_text(" ", strip=True).lower()
        lowered_href = href.lower()

        if "download the doi" in text or "declaration of interest" in text:
            continue
        if "academic.oup.com" in lowered_href:
            if article_url is None:
                article_url = href
            continue
        if lowered_href.endswith(".pdf") and "doi" not in text and "slide" not in text:
            if direct_pdf_url is None:
                direct_pdf_url = href

    if article_url is None and direct_pdf_url is None:
        return None

    download_url = article_url or direct_pdf_url
    download_mode = "render_article_pdf" if article_url else "direct_pdf"
    return GuidelineCandidate(
        dataset=ESC_DATASET,
        title=title,
        landing_url=detail_url,
        download_url=download_url,
        year=year_from_text(title),
        metadata={
            "publisher": "ESC",
            "download_mode": download_mode,
            "article_url": article_url,
        },
    )


def read_pdf_first_page_text(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(pdf_path))
        if not reader.pages:
            return ""
        return (reader.pages[0].extract_text() or "").strip()
    except Exception:
        return ""


def is_doi_report_text(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(marker in normalized for marker in DOI_TEXT_MARKERS)


def is_doi_report_pdf(pdf_path: Path) -> bool:
    return is_doi_report_text(read_pdf_first_page_text(pdf_path))


class EscGuidelineScraper:
    def __init__(
        self,
        paths: DatasetPaths,
        *,
        headless: bool = True,
        timeout_seconds: float = 60.0,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> None:
        self.paths = paths
        self.headless = headless
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
                    if is_doi_report_pdf(existing_path):
                        self.logger.warning(
                            "Existing ESC PDF for '%s' is a declaration-of-interest report; refreshing it",
                            candidate.title,
                        )
                    else:
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
                    records.append(
                        DownloadRecord(candidate=candidate, status="missing" if existing_path is None else "stale")
                    )
                    continue

                destination = self.paths.source_pdf_dir / slugify(candidate.title) / f"{slugify(candidate.title)}.pdf"
                try:
                    bytes_written = self._download_candidate(session, candidate, destination)
                    if is_doi_report_pdf(destination):
                        raise RuntimeError(
                            f"ESC download for '{candidate.title}' produced a declaration-of-interest PDF instead of the guideline"
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

    def _download_candidate(self, session, candidate: GuidelineCandidate, destination: Path) -> int:
        download_mode = str(candidate.metadata.get("download_mode") or "")
        if download_mode == "render_article_pdf":
            return self._render_article_to_pdf(candidate.download_url or candidate.landing_url, destination, candidate.title)
        return download_file(
            session,
            candidate.download_url or candidate.landing_url,
            destination,
            logger=self.logger,
            description=f"ESC {destination.stem}",
            timeout_seconds=self.timeout_seconds,
        )

    def _render_article_to_pdf(self, article_url: str, destination: Path, title: str) -> int:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - exercised during runtime only
            raise RuntimeError(
                "Playwright is required for ESC article rendering. Install project dependencies and run "
                "'playwright install chromium'."
            ) from exc

        timeout_ms = int(self.timeout_seconds * 1000)
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.headless)
                context = browser.new_context(locale="en-US", user_agent=USER_AGENT)
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                self.logger.info("Rendering ESC article PDF for %s from %s", title, article_url)
                page.goto(article_url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle")
                body_text = page.locator("body").inner_text()
                if "just a moment" in page.title().lower() or "verify you are human" in body_text.lower():
                    raise RuntimeError(f"OUP blocked automated access for ESC article '{title}'")
                page.emulate_media(media="screen")
                page.pdf(
                    path=str(destination),
                    format="A4",
                    print_background=True,
                    margin={"top": "0.5in", "right": "0.5in", "bottom": "0.5in", "left": "0.5in"},
                )
                context.close()
                browser.close()
        except Exception as exc:  # noqa: BLE001
            raise self._rewrite_browser_launch_error(exc) from exc

        return destination.stat().st_size

    def _rewrite_browser_launch_error(self, exc: Exception) -> RuntimeError:
        error_text = str(exc)
        lowered = error_text.lower()
        if "executable doesn't exist" in lowered:
            return RuntimeError(
                "Playwright Chromium is not installed on this machine. "
                "Run `.venv/bin/playwright install chromium` once, then rerun the command."
            )
        if "host system is missing dependencies" in lowered or "error while loading shared libraries" in lowered:
            return RuntimeError(
                "Playwright Chromium dependencies are missing on this machine. "
                "On Ubuntu, run `sudo .venv/bin/playwright install --with-deps chromium` once, then rerun the command."
            )
        return RuntimeError(error_text)

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
