from __future__ import annotations

import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_NEW_CORPUS_DIRS = (
    ("esc_new", Path("data/ESC-NEW")),
    ("acc_aha_new", Path("data/AHA-ACC-NEW")),
)


def slugify_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "document"


def pdf_page_count(pdf_path: Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        return None

    proc = subprocess.run(
        [pdfinfo, str(pdf_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None

    for line in proc.stdout.splitlines():
        if line.startswith("Pages:"):
            _, value = line.split(":", 1)
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def unique_document_dir(dataset_dir: Path, slug: str) -> Path:
    candidate = dataset_dir / slug
    if not candidate.exists():
        return candidate

    index = 2
    while True:
        candidate = dataset_dir / f"{slug}-{index}"
        if not candidate.exists():
            return candidate
        index += 1


def convert_pdf_pages_with_pdftoppm(
    pdf_path: Path,
    pages_dir: Path,
    *,
    dpi: int,
    image_format: str,
) -> list[dict[str, Any]]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError(
            "pdftoppm was not found. Install Poppler first, then rerun image preparation."
        )

    suffix = image_format.lower()
    if suffix not in {"png", "jpeg", "jpg"}:
        raise ValueError("image_format must be png, jpeg, or jpg")
    pdftoppm_format = "jpeg" if suffix in {"jpeg", "jpg"} else "png"
    suffix = "jpg" if suffix in {"jpeg", "jpg"} else "png"

    prefix = pages_dir / "page"
    cmd = [pdftoppm, f"-{pdftoppm_format}", "-r", str(dpi), str(pdf_path), str(prefix)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"pdftoppm failed for {pdf_path}")

    page_records: list[dict[str, Any]] = []
    rendered = sorted(pages_dir.glob(f"page-*.{suffix}"))
    for index, old_path in enumerate(rendered, start=1):
        page_path = pages_dir / f"page_{index:04d}.{suffix}"
        old_path.rename(page_path)
        page_records.append(
            {
                "page_number": index,
                "image_path": str(page_path),
                "file_name": page_path.name,
            }
        )
    return page_records


@dataclass(frozen=True)
class PreparedPdf:
    dataset: str
    pdf_path: Path
    document_dir: Path
    page_count: int
    manifest_path: Path


class GuidelineImagePreparer:
    def __init__(
        self,
        output_dir: Path,
        *,
        dpi: int = 180,
        image_format: str = "png",
        overwrite: bool = False,
        jobs: int = 1,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.dpi = dpi
        self.image_format = image_format
        self.overwrite = overwrite
        self.jobs = max(1, jobs)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def prepare_pdf(self, dataset: str, pdf_path: Path) -> PreparedPdf:
        dataset_dir = self.output_dir / dataset
        dataset_dir.mkdir(parents=True, exist_ok=True)

        slug = slugify_filename(pdf_path.stem)
        document_dir = dataset_dir / slug if self.overwrite else unique_document_dir(dataset_dir, slug)
        pages_dir = document_dir / "pages"

        if document_dir.exists() and self.overwrite:
            shutil.rmtree(document_dir)
        pages_dir.mkdir(parents=True, exist_ok=True)

        expected_page_count = pdf_page_count(pdf_path)
        pages = convert_pdf_pages_with_pdftoppm(
            pdf_path,
            pages_dir,
            dpi=self.dpi,
            image_format=self.image_format,
        )

        manifest = {
            "dataset": dataset,
            "document_slug": document_dir.name,
            "source_pdf_path": str(pdf_path),
            "source_pdf_name": pdf_path.name,
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "render": {
                "method": "pdftoppm",
                "dpi": self.dpi,
                "image_format": "jpg" if self.image_format in {"jpeg", "jpg"} else "png",
            },
            "page_count": len(pages),
            "expected_page_count": expected_page_count,
            "pages": pages,
            "next_step": {
                "status": "ready_for_openai_extraction",
                "notes": [
                    "Send each page image with its neighboring page metadata when available.",
                    "Preserve this per-document directory when writing page JSON outputs.",
                ],
            },
        }
        manifest_path = document_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return PreparedPdf(
            dataset=dataset,
            pdf_path=pdf_path,
            document_dir=document_dir,
            page_count=len(pages),
            manifest_path=manifest_path,
        )

    def prepare_pdf_dirs(self, pdf_dirs: Sequence[tuple[str, Path]]) -> dict[str, Any]:
        documents: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        tasks = [
            (dataset, pdf_path)
            for dataset, pdf_dir in pdf_dirs
            for pdf_path in sorted(Path(pdf_dir).glob("*.pdf"), key=lambda path: path.name.lower())
        ]

        if self.jobs == 1:
            for dataset, pdf_path in tasks:
                try:
                    prepared = self.prepare_pdf(dataset, pdf_path)
                except Exception as exc:
                    failures.append(
                        {
                            "dataset": dataset,
                            "source_pdf_path": str(pdf_path),
                            "error": str(exc),
                        }
                    )
                    continue

                documents.append(
                    {
                        "dataset": prepared.dataset,
                        "source_pdf_path": str(prepared.pdf_path),
                        "document_dir": str(prepared.document_dir),
                        "page_count": prepared.page_count,
                        "manifest_path": str(prepared.manifest_path),
                    }
                )
        else:
            with ThreadPoolExecutor(max_workers=self.jobs) as executor:
                future_map = {
                    executor.submit(self.prepare_pdf, dataset, pdf_path): (dataset, pdf_path)
                    for dataset, pdf_path in tasks
                }
                for future in as_completed(future_map):
                    dataset, pdf_path = future_map[future]
                    try:
                        prepared = future.result()
                    except Exception as exc:
                        failures.append(
                            {
                                "dataset": dataset,
                                "source_pdf_path": str(pdf_path),
                                "error": str(exc),
                            }
                        )
                        continue

                    documents.append(
                        {
                            "dataset": prepared.dataset,
                            "source_pdf_path": str(prepared.pdf_path),
                            "document_dir": str(prepared.document_dir),
                            "page_count": prepared.page_count,
                            "manifest_path": str(prepared.manifest_path),
                        }
                    )

        documents.sort(key=lambda item: (item["dataset"], item["source_pdf_path"]))
        failures.sort(key=lambda item: (item["dataset"], item["source_pdf_path"]))
        manifest = {
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(self.output_dir),
            "document_count": len(documents),
            "page_count": sum(document["page_count"] for document in documents),
            "failed_document_count": len(failures),
            "documents": documents,
            "failures": failures,
        }
        (self.output_dir / "corpus_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return manifest


def parse_pdf_dir_args(values: Iterable[str] | None) -> list[tuple[str, Path]]:
    if not values:
        return [(dataset, Path(path)) for dataset, path in DEFAULT_NEW_CORPUS_DIRS]

    parsed: list[tuple[str, Path]] = []
    for value in values:
        if "=" in value:
            dataset, path = value.split("=", 1)
            parsed.append((slugify_filename(dataset), Path(path)))
        else:
            path = Path(value)
            parsed.append((slugify_filename(path.name), path))
    return parsed
