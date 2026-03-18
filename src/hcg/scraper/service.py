from __future__ import annotations

from hcg.paths import ACC_AHA_DATASET, ESC_DATASET, SUPPORTED_DATASETS, get_dataset_paths
from hcg.scraper.acc import AccGuidelineScraper
from hcg.scraper.esc import EscGuidelineScraper
from hcg.scraper.models import ScrapeResult


def normalize_datasets(dataset_args: list[str] | None) -> list[str]:
    if not dataset_args:
        return [ESC_DATASET, ACC_AHA_DATASET]
    if "all" in dataset_args:
        return [ESC_DATASET, ACC_AHA_DATASET]

    unknown = sorted(set(dataset_args) - set(SUPPORTED_DATASETS))
    if unknown:
        supported = ", ".join((*SUPPORTED_DATASETS, "all"))
        unknown_text = ", ".join(unknown)
        raise ValueError(f"Unsupported dataset value(s): {unknown_text}. Expected one of: {supported}")
    return list(dict.fromkeys(dataset_args))


def run_scrapers(
    datasets: list[str] | None,
    *,
    headless: bool = True,
    timeout_seconds: float = 60.0,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, ScrapeResult]:
    results: dict[str, ScrapeResult] = {}
    for dataset in normalize_datasets(datasets):
        paths = get_dataset_paths(dataset)
        if dataset == ACC_AHA_DATASET:
            scraper = AccGuidelineScraper(
                paths,
                headless=headless,
                timeout_seconds=timeout_seconds,
                limit=limit,
                dry_run=dry_run,
            )
        elif dataset == ESC_DATASET:
            scraper = EscGuidelineScraper(
                paths,
                headless=headless,
                timeout_seconds=timeout_seconds,
                limit=limit,
                dry_run=dry_run,
            )
        else:  # pragma: no cover - protected by normalize_datasets
            raise ValueError(f"Unsupported dataset: {dataset}")

        results[dataset] = scraper.scrape()
    return results
