from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from hcg.paths import (
    ACC_AHA_DATASET,
    DEFAULT_RELEASE_DIR,
    GENE_REFERENCE_PATH,
    MANUAL_GENE_REVIEW_PATH,
    RAW_OUTPUT_DIR,
    SOURCE_PDF_DIR,
    SUPPORTED_DATASETS,
    get_dataset_paths,
)
from hcg.release_builder import build_release


DEFAULT_MODEL = "gpt-5-mini"


def require_api_key(api_key: str | None, *, command_name: str) -> str:
    if api_key:
        return api_key
    raise ValueError(
        f"OPENAI_API_KEY is required for `hcg {command_name}`. "
        "Set the environment variable or pass --api-key."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Heart Clinical Guideline extraction and release toolkit."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract",
        help="Convert guideline PDF pages into page-level JSON and aggregated outputs using OpenAI vision.",
    )
    extract_parser.add_argument(
        "--dataset",
        choices=SUPPORTED_DATASETS,
        default=ACC_AHA_DATASET,
        help="Dataset to extract when pdf/output directories are not provided.",
    )
    extract_parser.add_argument("--pdf-dir", default=None, help="Directory containing source PDFs.")
    extract_parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for page JSONs and aggregated outputs.",
    )
    extract_parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model to use.")
    extract_parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.0,
        help="Delay between page requests.",
    )
    extract_parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="OpenAI API key. Defaults to OPENAI_API_KEY.",
    )
    extract_parser.add_argument(
        "--rerun-error-pages",
        action="store_true",
        help="Reprocess only page JSON files whose content contains an error field.",
    )

    release_parser = subparsers.add_parser(
        "build-release",
        help="Build the ACC/AHA HeartBioPortal release from the raw extracted outputs.",
    )
    release_parser.add_argument(
        "--dataset",
        choices=[ACC_AHA_DATASET],
        default=ACC_AHA_DATASET,
        help="Release builder currently targets the ACC/AHA dataset.",
    )
    release_parser.add_argument("--raw-output-dir", default=str(RAW_OUTPUT_DIR))
    release_parser.add_argument("--source-pdf-dir", default=str(SOURCE_PDF_DIR))
    release_parser.add_argument("--manual-gene-review", default=str(MANUAL_GENE_REVIEW_PATH))
    release_parser.add_argument("--gene-reference", default=str(GENE_REFERENCE_PATH))
    release_parser.add_argument("--release-dir", default=str(DEFAULT_RELEASE_DIR))
    release_parser.add_argument(
        "--build-date",
        default=None,
        help="Optional ISO build date to embed in the release manifest.",
    )

    scrape_parser = subparsers.add_parser(
        "scrape",
        help="Check ACC/AHA and ESC guideline sites for missing PDFs and download them.",
    )
    scrape_parser.add_argument(
        "--datasets",
        nargs="+",
        default=["all"],
        help="Datasets to scrape: acc_aha, esc, or all.",
    )
    scrape_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="HTTP/browser timeout for scraping steps.",
    )
    scrape_parser.add_argument("--limit", type=int, default=None, help="Limit discovered documents per dataset.")
    scrape_parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Run ACC browser automation in headed mode instead of headless mode.",
    )
    scrape_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and compare PDFs without downloading anything.",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Run the scrapers and extract any newly downloaded PDFs into JSON outputs.",
    )
    sync_parser.add_argument(
        "--datasets",
        nargs="+",
        default=["all"],
        help="Datasets to sync: acc_aha, esc, or all.",
    )
    sync_parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model to use for new PDFs.")
    sync_parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=1.0,
        help="Delay between OpenAI page requests during extraction.",
    )
    sync_parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="OpenAI API key. Defaults to OPENAI_API_KEY.",
    )
    sync_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="HTTP/browser timeout for scraping steps.",
    )
    sync_parser.add_argument("--limit", type=int, default=None, help="Limit discovered documents per dataset.")
    sync_parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Run ACC browser automation in headed mode instead of headless mode.",
    )
    sync_parser.add_argument(
        "--no-release-build",
        action="store_true",
        help="Skip rebuilding the ACC/AHA release after new PDFs are processed.",
    )

    return parser


def run_extract(args: argparse.Namespace) -> int:
    from hcg.extractor import GuidelinePageExtractor

    dataset_paths = get_dataset_paths(args.dataset)
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir is not None else dataset_paths.source_pdf_dir
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")
    api_key = require_api_key(args.api_key, command_name="extract")

    extractor = GuidelinePageExtractor(
        pdf_dir=pdf_dir,
        output_dir=Path(args.output_dir) if args.output_dir is not None else dataset_paths.raw_output_dir,
        model=args.model,
        sleep_seconds=args.sleep_seconds,
        api_key=api_key,
    )
    extractor.process_all_pdfs(rerun_error_pages=args.rerun_error_pages)
    extractor.aggregate_outputs()
    return 0


def run_build_release(args: argparse.Namespace) -> int:
    build_release(
        raw_output_dir=Path(args.raw_output_dir),
        source_pdf_dir=Path(args.source_pdf_dir),
        manual_gene_review_path=Path(args.manual_gene_review),
        gene_reference_path=Path(args.gene_reference),
        release_dir=Path(args.release_dir),
        build_date=None if args.build_date is None else date.fromisoformat(args.build_date),
    )
    return 0


def run_scrape(args: argparse.Namespace) -> int:
    from hcg.scraper.service import run_scrapers

    results = run_scrapers(
        args.datasets,
        headless=not args.show_browser,
        timeout_seconds=args.timeout_seconds,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    for dataset, result in results.items():
        missing_count = sum(1 for record in result.records if record.status == "missing")
        print(
            f"{dataset}: discovered={result.discovered_count} "
            f"downloaded={len(result.downloaded_paths)} missing={missing_count} "
            f"blocked={len(result.blocked_records)} failed={len(result.failed_records)} "
            f"manifest={result.manifest_path}"
        )
    return 0


def run_sync(args: argparse.Namespace) -> int:
    from hcg.sync import sync_datasets

    api_key = require_api_key(args.api_key, command_name="sync")
    results = sync_datasets(
        args.datasets,
        model=args.model,
        sleep_seconds=args.sleep_seconds,
        api_key=api_key,
        headless=not args.show_browser,
        timeout_seconds=args.timeout_seconds,
        limit=args.limit,
        build_releases=not args.no_release_build,
    )
    for dataset, result in results.items():
        print(
            f"{dataset}: discovered={result.scrape_result.discovered_count} "
            f"downloaded={len(result.scrape_result.downloaded_paths)} "
            f"extracted={len(result.extracted_pdfs)} "
            f"blocked={len(result.scrape_result.blocked_records)} "
            f"failed={len(result.scrape_result.failed_records)}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "extract":
        return run_extract(args)
    if args.command == "build-release":
        return run_build_release(args)
    if args.command == "scrape":
        return run_scrape(args)
    if args.command == "sync":
        return run_sync(args)
    parser.error(f"Unknown command: {args.command}")
    return 2
