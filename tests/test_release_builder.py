import json

from hcg.release_builder import build_release, normalize_gene_name, preferred_gene_order


def test_normalize_gene_name_maps_known_aliases() -> None:
    valid_lookup = {"ERBB2": "ERBB2", "NKX2-5": "NKX2-5"}
    assert normalize_gene_name("HER2", valid_lookup) == ["ERBB2"]
    assert normalize_gene_name("NKX2.5", valid_lookup) == ["NKX2-5"]


def test_preferred_gene_order_uses_manual_gene_map() -> None:
    valid_lookup = {"ERBB2": "ERBB2"}
    manual_gene_map = {
        "Doc": [
            {"Gene": "HER2"},
            {"Gene": "HER2"},
        ]
    }
    order, title, source, unresolved = preferred_gene_order(
        slug="doc",
        title="Doc",
        manual_gene_map=manual_gene_map,
        raw_aggregated_genes={},
        valid_lookup=valid_lookup,
    )
    assert order == ["ERBB2"]
    assert title == "Doc"
    assert source == "manual_curation"
    assert unresolved == []


def test_build_release_accepts_flat_pdfs_and_missing_manual_review(tmp_path) -> None:
    raw_output_dir = tmp_path / "openai_outputs"
    source_pdf_dir = tmp_path / "source_pdfs"
    release_dir = tmp_path / "release"
    gene_reference_path = tmp_path / "genes.json"
    manual_gene_review_path = tmp_path / "missing_manual_gene_review.json"
    slug = "example-guideline"

    source_pdf_dir.mkdir()
    (source_pdf_dir / f"{slug}.pdf").write_bytes(b"%PDF-1.4")
    raw_output_dir.mkdir()
    gene_reference_path.write_text(json.dumps(["PCSK9"]), encoding="utf-8")
    (raw_output_dir / f"{slug}_aggregated.json").write_text(
        json.dumps(
            {
                "content": [
                    {
                        "content": {
                            "title": "Example Guideline",
                            "page_type": "recommendations",
                        },
                        "genes": [],
                    }
                ],
                "genes": [
                    {
                        "Gene": "PCSK9",
                        "Associated Conditions": ["hypercholesterolemia"],
                        "Occurrences": 1,
                        "context": ["PCSK9 inhibitor discussion"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release(
        raw_output_dir=raw_output_dir,
        source_pdf_dir=source_pdf_dir,
        manual_gene_review_path=manual_gene_review_path,
        gene_reference_path=gene_reference_path,
        release_dir=release_dir,
    )

    assert manifest["summary"]["document_count"] == 1
    assert manifest["summary"]["auto_gene_source_count"] == 1
    release_doc = json.loads((release_dir / "documents" / f"{slug}.json").read_text(encoding="utf-8"))
    assert release_doc["genes"][0]["Gene"] == "PCSK9"
