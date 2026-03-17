from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from tqdm import tqdm

from hcg.common import load_json, write_json

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
STOPWORDS = {
    "a",
    "acc",
    "aha",
    "amssm",
    "and",
    "apma",
    "asa",
    "ase",
    "cardiovascular",
    "clinical",
    "disease",
    "for",
    "guideline",
    "guidelines",
    "guideline-focused",
    "guidelinefocused",
    "hrs",
    "in",
    "management",
    "of",
    "on",
    "patients",
    "practice",
    "report",
    "scai",
    "statement",
    "the",
    "update",
    "with",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def build_logger(name: str, log_path: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(level)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    return logger


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def slugify(value: str, max_length: int = 120) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"&", " and ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized[:max_length].rstrip("-") or "guideline"


def normalize_title(text: str) -> str:
    text = re.sub(r"^read on [^:]+:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def resolve_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url, href)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> dict:
    if not path.exists():
        return {"documents": []}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {"documents": []}
    payload.setdefault("documents", [])
    return payload


def write_manifest(path: Path, payload: dict) -> None:
    write_json(path, payload)


def relative_to_project(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def text_tokens(text: str) -> set[str]:
    tokens = {normalize_token(token) for token in TOKEN_RE.findall(text.lower())}
    return {token for token in tokens if token not in STOPWORDS and len(token) > 2}


def year_from_text(text: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", text)
    if not match:
        return None
    return int(match.group(0))


def _flatten_text(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        fragments: list[str] = []
        for nested_value in value.values():
            fragments.extend(_flatten_text(nested_value))
        return fragments
    if isinstance(value, list):
        fragments = []
        for nested_value in value:
            fragments.extend(_flatten_text(nested_value))
        return fragments
    return []


def _output_text_for_pdf(raw_output_dir: Path | None, pdf_stem: str) -> str:
    if raw_output_dir is None:
        return ""

    page_json_path = raw_output_dir / pdf_stem / "1.json"
    if page_json_path.exists():
        try:
            payload = json.loads(page_json_path.read_text(encoding="utf-8"))
            return " ".join(_flatten_text(payload.get("content", payload)))
        except Exception:  # noqa: BLE001
            return ""

    aggregated_path = raw_output_dir / f"{pdf_stem}_aggregated.json"
    if aggregated_path.exists():
        try:
            payload = json.loads(aggregated_path.read_text(encoding="utf-8"))
            return " ".join(_flatten_text(payload.get("content", payload)))
        except Exception:  # noqa: BLE001
            return ""

    return ""


def existing_pdf_index(source_pdf_dir: Path, raw_output_dir: Path | None = None) -> list[dict[str, object]]:
    index: list[dict[str, object]] = []
    for pdf_path in sorted(source_pdf_dir.rglob("*.pdf")):
        searchable = f"{pdf_path.parent.name} {pdf_path.stem} {_output_text_for_pdf(raw_output_dir, pdf_path.stem)}"
        index.append(
            {
                "path": pdf_path,
                "tokens": text_tokens(searchable),
                "year": year_from_text(searchable),
            }
        )
    return index


def match_existing_pdf(title: str, source_pdf_dir: Path) -> Path | None:
    return match_existing_pdf_from_index(title, existing_pdf_index(source_pdf_dir))


def match_existing_pdf_from_index(title: str, pdf_index: list[dict[str, object]]) -> Path | None:
    candidate_tokens = text_tokens(title)
    if not candidate_tokens:
        return None
    candidate_year = year_from_text(title)
    best_match: tuple[int, float, Path] | None = None

    for entry in pdf_index:
        path = entry["path"]
        tokens = entry["tokens"]
        year = entry["year"]
        overlap = candidate_tokens & tokens
        if candidate_year is not None and year is not None and candidate_year != year:
            continue
        overlap_count = len(overlap)
        if overlap_count < 3:
            continue
        coverage = overlap_count / max(len(candidate_tokens), 1)
        if coverage < 0.45 and overlap_count < 5:
            continue
        score = (overlap_count, coverage, path)
        if best_match is None or score > best_match:
            best_match = score

    return None if best_match is None else best_match[2]


def manifest_lookup(manifest: dict, landing_url: str, project_root: Path) -> Path | None:
    for document in manifest.get("documents", []):
        if document.get("landing_url") != landing_url:
            continue
        relative_path = document.get("local_pdf")
        if not relative_path:
            continue
        pdf_path = project_root / relative_path
        if pdf_path.exists():
            return pdf_path
    return None


def download_file(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    logger: logging.Logger,
    description: str,
    timeout_seconds: float,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=timeout_seconds) as response:
        response.raise_for_status()
        total_bytes = int(response.headers.get("Content-Length", 0))
        with destination.open("wb") as handle, tqdm(
            total=total_bytes or None,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=description[:40],
            leave=False,
        ) as progress:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if not chunk:
                    continue
                handle.write(chunk)
                progress.update(len(chunk))

    byte_count = destination.stat().st_size
    logger.info("Downloaded %s (%s bytes)", destination.name, byte_count)
    return byte_count


def dedupe_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered
