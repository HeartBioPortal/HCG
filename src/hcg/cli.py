from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from hcg.paths import (
    DEFAULT_RELEASE_DIR,
    GENE_REFERENCE_PATH,
    MANUAL_GENE_REVIEW_PATH,
    RAW_OUTPUT_DIR,
    SOURCE_PDF_DIR,
)
from hcg.release_builder import build_release


DEFAULT_MODEL = "gpt-5-mini"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Heart Clinical Guideline extraction and release toolkit."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract",
        help="Convert guideline PDF pages into page-level JSON and aggregated outputs using OpenAI vision.",
    )
    extract_parser.add_argument("--pdf-dir", default=str(SOURCE_PDF_DIR), help="Directory containing source PDFs.")
    extract_parser.add_argument(
        "--output-dir",
        default=str(RAW_OUTPUT_DIR),
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
        "--organization",
        default=os.environ.get("ORGANIZATION_ID") or os.environ.get("OPENAI_ORG_ID"),
        help="OpenAI organization ID. Defaults to ORGANIZATION_ID or OPENAI_ORG_ID.",
    )
    extract_parser.add_argument(
        "--project",
        default=os.environ.get("PROJECT_ID") or os.environ.get("OPENAI_PROJECT_ID"),
        help="OpenAI project ID. Defaults to PROJECT_ID or OPENAI_PROJECT_ID.",
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

    return parser


def run_extract(args: argparse.Namespace) -> int:
    from hcg.extractor import GuidelinePageExtractor

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")
    if not args.api_key:
        raise ValueError("OPENAI_API_KEY is required. Pass --api-key or set the environment variable.")

    extractor = GuidelinePageExtractor(
        pdf_dir=pdf_dir,
        output_dir=Path(args.output_dir),
        model=args.model,
        sleep_seconds=args.sleep_seconds,
        api_key=args.api_key,
        organization=args.organization,
        project=args.project,
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "extract":
        return run_extract(args)
    if args.command == "build-release":
        return run_build_release(args)
    parser.error(f"Unknown command: {args.command}")
    return 2
