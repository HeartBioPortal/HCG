# Release Notes

## v3.0.0-nar

This release prepares HCG as the cardiovascular clinical guideline extraction resource for the HeartBioPortal 3.0 NAR Database Issue manuscript archive.

Included release-support material:

- `GUIDELINE_SOURCES.tsv` with guideline corpus metadata and licensing cautions
- `OUTPUT_MANIFEST.tsv` for extraction and release output families
- `PROVENANCE_SCHEMA.md` for guideline extraction provenance
- `MANIFEST.md`, `CITATION.cff`, `.zenodo.json`, and checksum tooling
- README sections linking HCG to DataHub, HCG-KG, the HeartBioPortal organization, and the live site

The current refreshed local corpus contains 42 PDFs in `data/AHA-ACC-NEW` and `data/ESC-NEW`. Page-image preparation has been run for the refreshed corpus, but OpenAI extraction and final release building have not been rerun for all refreshed PDFs in this checkout.

Third-party guideline source documents remain subject to publisher and society terms. Do not redistribute PDFs or long excerpts unless rights are confirmed.
