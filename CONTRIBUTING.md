# Contributing

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Common commands

```bash
pytest
python -m hcg build-release
python -m hcg extract --rerun-error-pages
```

## Scope

This repository is intentionally scoped to the ACC/AHA guideline pipeline and the release artifacts used by HeartBioPortal. Keep unrelated experiments, notebooks, analysis outputs, and virtual environments out of the repo.
