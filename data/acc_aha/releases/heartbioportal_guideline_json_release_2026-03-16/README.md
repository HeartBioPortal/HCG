# ACC/AHA HeartBioPortal Release Candidate

This folder is the current best handoff candidate for HeartBioPortal.

## Contents

- `documents/`
  One JSON file per ACC/AHA guideline or methodology document.
- `manifest.json`
  Build metadata, source provenance, recovered error pages, and gene-source mode for each document.

## Build notes

- Source corpus: `data/acc_aha/openai_outputs`
- Manual gene curation used for 21 documents
- Auto-normalized gene curation used for 16 documents
- Remaining page-level OpenAI failures recovered with `pdftotext` fallback: 0 pages

## Current status

The underlying ACC/AHA raw page set was rerun on March 16, 2026 using the current Responses API and `gpt-5-mini`. All previously failed page JSON files were regenerated successfully, so this release no longer depends on fallback text recovery for any page.

The remaining caveat is curation quality, not page coverage. Twenty-one documents use manual gene curation and sixteen use auto-normalized genes from the raw OpenAI output.
