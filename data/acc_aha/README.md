# ACC/AHA Dataset

This directory contains the complete ACC/AHA workflow inputs and outputs kept in this standalone repository.

## Contents

- `source_pdfs/`
  Source guideline PDFs used by the extractor.
- `openai_outputs/`
  Raw page-level JSON and aggregated JSON produced by the OpenAI extraction pipeline.
- `manual_gene_review.json`
  Human-curated title-to-gene mapping used by the release builder.
- `releases/`
  Release-ready document JSON prepared for downstream HeartBioPortal ingestion.

## Current release

- `releases/heartbioportal_guideline_json_release_2026-03-16`

## Current raw extraction status

- `37` ACC/AHA documents
- `2732` page-level JSON files
- `0` remaining page-level extraction errors
