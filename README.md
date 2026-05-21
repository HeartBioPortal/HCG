# HCG

HCG is a standalone HeartBioPortal module for preparing cardiovascular guideline PDFs and converting them into structured JSON artifacts.

HCG supports the HBP 3.0 ecosystem by serving as the clinical guideline extraction resource upstream of the HeartBioPortal guideline dossier and the HCG-KG knowledge graph. It discovers or stages guideline source PDFs, prepares page images, extracts structured page-level JSON, validates gene symbols, and builds guideline release artifacts that downstream HBP services can transform into gene-first guideline context.

The repository now centers on the locally refreshed guideline corpus while retaining the dataset-aware scraper/sync pipeline for future upstream checks:

- `acc_aha`
  ACC guideline discovery on `acc.org`, with browser-backed PDF resolution for JACC-hosted files.
- `esc`
  ESC guideline discovery on `escardio.org`, with article-first capture from the linked Oxford Academic guideline pages.

It also supports a staged rerun workflow for locally downloaded PDFs. This is the preferred path for
the `data/ESC-NEW` and `data/AHA-ACC-NEW` folders because it separates cheap page-image preparation
from later OpenAI vision extraction.

## Repository layout

- `src/hcg`
  Python package with the scraper, OpenAI extractor, release builder, schemas, and CLI.
- `data/reference/gene_names.json`
  Canonical gene reference used during normalization.
- `data/ESC-NEW` and `data/AHA-ACC-NEW`
  Newly downloaded local rerun corpus. These are treated as source inputs, not OpenAI outputs.
- `data/prepared_images/rerun_2026_05_18_api_ready`
  Page images rendered from the new local PDFs, with one directory and manifest per source PDF.
- `docs/project_audit.md`
  Current project audit and remaining caveats.

## Current status

- The old checked-in ACC/AHA and ESC raw extraction folders have been removed.
- The refreshed local corpus contains `42` PDFs: `22` ACC/AHA PDFs and `20` ESC PDFs.
- The image-only preparation stage rendered `4,290` page images with `0` failures under `data/prepared_images/rerun_2026_05_18_api_ready`.
- The rendered page images are intentionally ignored by git; regenerate them locally with `hcg prepare-images` when needed.
- OpenAI extraction and release building have not been rerun yet for the refreshed corpus.

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

Extract pages directly for a single scraper-managed dataset:

```bash
hcg extract --dataset acc_aha --api-key "$OPENAI_API_KEY"
```

Test one specific page from one specific guideline before running the full corpus:

```bash
export OPENAI_API_KEY="paste-your-key-here"
PYTHONPATH=src python3 -m hcg extract-page \
  --pdf "data/AHA-ACC-NEW/al-khatib-et-al-2018-2017-aha-acc-hrs-guideline-for-management-of-patients-with-ventricular-arrhythmias-and-the (1).pdf" \
  --page 21 \
  --output-dir data/test_openai_outputs \
  --overwrite
```

The command sends only that page image to OpenAI. It writes the page JSON under
`data/test_openai_outputs/<pdf-stem>/<page>.json`, writes detailed logs to
`data/test_openai_outputs/pdf_processing.log`, and shows a `tqdm` progress bar for the requested page.

If a model is unavailable for your organization, probe several candidates against the same page:

```bash
PYTHONPATH=src python3 -m hcg probe-models \
  --pdf "data/AHA-ACC-NEW/al-khatib-et-al-2018-2017-aha-acc-hrs-guideline-for-management-of-patients-with-ventricular-arrhythmias-and-the (1).pdf" \
  --page 43 \
  --output-dir data/model_probe_outputs
```

By default this tests `gpt-4.1-mini`, `gpt-4.1`, `gpt-4o-mini`, `gpt-4o`, `o4-mini`,
`gpt-5-mini`, and `gpt-5.4-mini`. Each model gets its own output directory under
`data/model_probe_outputs/<model>/`, and the command prints a tab-separated OK/FAIL summary.

Prepare the new locally downloaded PDFs as page images without calling the OpenAI API:

```bash
PYTHONPATH=src python3 -m hcg prepare-images --overwrite --jobs 4 --image-format jpg
```

That command defaults to:

- `data/ESC-NEW` -> `data/prepared_images/rerun_2026_05_18_api_ready/esc_new`
- `data/AHA-ACC-NEW` -> `data/prepared_images/rerun_2026_05_18_api_ready/acc_aha_new`

Each guideline gets its own directory:

```text
data/prepared_images/rerun_2026_05_18_api_ready/<dataset>/<document-slug>/
  manifest.json
  pages/
    page_0001.jpg
    page_0002.jpg
```

The top-level `corpus_manifest.json` records every source PDF, rendered page count, output
directory, and any failures. This is the checkpoint to inspect before spending API credits.

Rerun only stored error pages:

```bash
OPENAI_API_KEY=... hcg extract --rerun-error-pages
```

Build the ACC/AHA release from raw outputs after extraction artifacts are available:

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
- New reruns should keep each PDF compartmentalized: source PDF in the local corpus folder, rendered
  images under `data/prepared_images/.../<document-slug>/pages`, page JSONs under a matching document
  output directory, and final release/serving artifacts built only after validation.
- The extraction prompt is image-layout aware. It asks the model to preserve recommendation rows,
  Class/COR, Level/LOE, figures/tables, and page-continuity flags rather than flattening pages into
  loose prose.
- Gene extraction is intentionally conservative. The model is instructed to omit bare clinical
  abbreviations unless the page visually supports a human gene interpretation, and downstream release
  building still validates symbols against `data/reference/gene_names.json`.
- If Playwright Chromium is not installed, ACC scraping now fails with a direct instruction to run `.venv/bin/playwright install chromium`.
- JACC can still block automated access behind a Cloudflare verification page, even in a visible browser. When that happens, the ACC scraper records the item as `blocked` in the manifest and continues instead of hanging.
- ESC scraping now ignores ESC declaration-of-interest attachments, follows the linked journal article, and renders the article page to PDF for extraction.
- Existing ESC PDFs that look like declaration-of-interest reports are treated as stale and replaced on the next `hcg scrape` or `hcg sync` run.
- Scraper logs are written to `data/<dataset>/scraper.log`.
- Scraper manifests are written to `data/<dataset>/scraper_manifest.json`.
- `hcg sync` and `hcg extract` now fail immediately with a clear error if `OPENAI_API_KEY` is not set.
- `hcg sync` extracts any tracked PDFs that are still missing JSON outputs, even if those PDFs were downloaded in an earlier run.
- `hcg sync` does not redownload PDFs that already exist locally and match the upstream scraper catalog.
- If you ever install `hcg` non-editably, set `HCG_PROJECT_ROOT=/absolute/path/to/HCG` so outputs still land in the repo `data/` directory.

The repository is intentionally data-heavy because it ships the refreshed guideline PDFs used for the next HeartBioPortal guideline extraction run.

## How this repository supports HBP 3.0

HCG is the source-document and structured-extraction layer for cardiovascular guideline evidence in HeartBioPortal 3.0. HCG-KG builds graph and query artifacts from parsed guideline JSON, and DataHub can consume guideline-derived outputs for HBP search dossiers.

Related HBP 3.0 repositories:

- HeartBioPortal organization: https://github.com/HeartBioPortal
- Live site: https://heartbioportal.org/
- DataHub: https://github.com/HeartBioPortal/DataHub
- HCG-KG: https://github.com/HeartBioPortal/HCG-KG

## Manuscript release

This repository supports the HeartBioPortal 3.0 NAR Database Issue manuscript release (`v3.0.0-nar`). Release-support files include citation metadata, source and output manifests, provenance documentation, release notes, and checksum tooling.

Clinical guideline outputs are intended to expose guideline context. They should not be interpreted as medical advice, automated clinical recommendations, or direct clinical actionability.

## Security and privacy

No controlled individual-level human data should be committed. Do not commit API keys, credentials, protected data, tokens, or restricted source data. Source-specific licensing controls redistribution of guideline PDFs, snippets, and other third-party content; if redistribution rights are uncertain, document the source in `GUIDELINE_SOURCES.tsv` rather than adding new raw data.
