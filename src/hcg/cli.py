from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path

from hcg.paths import (
    ACC_AHA_DATASET,
    DEFAULT_LOG_FILENAME,
    DEFAULT_RELEASE_DIR,
    GENE_REFERENCE_PATH,
    MANUAL_GENE_REVIEW_PATH,
    RAW_OUTPUT_DIR,
    SOURCE_PDF_DIR,
    SUPPORTED_DATASETS,
    get_dataset_paths,
)
from hcg.release_builder import build_release
from hcg.extractor import DEFAULT_MAX_OUTPUT_TOKENS


DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_VISION_PROBE_MODELS = [
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4o",
    "o4-mini",
    "gpt-5-mini",
    "gpt-5.4-mini",
]


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
    extract_parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help="Maximum model output tokens per page.",
    )

    extract_page_parser = subparsers.add_parser(
        "extract-page",
        help="Run OpenAI vision extraction for one page from one guideline PDF.",
    )
    extract_page_parser.add_argument("--pdf", required=True, help="Path to the source guideline PDF.")
    extract_page_parser.add_argument("--page", required=True, type=int, help="1-based page number to extract.")
    extract_page_parser.add_argument(
        "--output-dir",
        default="data/test_openai_outputs",
        help="Directory for the single-page test JSON and log file.",
    )
    extract_page_parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model to use.")
    extract_page_parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Delay after the single page request.",
    )
    extract_page_parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="OpenAI API key. Defaults to OPENAI_API_KEY.",
    )
    extract_page_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing JSON file for this PDF/page.",
    )
    extract_page_parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help="Maximum model output tokens for the page.",
    )

    probe_models_parser = subparsers.add_parser(
        "probe-models",
        help="Test candidate OpenAI vision models against one guideline page.",
    )
    probe_models_parser.add_argument("--pdf", required=True, help="Path to the source guideline PDF.")
    probe_models_parser.add_argument("--page", required=True, type=int, help="1-based page number to extract.")
    probe_models_parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_VISION_PROBE_MODELS,
        help="Model IDs to test. Defaults to a small vision-capable candidate set.",
    )
    probe_models_parser.add_argument(
        "--output-dir",
        default="data/model_probe_outputs",
        help="Directory for per-model page JSONs and log files.",
    )
    probe_models_parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Delay after each model request.",
    )
    probe_models_parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
        help="OpenAI API key. Defaults to OPENAI_API_KEY.",
    )
    probe_models_parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help="Maximum model output tokens for each model/page test.",
    )

    prepare_images_parser = subparsers.add_parser(
        "prepare-images",
        help="Convert local guideline PDFs into organized page images without calling the OpenAI API.",
    )
    prepare_images_parser.add_argument(
        "--pdf-dir",
        action="append",
        default=None,
        help=(
            "PDF directory to render. Use dataset=/path/to/pdfs to choose the output dataset name. "
            "May be passed more than once. Defaults to data/ESC-NEW and data/AHA-ACC-NEW."
        ),
    )
    prepare_images_parser.add_argument(
        "--output-dir",
        default="data/prepared_images/rerun_2026_05_18_api_ready",
        help="Directory that will receive per-document page images and manifests.",
    )
    prepare_images_parser.add_argument("--dpi", type=int, default=180, help="PDF render DPI.")
    prepare_images_parser.add_argument(
        "--image-format",
        choices=["png", "jpg", "jpeg"],
        default="png",
        help="Image format for rendered pages.",
    )
    prepare_images_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing prepared-image document directories with the same slug.",
    )
    prepare_images_parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of PDFs to render in parallel.",
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
    sync_parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help="Maximum model output tokens per extracted page.",
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
        max_output_tokens=args.max_output_tokens,
    )
    extractor.process_all_pdfs(rerun_error_pages=args.rerun_error_pages)
    extractor.aggregate_outputs()
    return 0


def run_extract_page(args: argparse.Namespace) -> int:
    from hcg.extractor import GuidelinePageExtractor

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if args.page < 1:
        raise ValueError("--page must be a 1-based page number.")

    output_dir = Path(args.output_dir)
    api_key = require_api_key(args.api_key, command_name="extract-page")
    extractor = GuidelinePageExtractor(
        pdf_dir=pdf_path.parent,
        output_dir=output_dir,
        model=args.model,
        sleep_seconds=args.sleep_seconds,
        api_key=api_key,
        max_output_tokens=args.max_output_tokens,
    )
    output_paths = extractor.process_single_pdf(
        pdf_path,
        selected_pages=[args.page],
        overwrite_existing=args.overwrite,
    )
    page_output_path = output_dir / pdf_path.stem / f"{args.page}.json"
    if page_output_path not in output_paths:
        raise RuntimeError(f"Expected page JSON was not created: {page_output_path}")

    print(
        f"extract_page: pdf={pdf_path} page={args.page} "
        f"output={page_output_path} log={output_dir / DEFAULT_LOG_FILENAME}"
    )
    return 0


def _safe_model_dir_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("._") or "model"


def _probe_status(page_output_path: Path) -> tuple[str, str]:
    try:
        payload = json.loads(page_output_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ("FAIL", f"Could not read output JSON: {exc}")

    content = payload.get("content") if isinstance(payload, dict) else None
    if isinstance(content, dict) and content.get("error"):
        return ("FAIL", str(content["error"]).replace("\n", " ")[:220])

    genes = payload.get("genes") if isinstance(payload, dict) else None
    if isinstance(content, dict) and isinstance(genes, list):
        page_type = content.get("page_type") or "unknown"
        warnings = content.get("extraction_warnings") or []
        return ("OK", f"page_type={page_type}; genes={len(genes)}; warnings={len(warnings)}")

    return ("FAIL", "Output did not match expected top-level content/genes shape.")


def run_probe_models(args: argparse.Namespace) -> int:
    from hcg.extractor import GuidelinePageExtractor

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if args.page < 1:
        raise ValueError("--page must be a 1-based page number.")

    api_key = require_api_key(args.api_key, command_name="probe-models")
    output_root = Path(args.output_dir)
    rows: list[tuple[str, str, Path, str]] = []

    for model in args.models:
        model_output_dir = output_root / _safe_model_dir_name(model)
        extractor = GuidelinePageExtractor(
            pdf_dir=pdf_path.parent,
            output_dir=model_output_dir,
            model=model,
            sleep_seconds=args.sleep_seconds,
            api_key=api_key,
            max_output_tokens=args.max_output_tokens,
        )
        extractor.process_single_pdf(
            pdf_path,
            selected_pages=[args.page],
            overwrite_existing=True,
        )
        page_output_path = model_output_dir / pdf_path.stem / f"{args.page}.json"
        status, note = _probe_status(page_output_path)
        rows.append((model, status, page_output_path, note))

    print("model_probe_results:")
    print("MODEL\tSTATUS\tOUTPUT\tNOTE")
    for model, status, page_output_path, note in rows:
        print(f"{model}\t{status}\t{page_output_path}\t{note}")

    return 0 if any(status == "OK" for _, status, _, _ in rows) else 1


def run_prepare_images(args: argparse.Namespace) -> int:
    from hcg.image_preparer import GuidelineImagePreparer, parse_pdf_dir_args

    pdf_dirs = parse_pdf_dir_args(args.pdf_dir)
    for dataset, pdf_dir in pdf_dirs:
        if not pdf_dir.exists():
            raise FileNotFoundError(f"PDF directory not found for {dataset}: {pdf_dir}")

    preparer = GuidelineImagePreparer(
        output_dir=Path(args.output_dir),
        dpi=args.dpi,
        image_format=args.image_format,
        overwrite=args.overwrite,
        jobs=args.jobs,
    )
    manifest = preparer.prepare_pdf_dirs(pdf_dirs)
    print(
        f"prepared_images: documents={manifest['document_count']} "
        f"pages={manifest['page_count']} failures={manifest['failed_document_count']} "
        f"manifest={Path(args.output_dir) / 'corpus_manifest.json'}"
    )
    return 1 if manifest["failed_document_count"] else 0


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
        max_output_tokens=args.max_output_tokens,
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
    if args.command == "extract-page":
        return run_extract_page(args)
    if args.command == "probe-models":
        return run_probe_models(args)
    if args.command == "prepare-images":
        return run_prepare_images(args)
    if args.command == "build-release":
        return run_build_release(args)
    if args.command == "scrape":
        return run_scrape(args)
    if args.command == "sync":
        return run_sync(args)
    parser.error(f"Unknown command: {args.command}")
    return 2
