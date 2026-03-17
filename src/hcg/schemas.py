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
                "description": "Structured clinical content extracted from the page. Keys may vary by page content.",
                "additionalProperties": True,
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
                        "context": {"type": "string"},
                    },
                    "required": ["Gene", "Associated Conditions", "Occurrences", "context"],
                },
            },
        },
        "required": ["content", "genes"],
    },
}


EXTRACTION_INSTRUCTIONS = (
    "You are a medical information extraction expert. Extract clinical guideline "
    "information with special focus on human genes mentioned. Only include valid "
    "human genes when the page actually supports that interpretation. Exclude non-gene "
    "abbreviations, syndromes, procedures, cell types, biomarkers that are not genes, "
    "microorganisms, and generic placeholders like 'none' or 'unknown'."
)


EXTRACTION_PROMPT = (
    "Analyze this clinical guideline page image and extract the page content into "
    "structured JSON. Pay special attention to human genes actually mentioned on the page, "
    "their associated conditions, approximate occurrence count, and a short supporting context."
)
