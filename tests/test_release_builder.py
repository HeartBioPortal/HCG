from hcg.release_builder import normalize_gene_name, preferred_gene_order


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
