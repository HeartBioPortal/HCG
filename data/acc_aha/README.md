# ACC/AHA Dataset

This directory contains the complete ACC/AHA workflow inputs and outputs kept in this standalone repository.

## Contents

- `source_pdfs/`
  Source guideline PDFs used by the extractor and future sync runs.
- `openai_outputs/`
  Raw page-level JSON and aggregated JSON produced by the OpenAI extraction pipeline.
- `manual_gene_review.json`
  Human-curated title-to-gene mapping used by the release builder.
- `releases/`
  Release-ready document JSON prepared for downstream HeartBioPortal ingestion.
- `scraper_manifest.json`
  Created by `hcg scrape` or `hcg sync` to track upstream ACC guideline discovery and local PDF matches/downloads.
- `scraper.log`
  ACC scraper log file.

## Current release

- `releases/heartbioportal_guideline_json_release_2026-03-16`

## Current raw extraction status

- `37` ACC/AHA documents
- `2732` page-level JSON files
- `0` remaining page-level extraction errors

## Sync behavior

`hcg sync --datasets acc_aha ...` checks the live ACC guideline page for new guideline PDFs. It does not redownload PDFs that already exist locally, and it will still extract any tracked PDFs that are missing JSON outputs before rebuilding the ACC/AHA release. If JACC blocks an automated download behind Cloudflare, that item is marked as `blocked` in `scraper_manifest.json` and the sync run continues.
