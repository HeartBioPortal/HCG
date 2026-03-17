# Project Audit

## Bottom line

The OpenAI page-image pipeline is the current working extraction workflow in this repository. The ACC/AHA extraction run is complete at the raw page level, and all previously failed page JSON files have been rerun successfully. The repository now also includes a live scraper/sync layer for both ACC/AHA and ESC guideline sources.

The current release artifact is:

- `data/acc_aha/releases/heartbioportal_guideline_json_release_2026-03-16`

## What is complete

- `data/acc_aha/source_pdfs` contains the source ACC/AHA guideline and methodology PDFs used for the current run.
- `data/acc_aha/openai_outputs` contains outputs for all `37` ACC/AHA documents.
- `data/esc/` is scaffolded for ESC scraping and extraction outputs.
- Every source page has a matching page-level JSON file.
- Every processed document has an aggregated JSON file.
- The latest raw ACC/AHA page set has `0` remaining page-level extraction errors.
- The release artifact has been rebuilt from the cleaned raw output set and no longer depends on fallback page recovery.
- `hcg scrape` can now check the live ACC and ESC sites for PDFs not already present locally.
- `hcg sync` can now scrape, download, and extract PDFs that are missing JSON outputs without rerunning the full corpus or redownloading already-matched PDFs.
- Live ESC downloads work automatically. Live ACC discovery works, but JACC can block automated downloads with a Cloudflare verification page, so blocked ACC items are now recorded and skipped instead of stalling the sync run.

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

### 4. ESC has not been populated yet in this repo snapshot

The code path for ESC scraping and extraction is in place, but `data/esc/source_pdfs` and `data/esc/openai_outputs` are still empty until `hcg sync --datasets esc ...` is run with network access and a valid OpenAI API key.

## Recommended next steps

1. Run `hcg sync --datasets esc --model gpt-5-mini` to populate the ESC dataset.
2. Run `hcg sync --datasets acc_aha --model gpt-5-mini` to capture newer ACC guidelines published after the current local corpus.
3. Spot-check the `16` auto-normalized ACC/AHA documents in the release manifest.
4. Decide whether the methodology documents should stay in the main ACC/AHA release or move to a separate dataset.
5. Expand `data/acc_aha/manual_gene_review.json` if you want all ACC/AHA release documents to have explicit human-reviewed gene lists.
