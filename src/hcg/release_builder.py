from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from hcg.common import load_json, write_json
from hcg.paths import PROJECT_ROOT


MANUAL_TITLE_OVERRIDES = {
    "stout-et-al-2018-2018-aha-acc-guideline-for-the-management-of-adults-with-congenital-heart-disease":
        "2018 AHA/ACC Guideline for the Management of Adults With Congenital Heart Disease",
}

GENE_ALIASES = {
    "ACTC": ["ACTC1"],
    "APOB-100": ["APOB"],
    "APOB100": ["APOB"],
    "APOE2": ["APOE"],
    "CYP3A4/5": ["CYP3A4", "CYP3A5"],
    "HER2": ["ERBB2"],
    "JNK2": ["MAPK9"],
    "LP(A)": ["LPA"],
    "ND4": ["MT-ND4"],
    "NKX2.5": ["NKX2-5"],
    "NT-PROBNP": ["NPPB"],
    "OCT2": ["SLC22A2"],
    "P2Y12": ["P2RY12"],
    "TGFΒ2": ["TGFB2"],
    "TGFΒ3": ["TGFB3"],
    "TGFRB1": ["TGFBR1"],
    "TGFRB2": ["TGFBR2"],
}

EXPLICIT_ALLOWED_GENES = {
    "MT-TL1",
    "MT-ND4",
}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def canonical_gene_map(gene_reference_path: Path) -> dict[str, str]:
    valid = load_json(gene_reference_path)
    return {gene.upper(): gene for gene in valid}


def normalize_gene_name(raw_name: str | None, valid_lookup: dict[str, str]) -> list[str]:
    if not raw_name:
        return []

    cleaned = raw_name.strip()
    cleaned = cleaned.replace("β", "B").replace("Β", "B").replace("ß", "B")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*\((.*?)\)\s*$", "", cleaned).strip()
    upper = cleaned.upper()

    if upper in GENE_ALIASES:
        return GENE_ALIASES[upper]
    if cleaned in GENE_ALIASES:
        return GENE_ALIASES[cleaned]
    if upper in valid_lookup:
        return [valid_lookup[upper]]
    if upper in EXPLICIT_ALLOWED_GENES:
        return [upper]
    return []


def extract_title(aggregated_doc: dict[str, Any]) -> str | None:
    for item in aggregated_doc.get("content", []):
        content = item.get("content") if isinstance(item, dict) else None
        if isinstance(content, dict):
            title = content.get("Title") or content.get("title")
            if title:
                return title
    return None


def source_pdf_for_slug(slug: str, source_pdf_dir: Path) -> Path:
    pdf_dir = source_pdf_dir / slug
    if pdf_dir.exists():
        pdfs = sorted(pdf_dir.glob("*.pdf"))
        if pdfs:
            return pdfs[0]

    extra_pdf = source_pdf_dir / "extra" / f"{slug}.pdf"
    if extra_pdf.exists():
        return extra_pdf

    raise FileNotFoundError(f"Could not locate source PDF for {slug}")


def recover_error_pages(content_items: list[dict[str, Any]], pdf_path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    recovered_pages: list[int] = []
    rebuilt_content: list[dict[str, Any]] = []

    for page_number, item in enumerate(content_items, start=1):
        page_copy = item
        content = item.get("content") if isinstance(item, dict) else None
        if isinstance(content, dict) and "error" in content:
            proc = subprocess.run(
                [
                    "pdftotext",
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-layout",
                    "-nopgbrk",
                    str(pdf_path),
                    "-",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            fallback_text = proc.stdout.strip()
            page_copy = dict(item)
            page_copy["content"] = {
                **content,
                "fallback_text": fallback_text,
            }
            page_copy["_recovery"] = {
                "page_number": page_number,
                "method": "pdftotext",
                "status": "fallback_text_only",
            }
            recovered_pages.append(page_number)
        rebuilt_content.append(page_copy)

    return rebuilt_content, recovered_pages


def aggregate_raw_gene_entries(
    raw_genes: list[dict[str, Any]],
    valid_lookup: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    aggregated: dict[str, dict[str, Any]] = {}
    unresolved: list[str] = []

    for gene_entry in raw_genes:
        raw_name = gene_entry.get("Gene")
        canonical_names = normalize_gene_name(raw_name, valid_lookup)
        if not canonical_names:
            unresolved.append(raw_name)
            continue

        for canonical_name in canonical_names:
            if canonical_name not in aggregated:
                aggregated[canonical_name] = {
                    "Gene": canonical_name,
                    "Associated Conditions": [],
                    "Occurrences": 0,
                    "context": [],
                }

            target = aggregated[canonical_name]
            target["Occurrences"] += gene_entry.get("Occurrences", 1)

            for condition in gene_entry.get("Associated Conditions", []):
                if condition not in target["Associated Conditions"]:
                    target["Associated Conditions"].append(condition)

            context_values = gene_entry.get("context", [])
            if isinstance(context_values, str):
                context_values = [context_values]
            for context in context_values:
                if context and context not in target["context"]:
                    target["context"].append(context)

    return aggregated, sorted({name for name in unresolved if name})


def preferred_gene_order(
    slug: str,
    title: str | None,
    manual_gene_map: dict[str, list[dict[str, Any]]],
    raw_aggregated_genes: dict[str, dict[str, Any]],
    valid_lookup: dict[str, str],
) -> tuple[list[str], str | None, str, list[str]]:
    manual_title = MANUAL_TITLE_OVERRIDES.get(slug, title)
    if manual_title in manual_gene_map:
        manual_genes = manual_gene_map[manual_title]
        ordered: list[str] = []
        seen: set[str] = set()
        unresolved: list[str] = []

        for gene_entry in manual_genes:
            raw_name = gene_entry.get("Gene")
            canonical_names = normalize_gene_name(raw_name, valid_lookup)
            if not canonical_names:
                unresolved.append(raw_name)
                continue
            for canonical_name in canonical_names:
                if canonical_name not in seen:
                    ordered.append(canonical_name)
                    seen.add(canonical_name)

        return ordered, manual_title, "manual_curation", unresolved

    return list(raw_aggregated_genes.keys()), title, "auto_normalized_from_raw", []


def build_release(
    raw_output_dir: Path,
    source_pdf_dir: Path,
    manual_gene_review_path: Path,
    gene_reference_path: Path,
    release_dir: Path,
    build_date: date | None = None,
) -> dict[str, Any]:
    valid_lookup = canonical_gene_map(gene_reference_path)
    manual_gene_map = load_json(manual_gene_review_path)
    aggregated_files = sorted(raw_output_dir.glob("*_aggregated.json"))
    release_docs_dir = release_dir / "documents"
    manifest_path = release_dir / "manifest.json"
    effective_build_date = (build_date or date.today()).isoformat()

    manifest: dict[str, Any] = {
        "build_date": effective_build_date,
        "source_dir": display_path(raw_output_dir),
        "source_pdf_dir": display_path(source_pdf_dir),
        "documents_dir": display_path(release_docs_dir),
        "documents": [],
    }

    for aggregated_file in aggregated_files:
        slug = aggregated_file.stem.replace("_aggregated", "")
        raw_doc = load_json(aggregated_file)
        title = extract_title(raw_doc)
        pdf_path = source_pdf_for_slug(slug, source_pdf_dir)
        rebuilt_content, recovered_pages = recover_error_pages(raw_doc.get("content", []), pdf_path)
        raw_gene_index, unresolved_raw = aggregate_raw_gene_entries(raw_doc.get("genes", []), valid_lookup)
        gene_order, manual_title_used, gene_source, unresolved_manual = preferred_gene_order(
            slug,
            title,
            manual_gene_map,
            raw_gene_index,
            valid_lookup,
        )

        final_genes: list[dict[str, Any]] = []
        for gene_name in gene_order:
            gene_payload = raw_gene_index.get(
                gene_name,
                {
                    "Gene": gene_name,
                    "Associated Conditions": [],
                    "Occurrences": 1,
                    "context": [],
                },
            )
            final_genes.append(gene_payload)

        release_doc = {
            "content": rebuilt_content,
            "genes": final_genes,
        }
        write_json(release_docs_dir / f"{slug}.json", release_doc)
        manifest["documents"].append(
            {
                "slug": slug,
                "title": manual_title_used,
                "page_count": len(raw_doc.get("content", [])),
                "recovered_error_pages": recovered_pages,
                "raw_gene_count": len(raw_doc.get("genes", [])),
                "final_gene_count": len(final_genes),
                "gene_source": gene_source,
                "manual_genes_unresolved": unresolved_manual,
                "raw_genes_unresolved": unresolved_raw,
            }
        )

    manifest["summary"] = {
        "document_count": len(manifest["documents"]),
        "recovered_error_page_count": sum(
            len(document["recovered_error_pages"]) for document in manifest["documents"]
        ),
        "manual_gene_source_count": sum(
            document["gene_source"] == "manual_curation" for document in manifest["documents"]
        ),
        "auto_gene_source_count": sum(
            document["gene_source"] == "auto_normalized_from_raw" for document in manifest["documents"]
        ),
    }
    write_json(manifest_path, manifest)
    return manifest
