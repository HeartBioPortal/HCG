# HCG Provenance Schema

HCG extraction outputs should preserve source and transformation provenance for every guideline document, page, snippet, recommendation, and gene/biomedical entity link.

| Field | Description |
| --- | --- |
| `guideline_id` | Stable HCG guideline identifier. |
| `source_document` | Source PDF path, source URL, DOI, or document title. |
| `source_organization` | AHA, ACC, ESC, or collaborating organization. |
| `publication_year` | Guideline publication year. |
| `excerpt_or_snippet` | Source-grounded text excerpt when redistribution is allowed. |
| `recommendation_id` | Recommendation row or statement identifier. |
| `recommendation_text_if_allowed` | Recommendation text only when source terms allow redistribution. |
| `evidence_class` | Class/COR when available. |
| `evidence_level` | Level/LOE when available. |
| `condition` | Disease, phenotype, syndrome, or clinical topic. |
| `biomarker` | Biomarker or measurement concept. |
| `gene` | Gene symbol after conservative validation. |
| `variant` | Variant mention when explicitly present. |
| `drug_or_intervention` | Drug, device, procedure, or clinical intervention. |
| `relationship_type` | Extracted relationship label. |
| `extraction_method` | Parser, model, prompt, or release-builder stage. |
| `curator_or_pipeline_version` | HCG version, model version, prompt version, or curator label. |
| `source_license` | Source-document license or terms. |

Guideline evidence is context for HeartBioPortal users and should not be interpreted as medical advice or automated clinical recommendations.
