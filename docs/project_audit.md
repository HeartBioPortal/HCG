# Project Audit

## Bottom line

The OpenAI page-image pipeline is the current working workflow in this repository. The ACC/AHA extraction run is complete at the raw page level, and all previously failed page JSON files have been rerun successfully. The remaining work is curation validation, not extraction coverage.

The current release artifact is:

- `data/acc_aha/releases/heartbioportal_guideline_json_release_2026-03-16`

## What is complete

- `data/acc_aha/source_pdfs` contains the source ACC/AHA guideline and methodology PDFs used for the current run.
- `data/acc_aha/openai_outputs` contains outputs for all `37` ACC/AHA documents.
- Every source page has a matching page-level JSON file.
- Every processed document has an aggregated JSON file.
- The latest raw ACC/AHA page set has `0` remaining page-level extraction errors.
- The release artifact has been rebuilt from the cleaned raw output set and no longer depends on fallback page recovery.

## Coverage counts

- ACC/AHA documents: `37`
- ACC/AHA page JSON files: `2732`
- Aggregated ACC/AHA raw outputs: `37`
- Release document JSON files: `37`
- Manual-curation documents: `21`
- Auto-normalized documents: `16`
- Final canonical gene entries in the release: `174`

## What is not fully done

### 1. The release is not fully human-curated

The raw extraction coverage is complete, but `16` documents in the release still rely on auto-normalized gene output rather than explicit manual review.

### 2. The manual review map is partial

`data/acc_aha/manual_gene_review.json` contains reviewed gene lists for `21` titles, not the full `37`-document corpus.

### 3. Methodology documents are still mixed with clinical guideline documents

The current source and release sets include both core clinical guidelines and methodology or process-oriented documents. That may be acceptable for provenance, but it is still a product decision rather than a purely technical one.

## Recommended next steps

1. Spot-check the `16` auto-normalized documents in the release manifest.
2. Decide whether the methodology documents should stay in the main release or move to a separate dataset.
3. Expand `data/acc_aha/manual_gene_review.json` if you want all release documents to have explicit human-reviewed gene lists.
