from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hcg.extractor import GuidelinePageExtractor
from hcg.paths import ACC_AHA_DATASET, GENE_REFERENCE_PATH, PROJECT_ROOT, get_dataset_paths
from hcg.release_builder import build_release
from hcg.scraper.models import ScrapeResult
from hcg.scraper.service import normalize_datasets, run_scrapers
from hcg.scraper.utils import build_logger


@dataclass(slots=True)
class DatasetSyncResult:
    scrape_result: ScrapeResult
    extracted_pdfs: list[Path]
    release_dir: Path | None = None


def sync_datasets(
    datasets: list[str] | None,
    *,
    model: str,
    sleep_seconds: float,
    api_key: str | None,
    headless: bool = True,
    timeout_seconds: float = 60.0,
    limit: int | None = None,
    build_releases: bool = True,
) -> dict[str, DatasetSyncResult]:
    logger = build_logger("hcg.sync", PROJECT_ROOT / "logs" / "sync.log")
    normalized_datasets = normalize_datasets(datasets)
    sync_results: dict[str, DatasetSyncResult] = {}

    for dataset in normalized_datasets:
        scrape_result = run_scrapers(
            [dataset],
            headless=headless,
            timeout_seconds=timeout_seconds,
            limit=limit,
        )[dataset]
        dataset_paths = get_dataset_paths(dataset)
        extracted_pdfs: list[Path] = []
        release_dir: Path | None = None

        pdfs_to_extract = pending_extraction_paths(scrape_result, dataset_paths)
        if pdfs_to_extract and not api_key:
            raise ValueError("OPENAI_API_KEY is required to extract PDFs that are missing JSON outputs during sync.")

        if pdfs_to_extract:
            logger.info(
                "Running OpenAI extraction for %s %s PDF(s) that are missing JSON outputs",
                len(pdfs_to_extract),
                dataset,
            )
            extractor = GuidelinePageExtractor(
                pdf_dir=dataset_paths.source_pdf_dir,
                output_dir=dataset_paths.raw_output_dir,
                model=model,
                sleep_seconds=sleep_seconds,
                api_key=api_key,
            )
            extractor.process_pdf_paths(pdfs_to_extract)
            extractor.aggregate_outputs()
            extracted_pdfs = pdfs_to_extract

            if (
                build_releases
                and dataset == ACC_AHA_DATASET
                and dataset_paths.manual_gene_review_path is not None
                and dataset_paths.default_release_dir is not None
            ):
                build_release(
                    raw_output_dir=dataset_paths.raw_output_dir,
                    source_pdf_dir=dataset_paths.source_pdf_dir,
                    manual_gene_review_path=dataset_paths.manual_gene_review_path,
                    gene_reference_path=GENE_REFERENCE_PATH,
                    release_dir=dataset_paths.default_release_dir,
                )
                release_dir = dataset_paths.default_release_dir
                logger.info("Rebuilt ACC/AHA release at %s", release_dir)
        else:
            logger.info("No missing JSON outputs for %s; skipping extraction", dataset)

        sync_results[dataset] = DatasetSyncResult(
            scrape_result=scrape_result,
            extracted_pdfs=extracted_pdfs,
            release_dir=release_dir,
        )

    return sync_results


def pending_extraction_paths(scrape_result: ScrapeResult, dataset_paths) -> list[Path]:
    pending: list[Path] = []
    seen: set[Path] = set()
    tracked_paths = [*scrape_result.downloaded_paths, *scrape_result.existing_paths]
    for pdf_path in tracked_paths:
        if pdf_path in seen:
            continue
        seen.add(pdf_path)
        if pdf_requires_extraction(dataset_paths.raw_output_dir, pdf_path):
            pending.append(pdf_path)
    return pending


def pdf_requires_extraction(raw_output_dir: Path, pdf_path: Path) -> bool:
    pdf_output_dir = raw_output_dir / pdf_path.stem
    if not pdf_output_dir.exists():
        return True

    page_json_files = [path for path in pdf_output_dir.glob("*.json") if path.stem.isdigit()]
    if not page_json_files:
        return True

    aggregated_path = raw_output_dir / f"{pdf_path.stem}_aggregated.json"
    return not aggregated_path.exists()
