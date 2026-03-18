from __future__ import annotations

from hcg.scraper.acc import AccGuidelineScraper, parse_acc_candidates
from hcg.scraper.esc import parse_esc_detail_candidate, parse_esc_detail_urls
from hcg.scraper.models import GuidelineCandidate
from hcg.paths import DatasetPaths
from hcg.scraper.utils import existing_pdf_index, match_existing_pdf_from_index


def test_parse_acc_candidates_filters_to_guidelines() -> None:
    html = """
    <html>
      <body>
        <a
          href="https://www.jacc.org/doi/10.1016/j.jacc.2024.02.013"
          title="Read on JACC: 2024 ACC/AHA Guideline for the Management of Lower Extremity Peripheral Artery Disease"
        >2024 Lower Extremity Peripheral Artery Disease</a>
        <a
          href="https://www.jacc.org/doi/10.1016/j.jacc.2024.09.999"
          title="Read on JACC: 2024 ACC Expert Consensus Decision Pathway"
        >2024 Consensus</a>
      </body>
    </html>
    """

    candidates = parse_acc_candidates(html)

    assert len(candidates) == 1
    assert candidates[0].title == "2024 ACC/AHA Guideline for the Management of Lower Extremity Peripheral Artery Disease"
    assert candidates[0].landing_url == "https://www.jacc.org/doi/10.1016/j.jacc.2024.02.013"


def test_parse_esc_detail_candidate_prefers_article_link_and_ignores_doi() -> None:
    html = """
    <html>
      <body>
        <h1>2024 ESC Guidelines for the management of chronic coronary syndromes</h1>
        <a href="https://academic.oup.com/eurheartj/article-lookup/doi/10.1093/eurheartj/ehae177">
          Read the European Heart Journal
        </a>
        <a href="https://yjxzhi.files.cmp.optimizely.com/download/abcdef">Download the DOI</a>
      </body>
    </html>
    """

    candidate = parse_esc_detail_candidate(
        html,
        "https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/chronic-coronary-syndromes/",
    )

    assert candidate is not None
    assert candidate.title == "2024 ESC Guidelines for the management of chronic coronary syndromes"
    assert candidate.download_url == "https://academic.oup.com/eurheartj/article-lookup/doi/10.1093/eurheartj/ehae177"
    assert candidate.metadata["download_mode"] == "render_article_pdf"


def test_parse_esc_detail_candidate_skips_generic_esc_journal_hub() -> None:
    html = """
    <html>
      <body>
        <h1>The Role of Endomyocardial Biopsy in the Management of Cardiovascular Disease Guidelines</h1>
        <a href="https://academic.oup.com/esc/pages/esc-journals">Read the European Heart Journal</a>
      </body>
    </html>
    """

    candidate = parse_esc_detail_candidate(
        html,
        "https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/endomyocardial-biopsy/",
    )

    assert candidate is None


def test_parse_esc_detail_urls_extracts_guideline_pages() -> None:
    html = """
    <html>
      <body>
        <a href="/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/atrial-fibrillation/">AF</a>
        <a href="/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/chronic-coronary-syndromes/">CCS</a>
        <a href="/Guidelines/Clinical-Practice-Guidelines">Overview</a>
      </body>
    </html>
    """

    urls = parse_esc_detail_urls(html)

    assert urls == [
        "https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/atrial-fibrillation/",
        "https://www.escardio.org/guidelines/clinical-practice-guidelines/all-esc-practice-guidelines/chronic-coronary-syndromes/",
    ]


def test_match_existing_pdf_from_index_bootstraps_existing_files(tmp_path) -> None:
    pdf_path = tmp_path / "gornik-et-al-2024-2024-acc-aha-guideline-for-the-management-of-lower.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    raw_output_dir = tmp_path / "raw"
    raw_output_dir.mkdir()
    page_dir = raw_output_dir / pdf_path.stem
    page_dir.mkdir()
    (page_dir / "1.json").write_text(
        """
        {
          "content": {
            "title": "2024 ACC/AHA Guideline for the Management of Lower Extremity Peripheral Artery Disease"
          },
          "genes": []
        }
        """.strip(),
        encoding="utf-8",
    )
    pdf_index = existing_pdf_index(tmp_path, raw_output_dir)

    match = match_existing_pdf_from_index(
        "2024 ACC/AHA Guideline for the Management of Lower Extremity Peripheral Artery Disease",
        pdf_index,
    )

    assert match == pdf_path


def test_acc_scraper_marks_cloudflare_blocks_without_hanging(tmp_path, monkeypatch) -> None:
    paths = DatasetPaths(
        name="acc_aha",
        root_dir=tmp_path,
        source_pdf_dir=tmp_path / "source_pdfs",
        raw_output_dir=tmp_path / "openai_outputs",
        scraper_manifest_path=tmp_path / "scraper_manifest.json",
        scraper_log_path=tmp_path / "scraper.log",
    )
    candidate = GuidelineCandidate(
        dataset="acc_aha",
        title="2026 Dyslipidemia",
        landing_url="https://www.jacc.org/doi/10.1016/j.jacc.2025.11.016",
    )

    monkeypatch.setattr(AccGuidelineScraper, "discover", lambda self, session=None: [candidate])

    class DummyContextManager:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(AccGuidelineScraper, "_browser_context", lambda self: DummyContextManager())
    monkeypatch.setattr(
        AccGuidelineScraper,
        "_download_candidate",
        lambda self, context, candidate: (_ for _ in ()).throw(
            RuntimeError("JACC blocked automated access with a Cloudflare verification page.")
        ),
    )

    result = AccGuidelineScraper(paths, headless=True, limit=1).scrape()

    assert len(result.records) == 1
    assert result.records[0].status == "blocked"
    assert "Cloudflare" in result.records[0].error
