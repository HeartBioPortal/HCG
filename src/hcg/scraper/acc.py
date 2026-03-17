from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from requests import Session
from tqdm import tqdm

from hcg.paths import ACC_AHA_DATASET, PROJECT_ROOT, DatasetPaths
from hcg.scraper.models import DownloadRecord, GuidelineCandidate, ScrapeResult
from hcg.scraper.utils import (
    build_logger,
    build_session,
    dedupe_urls,
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

ACC_GUIDELINES_URL = "https://www.acc.org/guidelines"
ACC_SKIP_TOKENS = (
    "clinical performance",
    "statement",
    "consensus",
    "competencies",
    "appropriate use",
    "care pathway",
    "concise clinical guidance",
    "policy",
    "quality measure",
)


def parse_acc_candidates(html: str) -> list[GuidelineCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[str, GuidelineCandidate] = {}

    for anchor in soup.find_all("a", href=True):
        href = resolve_url(ACC_GUIDELINES_URL, anchor.get("href"))
        if not href or "jacc.org/doi/" not in href:
            continue

        raw_label = normalize_title(anchor.get_text(" ", strip=True))
        if not raw_label or raw_label.lower().startswith("read the "):
            continue

        title_attr = normalize_title(anchor.get("title") or "")
        if raw_label.startswith("Guidelines ") and raw_label.endswith(" Go to Document"):
            title = raw_label.removeprefix("Guidelines ").removesuffix(" Go to Document").strip()
        else:
            title = title_attr or raw_label

        if not title:
            continue

        lowered = title.lower()
        if any(token in lowered for token in ACC_SKIP_TOKENS):
            continue
        if (
            not title_attr
            and not raw_label.startswith("Guidelines ")
            and "guideline" not in lowered
            and "focused update" not in lowered
        ):
            continue

        if href not in candidates:
            candidates[href] = GuidelineCandidate(
                dataset=ACC_AHA_DATASET,
                title=title,
                landing_url=href,
                year=year_from_text(title),
                source_label=raw_label or None,
                metadata={"publisher": "ACC/JACC"},
            )

    return sorted(candidates.values(), key=lambda candidate: (candidate.year or 0, candidate.title), reverse=True)


class AccGuidelineScraper:
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
        self.logger = build_logger("hcg.scraper.acc", self.paths.scraper_log_path)

    def discover(self, session: Session | None = None) -> list[GuidelineCandidate]:
        own_session = session is None
        session = session or build_session()
        try:
            self.logger.info("Fetching ACC guideline catalog from %s", ACC_GUIDELINES_URL)
            response = session.get(ACC_GUIDELINES_URL, timeout=self.timeout_seconds)
            response.raise_for_status()
            candidates = parse_acc_candidates(response.text)
            if self.limit is not None:
                candidates = candidates[: self.limit]
            self.logger.info("Discovered %s ACC/AHA guideline candidates", len(candidates))
            return candidates
        finally:
            if own_session:
                session.close()

    def scrape(self) -> ScrapeResult:
        session = build_session()
        manifest = read_manifest(self.paths.scraper_manifest_path)
        pdf_index = existing_pdf_index(self.paths.source_pdf_dir, self.paths.raw_output_dir)
        records: list[DownloadRecord] = []
        pending_downloads: list[GuidelineCandidate] = []

        try:
            for candidate in tqdm(self.discover(session), desc="ACC catalog", unit="guideline"):
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

                pending_downloads.append(candidate)

            if pending_downloads:
                self.logger.info("Downloading %s new ACC/AHA PDFs", len(pending_downloads))
                browser_context = self._browser_context()
                with browser_context as context:
                    for candidate in tqdm(pending_downloads, desc="ACC downloads", unit="pdf"):
                        try:
                            pdf_path, bytes_written = self._download_candidate(context, candidate)
                            pdf_index.append(
                                {
                                    "path": pdf_path,
                                    "tokens": text_tokens(candidate.title),
                                    "year": candidate.year,
                                }
                            )
                            records.append(
                                DownloadRecord(
                                    candidate=candidate,
                                    status="downloaded",
                                    pdf_path=pdf_path,
                                    bytes_written=bytes_written,
                                    sha256=sha256_file(pdf_path),
                                )
                            )
                        except Exception as exc:  # noqa: BLE001
                            error_text = str(exc)
                            if "cloudflare" in error_text.lower():
                                self.logger.warning(
                                    "ACC download blocked upstream for '%s': %s",
                                    candidate.title,
                                    error_text,
                                )
                                records.append(
                                    DownloadRecord(candidate=candidate, status="blocked", error=error_text)
                                )
                                continue
                            self.logger.exception("Failed to download ACC guideline '%s'", candidate.title)
                            records.append(DownloadRecord(candidate=candidate, status="failed", error=error_text))
            elif self.dry_run:
                missing_count = sum(1 for record in records if record.status == "missing")
                self.logger.info("Dry run found %s ACC/AHA guideline PDF(s) not present locally", missing_count)
            else:
                self.logger.info("No new ACC/AHA PDFs detected")
        finally:
            session.close()

        if not self.dry_run:
            self._write_manifest(records)
        return ScrapeResult(dataset=ACC_AHA_DATASET, records=records, manifest_path=self.paths.scraper_manifest_path)

    def _browser_context(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - exercised during runtime only
            raise RuntimeError(
                "Playwright is required for ACC scraping. Install project dependencies and run "
                "'playwright install chromium'."
            ) from exc

        timeout_ms = int(self.timeout_seconds * 1000)
        scraper = self

        class BrowserContextManager:
            def __enter__(self):
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(headless=scraper.headless)
                self.context = self.browser.new_context(accept_downloads=True)
                self.context.set_default_timeout(timeout_ms)
                return self.context

            def __exit__(self, exc_type, exc, tb):
                self.context.close()
                self.browser.close()
                self.playwright.stop()

        return BrowserContextManager()

    def _download_candidate(self, context, candidate: GuidelineCandidate) -> tuple[Path, int]:
        pdf_path = self.paths.source_pdf_dir / slugify(candidate.title) / f"{slugify(candidate.title)}.pdf"
        page = context.new_page()
        try:
            self.logger.info("Resolving ACC guideline PDF for %s", candidate.title)
            page.goto(candidate.landing_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            self._wait_for_jacc_access(page, candidate)

            pdf_urls = self._candidate_pdf_urls(candidate.landing_url, page.url)
            pdf_urls.extend(self._pdf_links_from_page(page))
            for pdf_url in dedupe_urls(pdf_urls):
                bytes_written = self._download_pdf_via_context(context, pdf_url, pdf_path)
                if bytes_written is not None:
                    return pdf_path, bytes_written

            selectors = [
                "a[href*='/doi/pdf/']",
                "a[href*='/doi/epdf/']",
                "a:has-text('PDF')",
                "button:has-text('PDF')",
                "text=/download pdf/i",
                "text=/view pdf/i",
            ]
            for selector in selectors:
                locator = page.locator(selector)
                if locator.count() == 0:
                    continue
                try:
                    with page.expect_download(timeout=int(self.timeout_seconds * 1000)) as download_info:
                        locator.first.click()
                    download = download_info.value
                    pdf_path.parent.mkdir(parents=True, exist_ok=True)
                    download.save_as(str(pdf_path))
                    if pdf_path.exists() and pdf_path.stat().st_size > 0:
                        return pdf_path, pdf_path.stat().st_size
                except Exception:  # noqa: BLE001
                    continue
        finally:
            page.close()

        raise RuntimeError(f"Unable to resolve PDF link from JACC for {candidate.title}")

    def _wait_for_jacc_access(self, page, candidate: GuidelineCandidate) -> None:
        if not self._is_cloudflare_interstitial(page):
            return

        if self.headless:
            raise RuntimeError(
                f"JACC blocked headless Chromium for '{candidate.title}' with a Cloudflare verification page. "
                "ACC discovery can continue, but this PDF cannot be downloaded automatically right now."
            )

        raise RuntimeError(
            f"JACC blocked automated access for '{candidate.title}' with a Cloudflare verification page. "
            "ACC discovery can continue, but this PDF cannot be downloaded automatically right now."
        )

    def _is_cloudflare_interstitial(self, page) -> bool:
        title = (page.title() or "").strip().lower()
        if "just a moment" in title:
            return True

        body = (page.text_content("body") or "").lower()
        return "security verification" in body or "enable javascript and cookies to continue" in body

    def _candidate_pdf_urls(self, *article_urls: str) -> list[str]:
        urls: list[str] = []
        for article_url in article_urls:
            if "/doi/" not in article_url:
                continue
            urls.append(article_url.replace("/doi/", "/doi/pdf/"))
            urls.append(article_url.replace("/doi/", "/doi/epdf/"))
        return urls

    def _pdf_links_from_page(self, page) -> list[str]:
        links = page.eval_on_selector_all(
            "a[href]",
            """
            elements => elements.map(element => ({
              href: element.href,
              text: (element.innerText || element.textContent || '').trim()
            }))
            """,
        )
        urls: list[str] = []
        for link in links:
            href = link.get("href") or ""
            text = (link.get("text") or "").lower()
            if "/doi/pdf/" in href or "/doi/epdf/" in href or ".pdf" in href.lower():
                urls.append(href)
                continue
            if "pdf" in text and href.startswith("http"):
                urls.append(href)
        return urls

    def _download_pdf_via_context(self, context, url: str, destination: Path) -> int | None:
        response = context.request.get(url, timeout=int(self.timeout_seconds * 1000), fail_on_status_code=False)
        if not response.ok:
            return None

        content_type = (response.headers.get("content-type") or "").lower()
        body = response.body()
        if "pdf" not in content_type and not body.startswith(b"%PDF"):
            return None

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        self.logger.info("Downloaded ACC PDF from %s", url)
        return len(body)

    def _write_manifest(self, records: Iterable[DownloadRecord]) -> None:
        existing_payload = read_manifest(self.paths.scraper_manifest_path)
        documents_by_url = {
            document.get("landing_url"): document
            for document in existing_payload.get("documents", [])
            if document.get("landing_url")
        }
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "dataset": ACC_AHA_DATASET,
            "catalog_url": ACC_GUIDELINES_URL,
            "updated_at": now,
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
                "source_label": record.candidate.source_label,
                "metadata": record.candidate.metadata,
            }

        payload["documents"] = sorted(
            documents_by_url.values(),
            key=lambda document: str(document.get("title", "")).lower(),
        )

        write_manifest(self.paths.scraper_manifest_path, payload)
