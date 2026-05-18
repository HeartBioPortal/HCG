#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

output="CHECKSUMS.txt"
tmp="${output}.tmp"

files=(
  "README.md"
  "LICENSE"
  "CITATION.cff"
  ".zenodo.json"
  "RELEASE_NOTES.md"
  "MANIFEST.md"
  "GUIDELINE_SOURCES.tsv"
  "OUTPUT_MANIFEST.tsv"
  "PROVENANCE_SCHEMA.md"
)

for file in "${files[@]}"; do
  if [[ -f "$file" ]]; then
    shasum -a 256 "$file"
  fi
done > "$tmp"

mv "$tmp" "$output"
echo "Wrote $output"
