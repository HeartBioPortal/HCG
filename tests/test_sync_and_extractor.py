from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hcg.cli import require_api_key
import hcg.scraper.esc as esc_module
import hcg.sync as sync_module
from hcg.extractor import GuidelinePageExtractor
from hcg.paths import DatasetPaths
from hcg.scraper.acc import AccGuidelineScraper
from hcg.scraper.esc import EscGuidelineScraper, is_doi_report_text, parse_esc_detail_candidate
from hcg.scraper.models import DownloadRecord, GuidelineCandidate, ScrapeResult
from hcg.scraper.utils import slugify


def make_dataset_paths(tmp_path: Path, name: str) -> DatasetPaths:
    root = tmp_path / name
    return DatasetPaths(
        name=name,
        root_dir=root,
        source_pdf_dir=root / "source_pdfs",
        raw_output_dir=root / "openai_outputs",
        scraper_manifest_path=root / "scraper_manifest.json",
        scraper_log_path=root / "scraper.log",
    )


def test_esc_scraper_does_not_redownload_existing_pdf(tmp_path, monkeypatch) -> None:
    paths = make_dataset_paths(tmp_path, "esc")
    paths.ensure_directories()
    title = "2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure"
    slug = slugify(title)
    pdf_path = paths.source_pdf_dir / slug / f"{slug}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4")

    candidate = GuidelineCandidate(
        dataset="esc",
        title=title,
        landing_url="https://www.escardio.org/guideline-detail",
        download_url="https://files.example.org/doc.pdf",
    )

    monkeypatch.setattr(EscGuidelineScraper, "discover", lambda self: [candidate])

    def fail_download(*args, **kwargs):
        raise AssertionError("download_file should not be called for an existing PDF")

    monkeypatch.setattr(esc_module, "download_file", fail_download)

    result = EscGuidelineScraper(paths, limit=1).scrape()

    assert len(result.records) == 1
    assert result.records[0].status == "existing"
    assert result.records[0].pdf_path == pdf_path


def test_parse_esc_detail_candidate_prefers_article_link_over_doi() -> None:
    html = """
    <html>
      <body>
        <h1>2022 ESC Guidelines on cardio-oncology</h1>
        <a href="https://academic.oup.com/eurheartj/article-lookup/doi/10.1093/eurheartj/ehac244">
          Read the European Heart Journal
        </a>
        <a href="https://files.cmp.optimizely.com/download/bad-doi-report">Download the DOI</a>
      </body>
    </html>
    """

    candidate = parse_esc_detail_candidate(
        html,
        "https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/cardio-oncology-guidelines/",
    )

    assert candidate is not None
    assert candidate.download_url == "https://academic.oup.com/eurheartj/article-lookup/doi/10.1093/eurheartj/ehac244"
    assert candidate.metadata["download_mode"] == "render_article_pdf"


def test_esc_scraper_replaces_existing_doi_report(tmp_path, monkeypatch) -> None:
    paths = make_dataset_paths(tmp_path, "esc")
    paths.ensure_directories()
    title = "2022 ESC Guidelines on cardio-oncology"
    slug = slugify(title)
    pdf_path = paths.source_pdf_dir / slug / f"{slug}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"old doi report")

    candidate = GuidelineCandidate(
        dataset="esc",
        title=title,
        landing_url="https://www.escardio.org/guideline-detail",
        download_url="https://academic.oup.com/eurheartj/article-lookup/doi/10.1093/eurheartj/ehac244",
        metadata={"download_mode": "render_article_pdf"},
    )

    monkeypatch.setattr(EscGuidelineScraper, "discover", lambda self: [candidate])
    monkeypatch.setattr(esc_module, "is_doi_report_pdf", lambda path: path.read_bytes() == b"old doi report")

    def fake_render(self, article_url: str, destination: Path, title: str) -> int:
        destination.write_bytes(b"%PDF-1.4 refreshed guideline")
        return destination.stat().st_size

    monkeypatch.setattr(EscGuidelineScraper, "_render_article_to_pdf", fake_render)

    result = EscGuidelineScraper(paths, limit=1).scrape()

    assert len(result.records) == 1
    assert result.records[0].status == "downloaded"
    assert result.records[0].pdf_path == pdf_path
    assert pdf_path.read_bytes().startswith(b"%PDF-1.4 refreshed guideline")


def test_is_doi_report_text_detects_declaration_reports() -> None:
    assert is_doi_report_text(
        "ESC Declaration of Interest Report 2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure"
    )
    assert not is_doi_report_text("2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure")


def test_wait_for_article_ready_uses_content_presence_not_networkidle(tmp_path) -> None:
    paths = make_dataset_paths(tmp_path, "esc")
    scraper = EscGuidelineScraper(paths, timeout_seconds=1.0)

    class FakeLocator:
        def __init__(self, text: str) -> None:
            self._text = text
            self.first = self

        def inner_text(self, timeout=None) -> str:
            return self._text

    class FakePage:
        def __init__(self) -> None:
            self._body_text = (
                "2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure "
                + ("clinical guidance " * 400)
            )

        def title(self) -> str:
            return "ESC Guideline Article"

        def evaluate(self, script: str) -> str:
            return self._body_text

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self._body_text if selector == "main" else "")

        def wait_for_timeout(self, ms: int) -> None:
            raise AssertionError("wait_for_timeout should not be needed once article content is present")

    body_text = scraper._wait_for_article_ready(
        FakePage(),
        "2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure",
    )

    assert "clinical guidance" in body_text


def test_process_single_pdf_writes_readable_non_error_json(tmp_path, monkeypatch) -> None:
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    pdf_path = pdf_dir / "demo.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    output_dir = tmp_path / "outputs"
    page_lookup: dict[str, int] = {}

    def fake_convert_pdf_to_images(self, pdf_path: Path, pages=None):
        page_numbers = [1, 2] if pages is None else list(pages)
        temp_files = []
        for page_number in page_numbers:
            handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            handle.write(b"fake image")
            handle.close()
            page_lookup[handle.name] = page_number
            temp_files.append((page_number, handle))
        return temp_files

    def fake_analyze_image(self, image_path: Path):
        page_number = page_lookup[str(image_path)]
        return {
            "content": {"page_number": page_number, "status": "ok"},
            "genes": [
                {
                    "Gene": f"GENE{page_number}",
                    "Occurrences": 1,
                    "Associated Conditions": ["Condition"],
                    "context": [f"Page {page_number}"],
                }
            ],
        }

    monkeypatch.setattr(GuidelinePageExtractor, "convert_pdf_to_images", fake_convert_pdf_to_images)
    monkeypatch.setattr(GuidelinePageExtractor, "analyze_image", fake_analyze_image)

    extractor = GuidelinePageExtractor(
        pdf_dir=pdf_dir,
        output_dir=output_dir,
        model="gpt-5-mini",
        api_key="test-key",
    )
    extractor.process_single_pdf(pdf_path)
    extractor.aggregate_outputs()

    page_one = json.loads((output_dir / "demo" / "1.json").read_text(encoding="utf-8"))
    page_two = json.loads((output_dir / "demo" / "2.json").read_text(encoding="utf-8"))
    aggregated = json.loads((output_dir / "demo_aggregated.json").read_text(encoding="utf-8"))

    assert page_one["content"]["status"] == "ok"
    assert "error" not in page_one["content"]
    assert page_two["content"]["page_number"] == 2
    assert len(aggregated["content"]) == 2
    assert [gene["Gene"] for gene in aggregated["genes"]] == ["GENE1", "GENE2"]


def test_sync_extracts_existing_pdf_without_redownloading(tmp_path, monkeypatch) -> None:
    paths = make_dataset_paths(tmp_path, "esc")
    paths.ensure_directories()
    title = "2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure"
    slug = slugify(title)
    pdf_path = paths.source_pdf_dir / slug / f"{slug}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4")

    scrape_result = ScrapeResult(
        dataset="esc",
        records=[
            DownloadRecord(
                candidate=GuidelineCandidate(
                    dataset="esc",
                    title=title,
                    landing_url="https://www.escardio.org/guideline-detail",
                    download_url="https://files.example.org/doc.pdf",
                ),
                status="existing",
                pdf_path=pdf_path,
            )
        ],
        manifest_path=paths.scraper_manifest_path,
    )

    monkeypatch.setattr(sync_module, "run_scrapers", lambda *args, **kwargs: {"esc": scrape_result})
    monkeypatch.setattr(sync_module, "get_dataset_paths", lambda dataset: paths)

    recorded: dict[str, object] = {}

    class FakeExtractor:
        def __init__(self, *, pdf_dir, output_dir, model, sleep_seconds, api_key) -> None:
            recorded["init"] = {
                "pdf_dir": pdf_dir,
                "output_dir": output_dir,
                "model": model,
                "sleep_seconds": sleep_seconds,
                "api_key": api_key,
            }
            self.output_dir = output_dir

        def process_pdf_paths(self, pdf_paths) -> None:
            recorded["pdf_paths"] = list(pdf_paths)
            pdf_output_dir = self.output_dir / pdf_path.stem
            pdf_output_dir.mkdir(parents=True, exist_ok=True)
            (pdf_output_dir / "1.json").write_text(
                json.dumps({"content": {"status": "ok"}, "genes": []}),
                encoding="utf-8",
            )

        def aggregate_outputs(self) -> None:
            (self.output_dir / f"{pdf_path.stem}_aggregated.json").write_text(
                json.dumps({"content": [{"content": {"status": "ok"}, "genes": []}], "genes": []}),
                encoding="utf-8",
            )

    monkeypatch.setattr(sync_module, "GuidelinePageExtractor", FakeExtractor)

    results = sync_module.sync_datasets(
        ["esc"],
        model="gpt-5-mini",
        sleep_seconds=0.0,
        api_key="test-key",
        headless=True,
        timeout_seconds=1.0,
    )

    assert recorded["pdf_paths"] == [pdf_path]
    assert results["esc"].extracted_pdfs == [pdf_path]
    assert json.loads((paths.raw_output_dir / f"{pdf_path.stem}_aggregated.json").read_text(encoding="utf-8"))[
        "content"
    ][0]["content"]["status"] == "ok"


def test_sync_reextracts_refreshed_pdf_and_resets_stale_outputs(tmp_path, monkeypatch) -> None:
    paths = make_dataset_paths(tmp_path, "esc")
    paths.ensure_directories()
    title = "2022 ESC Guidelines on cardio-oncology"
    slug = slugify(title)
    pdf_path = paths.source_pdf_dir / slug / f"{slug}.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4 refreshed")

    stale_pdf_output_dir = paths.raw_output_dir / pdf_path.stem
    stale_pdf_output_dir.mkdir(parents=True, exist_ok=True)
    (stale_pdf_output_dir / "1.json").write_text(
        json.dumps({"content": {"status": "stale"}, "genes": []}),
        encoding="utf-8",
    )
    (paths.raw_output_dir / f"{pdf_path.stem}_aggregated.json").write_text(
        json.dumps({"content": [{"content": {"status": "stale"}, "genes": []}], "genes": []}),
        encoding="utf-8",
    )

    scrape_result = ScrapeResult(
        dataset="esc",
        records=[
            DownloadRecord(
                candidate=GuidelineCandidate(
                    dataset="esc",
                    title=title,
                    landing_url="https://www.escardio.org/guideline-detail",
                    download_url="https://academic.oup.com/article",
                ),
                status="downloaded",
                pdf_path=pdf_path,
            )
        ],
        manifest_path=paths.scraper_manifest_path,
    )

    monkeypatch.setattr(sync_module, "run_scrapers", lambda *args, **kwargs: {"esc": scrape_result})
    monkeypatch.setattr(sync_module, "get_dataset_paths", lambda dataset: paths)

    recorded: dict[str, object] = {}

    class FakeExtractor:
        def __init__(self, *, pdf_dir, output_dir, model, sleep_seconds, api_key) -> None:
            recorded["init"] = True
            self.output_dir = output_dir

        def process_pdf_paths(self, pdf_paths) -> None:
            recorded["pdf_paths"] = list(pdf_paths)
            pdf_output_dir = self.output_dir / pdf_path.stem
            pdf_output_dir.mkdir(parents=True, exist_ok=True)
            (pdf_output_dir / "1.json").write_text(
                json.dumps({"content": {"status": "fresh"}, "genes": []}),
                encoding="utf-8",
            )

        def aggregate_outputs(self) -> None:
            (self.output_dir / f"{pdf_path.stem}_aggregated.json").write_text(
                json.dumps({"content": [{"content": {"status": "fresh"}, "genes": []}], "genes": []}),
                encoding="utf-8",
            )

    monkeypatch.setattr(sync_module, "GuidelinePageExtractor", FakeExtractor)

    results = sync_module.sync_datasets(
        ["esc"],
        model="gpt-5-mini",
        sleep_seconds=0.0,
        api_key="test-key",
        headless=True,
        timeout_seconds=1.0,
    )

    assert recorded["pdf_paths"] == [pdf_path]
    assert results["esc"].extracted_pdfs == [pdf_path]
    assert json.loads((paths.raw_output_dir / f"{pdf_path.stem}_aggregated.json").read_text(encoding="utf-8"))[
        "content"
    ][0]["content"]["status"] == "fresh"


def test_require_api_key_raises_clear_error() -> None:
    try:
        require_api_key(None, command_name="sync")
    except ValueError as exc:
        assert "OPENAI_API_KEY is required" in str(exc)
        assert "hcg sync" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("require_api_key should raise when the key is missing")


def test_acc_browser_launch_error_is_rewritten(tmp_path) -> None:
    paths = make_dataset_paths(tmp_path, "acc_aha")
    scraper = AccGuidelineScraper(paths)

    rewritten = scraper._rewrite_browser_launch_error(
        RuntimeError("BrowserType.launch: Executable doesn't exist at /tmp/chrome")
    )

    assert "playwright install chromium" in str(rewritten)
