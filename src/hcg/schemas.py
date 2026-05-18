from __future__ import annotations


RESPONSE_SCHEMA = {
    "name": "guideline_page_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "content": {
                "type": "object",
                "description": "Structured clinical guideline content extracted from one page image.",
                "additionalProperties": False,
                "properties": {
                    "page_type": {
                        "type": "string",
                        "description": "One of title, table_of_contents, recommendations, narrative, figure_or_algorithm, references, appendix, mixed, blank_or_administrative.",
                    },
                    "title": {"type": "string"},
                    "section_headings": {"type": "array", "items": {"type": "string"}},
                    "narrative_summary": {
                        "type": "string",
                        "description": "Concise summary of clinically meaningful prose on the page; do not invent absent content.",
                    },
                    "recommendation_tables": {
                        "type": "array",
                        "description": "Recommendation tables or boxes visible on the page, preserving COR/Class and LOE/Level values.",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string"},
                                "rows": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "recommendation": {"type": "string"},
                                            "class_of_recommendation": {"type": "string"},
                                            "level_of_evidence": {"type": "string"},
                                            "supporting_text": {"type": "string"},
                                            "row_continues_from_previous_page": {"type": "boolean"},
                                            "row_continues_to_next_page": {"type": "boolean"},
                                        },
                                        "required": [
                                            "recommendation",
                                            "class_of_recommendation",
                                            "level_of_evidence",
                                            "supporting_text",
                                            "row_continues_from_previous_page",
                                            "row_continues_to_next_page",
                                        ],
                                    },
                                },
                            },
                            "required": ["title", "rows"],
                        },
                    },
                    "figures_tables_algorithms": {
                        "type": "array",
                        "description": "Non-recommendation tables, figures, flowcharts, algorithms, and boxes.",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "label": {"type": "string"},
                                "kind": {"type": "string"},
                                "title": {"type": "string"},
                                "summary": {"type": "string"},
                                "continuation_status": {
                                    "type": "string",
                                    "description": "complete, starts_before_page, continues_after_page, or spans_previous_and_next.",
                                },
                            },
                            "required": ["label", "kind", "title", "summary", "continuation_status"],
                        },
                    },
                    "continuity": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "starts_mid_sentence_or_table": {"type": "boolean"},
                            "ends_mid_sentence_or_table": {"type": "boolean"},
                            "requires_previous_page": {"type": "boolean"},
                            "requires_next_page": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "starts_mid_sentence_or_table",
                            "ends_mid_sentence_or_table",
                            "requires_previous_page",
                            "requires_next_page",
                            "reason",
                        ],
                    },
                    "extraction_warnings": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "page_type",
                    "title",
                    "section_headings",
                    "narrative_summary",
                    "recommendation_tables",
                    "figures_tables_algorithms",
                    "continuity",
                    "extraction_warnings",
                ],
            },
            "genes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "Gene": {"type": "string"},
                        "Associated Conditions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "Occurrences": {"type": "integer"},
                        "context": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "evidence_text": {"type": "string"},
                        "confidence": {"type": "string"},
                        "validation_note": {"type": "string"},
                    },
                    "required": [
                        "Gene",
                        "Associated Conditions",
                        "Occurrences",
                        "context",
                        "evidence_text",
                        "confidence",
                        "validation_note",
                    ],
                },
            },
        },
        "required": ["content", "genes"],
    },
}


EXTRACTION_INSTRUCTIONS = """
You are extracting cardiovascular guideline pages from page images, not from plain text.
The page may contain two-column prose, recommendation boxes, colored Class/COR and Level/LOE cells,
tables, algorithms, legends, footnotes, appendices, or content that continues across pages.

Core rules:
- Preserve recommendation tables as rows. For every visible recommendation row, capture the
  recommendation text plus the visible Class/COR and Level/LOE values. If Class/COR or Level/LOE is
  not visible on this page, leave the field empty and explain in extraction_warnings.
- Detect page-boundary continuity. Flag when the page starts or ends in the middle of a sentence,
  paragraph, table, recommendation row, figure, or algorithm.
- Do not collapse structured tables into vague prose summaries. Summaries are allowed, but the row
  data must remain structured.
- Do not infer missing recommendations, classes, levels, genes, or titles from medical knowledge.
  Extract only what the page image supports.

Gene rules:
- Include a gene only when the page visibly supports a human gene interpretation, such as a mutation,
  variant, genotype, familial/genetic testing context, or a known gene symbol explicitly presented as a
  gene. A bare all-caps clinical abbreviation is not enough.
- Exclude medical abbreviations, diseases, procedures, trials, societies, risk scores, proteins or
  biomarkers when they are not explicitly used as genes, microorganisms, drug names, device names,
  headings, and placeholders.
- If a token could be both a gene and a clinical abbreviation, include it only when nearby wording
  makes the gene meaning explicit. Otherwise omit it and add an extraction warning.
- For each included gene, provide the exact visible evidence_text and a validation_note explaining why
  it is a gene mention.
""".strip()


EXTRACTION_PROMPT = """
Analyze this single clinical guideline page image and return valid JSON matching the schema.
Treat the image layout as important evidence. Extract visible recommendation tables/boxes, figures,
section headings, clinically meaningful prose, page-continuity flags, and strictly supported human
gene mentions. If the page is mostly table of contents, references, author lists, disclosures, or
administrative material, identify that page_type and avoid inventing clinical recommendations.
""".strip()
