from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def is_project_root(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "src" / "hcg").is_dir()


def detect_project_root(
    *,
    module_file: Path | None = None,
    cwd: Path | None = None,
    env_root: str | None = None,
) -> Path:
    if env_root:
        return Path(env_root).expanduser().resolve()

    search_starts = []
    if cwd is not None:
        search_starts.append(cwd.resolve())
    if module_file is not None:
        search_starts.append(module_file.resolve())

    for start in search_starts:
        candidates = (start, *start.parents)
        for candidate in candidates:
            if is_project_root(candidate):
                return candidate

    if cwd is not None:
        return cwd.resolve()
    if module_file is not None:
        return module_file.resolve().parent
    return Path.cwd().resolve()


PROJECT_ROOT = detect_project_root(
    module_file=Path(__file__),
    cwd=Path.cwd(),
    env_root=os.environ.get("HCG_PROJECT_ROOT"),
)
DATA_DIR = PROJECT_ROOT / "data"
REFERENCE_DIR = DATA_DIR / "reference"
ACC_AHA_DIR = DATA_DIR / "acc_aha"
ESC_DIR = DATA_DIR / "esc"

SOURCE_PDF_DIR = ACC_AHA_DIR / "source_pdfs"
RAW_OUTPUT_DIR = ACC_AHA_DIR / "openai_outputs"
MANUAL_GENE_REVIEW_PATH = ACC_AHA_DIR / "manual_gene_review.json"
RELEASES_DIR = ACC_AHA_DIR / "releases"
DEFAULT_RELEASE_NAME = "heartbioportal_guideline_json_release_2026-03-16"
DEFAULT_RELEASE_DIR = RELEASES_DIR / DEFAULT_RELEASE_NAME
GENE_REFERENCE_PATH = REFERENCE_DIR / "gene_names.json"
DEFAULT_LOG_FILENAME = "pdf_processing.log"
SCRAPER_MANIFEST_FILENAME = "scraper_manifest.json"
SCRAPER_LOG_FILENAME = "scraper.log"

ACC_AHA_DATASET = "acc_aha"
ESC_DATASET = "esc"
SUPPORTED_DATASETS = (ACC_AHA_DATASET, ESC_DATASET)


@dataclass(frozen=True)
class DatasetPaths:
    name: str
    root_dir: Path
    source_pdf_dir: Path
    raw_output_dir: Path
    scraper_manifest_path: Path
    scraper_log_path: Path
    manual_gene_review_path: Path | None = None
    releases_dir: Path | None = None
    default_release_dir: Path | None = None

    def ensure_directories(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.source_pdf_dir.mkdir(parents=True, exist_ok=True)
        self.raw_output_dir.mkdir(parents=True, exist_ok=True)
        self.scraper_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.scraper_log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.releases_dir is not None:
            self.releases_dir.mkdir(parents=True, exist_ok=True)


DATASET_PATHS = {
    ACC_AHA_DATASET: DatasetPaths(
        name=ACC_AHA_DATASET,
        root_dir=ACC_AHA_DIR,
        source_pdf_dir=SOURCE_PDF_DIR,
        raw_output_dir=RAW_OUTPUT_DIR,
        scraper_manifest_path=ACC_AHA_DIR / SCRAPER_MANIFEST_FILENAME,
        scraper_log_path=ACC_AHA_DIR / SCRAPER_LOG_FILENAME,
        manual_gene_review_path=MANUAL_GENE_REVIEW_PATH,
        releases_dir=RELEASES_DIR,
        default_release_dir=DEFAULT_RELEASE_DIR,
    ),
    ESC_DATASET: DatasetPaths(
        name=ESC_DATASET,
        root_dir=ESC_DIR,
        source_pdf_dir=ESC_DIR / "source_pdfs",
        raw_output_dir=ESC_DIR / "openai_outputs",
        scraper_manifest_path=ESC_DIR / SCRAPER_MANIFEST_FILENAME,
        scraper_log_path=ESC_DIR / SCRAPER_LOG_FILENAME,
    ),
}


def get_dataset_paths(dataset: str) -> DatasetPaths:
    try:
        return DATASET_PATHS[dataset]
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_DATASETS)
        raise ValueError(f"Unsupported dataset '{dataset}'. Expected one of: {supported}") from exc


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
