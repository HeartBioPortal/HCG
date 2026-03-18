# HCG

HCG is a standalone HeartBioPortal module for scraping cardiovascular guideline PDFs and converting them into structured JSON artifacts.

The repository ships the current ACC/AHA extraction corpus and now includes a dataset-aware scraper/sync pipeline for:

- `acc_aha`
  ACC guideline discovery on `acc.org`, with browser-backed PDF resolution for JACC-hosted files.
- `esc`
  ESC guideline discovery on `escardio.org`, with direct PDF downloads from ESC-hosted guideline pages.

## Repository layout

- `src/hcg`
  Python package with the scraper, OpenAI extractor, release builder, schemas, and CLI.
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
- `data/esc`
  ESC dataset workspace for scraped PDFs, scraper manifests, and extracted outputs.
- `docs/project_audit.md`
  Current project audit and remaining caveats.

## Current status

- The ACC/AHA raw page set is complete and currently has `0` remaining page-level extraction errors.
- The current ACC/AHA release contains `37` document JSON files.
- The scraper/sync workflow is in place for both `acc_aha` and `esc`.
- The remaining content caveat is curation quality for the `16` ACC/AHA auto-normalized documents that do not yet have full manual review.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install chromium
```

On Ubuntu or other minimal Linux hosts, you may also need:

```bash
sudo .venv/bin/playwright install --with-deps chromium
```

`pdf2image` requires Poppler on the host system.

- macOS: `brew install poppler`
- Ubuntu/Debian: `sudo apt-get install poppler-utils`

## CLI usage

Scrape both upstream sources and download any missing PDFs:

```bash
hcg scrape
```

Inspect live discovery without downloading files:

```bash
hcg scrape --datasets esc --limit 5 --dry-run
```

Run the end-to-end update flow. This scrapes the source sites, downloads missing PDFs, extracts newly downloaded pages to JSON, aggregates outputs, and rebuilds the ACC/AHA release if that dataset changed:

```bash
OPENAI_API_KEY=... hcg sync
```

Target a specific dataset:

```bash
OPENAI_API_KEY=... hcg sync --datasets esc --model gpt-5-mini
```

For ACC/AHA updates on a desktop session, prefer the visible browser mode because JACC can block headless Chromium with a Cloudflare verification page:

```bash
OPENAI_API_KEY=... hcg sync --datasets acc_aha --model gpt-5-mini --show-browser
```

Extract pages directly for a single dataset:

```bash
hcg extract --dataset acc_aha --api-key "$OPENAI_API_KEY"
```

Rerun only stored error pages:

```bash
OPENAI_API_KEY=... hcg extract --rerun-error-pages
```

Build the ACC/AHA release from raw outputs:

```bash
hcg build-release
```

Without installing the package:

```bash
PYTHONPATH=src python -m hcg sync --datasets all --model gpt-5-mini
```

## Development

```bash
pytest
python -m hcg scrape --datasets esc --limit 1 --dry-run
python -m hcg build-release
```

## Operational notes

- ACC scraping uses Playwright because the ACC site links out to JACC-hosted documents that are not reliably downloadable through plain HTTP requests.
- If Playwright Chromium is not installed, ACC scraping now fails with a direct instruction to run `.venv/bin/playwright install chromium`.
- JACC can still block automated access behind a Cloudflare verification page, even in a visible browser. When that happens, the ACC scraper records the item as `blocked` in the manifest and continues instead of hanging.
- ESC scraping uses direct PDF links exposed on official ESC guideline detail pages.
- Scraper logs are written to `data/<dataset>/scraper.log`.
- Scraper manifests are written to `data/<dataset>/scraper_manifest.json`.
- `hcg sync` and `hcg extract` now fail immediately with a clear error if `OPENAI_API_KEY` is not set.
- `hcg sync` extracts any tracked PDFs that are still missing JSON outputs, even if those PDFs were downloaded in an earlier run.
- `hcg sync` does not redownload PDFs that already exist locally and match the upstream scraper catalog.

The repository is intentionally data-heavy because it ships the exact inputs and outputs used for the current HeartBioPortal ACC/AHA guideline JSON release.
