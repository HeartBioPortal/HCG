# HCG

HCG is a standalone HeartBioPortal module for converting cardiovascular guideline PDFs into structured JSON and release-ready document bundles.

This repository is intentionally scoped to the ACC/AHA workflow that produced the current HeartBioPortal guideline JSON set. It includes the exact source PDFs, the raw OpenAI page outputs, the manual gene review map, and the current release artifact.

## Repository layout

- `src/hcg`
  Python package with the OpenAI extractor, release builder, schemas, and CLI.
- `data/acc_aha/source_pdfs`
  ACC/AHA guideline PDFs and methodology PDFs used for the current extraction run.
- `data/acc_aha/openai_outputs`
  Raw page-level JSON and aggregated document JSON from the current OpenAI run.
- `data/acc_aha/manual_gene_review.json`
  Human-reviewed title-to-gene mappings used by the release builder.
- `data/acc_aha/releases/heartbioportal_guideline_json_release_2026-03-16`
  Current HeartBioPortal handoff artifact.
- `data/reference/gene_names.json`
  Canonical gene reference used during normalization.
- `docs/project_audit.md`
  Current project audit and remaining caveats.

## Current status

The ACC/AHA raw page set is complete and currently has `0` remaining page-level extraction errors. The current release contains `37` document JSON files. The remaining caveat is curation quality for the `16` auto-normalized documents that do not yet have full manual review.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

`pdf2image` requires Poppler on the host system.

- macOS: `brew install poppler`
- Ubuntu/Debian: `sudo apt-get install poppler-utils`

## CLI usage

Extract guideline pages with the default ACC/AHA dataset:

```bash
hcg extract --api-key "$OPENAI_API_KEY"
```

Route requests through a specific organization or project when needed:

```bash
OPENAI_API_KEY=... ORGANIZATION_ID=... PROJECT_ID=... hcg extract --rerun-error-pages
```

Build the current release from the raw outputs:

```bash
hcg build-release
```

Without installing the package:

```bash
PYTHONPATH=src python -m hcg build-release
```

## Development

```bash
pytest
python -m hcg build-release
```

The repository is intentionally data-heavy because it ships the exact inputs and outputs used for the current HeartBioPortal guideline JSON release.
