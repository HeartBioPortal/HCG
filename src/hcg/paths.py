from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
REFERENCE_DIR = DATA_DIR / "reference"
ACC_AHA_DIR = DATA_DIR / "acc_aha"

SOURCE_PDF_DIR = ACC_AHA_DIR / "source_pdfs"
RAW_OUTPUT_DIR = ACC_AHA_DIR / "openai_outputs"
MANUAL_GENE_REVIEW_PATH = ACC_AHA_DIR / "manual_gene_review.json"
RELEASES_DIR = ACC_AHA_DIR / "releases"
DEFAULT_RELEASE_NAME = "heartbioportal_guideline_json_release_2026-03-16"
DEFAULT_RELEASE_DIR = RELEASES_DIR / DEFAULT_RELEASE_NAME
GENE_REFERENCE_PATH = REFERENCE_DIR / "gene_names.json"
DEFAULT_LOG_FILENAME = "pdf_processing.log"
