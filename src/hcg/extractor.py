from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from openai import BadRequestError, OpenAI
from tqdm import tqdm

from hcg.paths import DEFAULT_LOG_FILENAME
from hcg.schemas import EXTRACTION_INSTRUCTIONS, EXTRACTION_PROMPT, RESPONSE_SCHEMA


class GuidelinePageExtractor:
    def __init__(
        self,
        pdf_dir: Path,
        output_dir: Path,
        model: str,
        sleep_seconds: float = 1.0,
        api_key: str | None = None,
    ) -> None:
        self.pdf_dir = Path(pdf_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.sleep_seconds = sleep_seconds
        self.logger = self._configure_logger()
        self.client = OpenAI(api_key=api_key)

    def _configure_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"hcg.extractor.{self.output_dir}")
        if logger.handlers:
            return logger

        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        file_handler = logging.FileHandler(self.output_dir / DEFAULT_LOG_FILENAME)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        logger.propagate = False
        return logger

    def get_pdf_output_dir(self, pdf_path: Path) -> Path:
        pdf_output_dir = self.output_dir / pdf_path.stem
        pdf_output_dir.mkdir(parents=True, exist_ok=True)
        return pdf_output_dir

    def get_last_processed_page(self, pdf_output_dir: Path) -> int:
        existing_files = [file_path for file_path in pdf_output_dir.glob("*.json") if file_path.stem.isdigit()]
        if not existing_files:
            return 0
        return max(int(file_path.stem) for file_path in existing_files)

    def find_error_pages(self, pdf_output_dir: Path) -> list[int]:
        error_pages: list[int] = []
        for json_file in sorted(
            pdf_output_dir.glob("*.json"),
            key=lambda path: int(path.stem) if path.stem.isdigit() else 0,
        ):
            if not json_file.stem.isdigit():
                continue
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                error_pages.append(int(json_file.stem))
                continue
            content = payload.get("content") if isinstance(payload, dict) else None
            if isinstance(content, dict) and "error" in content:
                error_pages.append(int(json_file.stem))
        return error_pages

    def convert_pdf_to_images(
        self,
        pdf_path: Path,
        pages: Optional[Sequence[int]] = None,
    ) -> list[tuple[int, tempfile.NamedTemporaryFile]]:
        try:
            from pdf2image import convert_from_path

            temp_files: list[tuple[int, tempfile.NamedTemporaryFile]] = []
            if pages:
                for page_number in pages:
                    images = convert_from_path(pdf_path, first_page=page_number, last_page=page_number)
                    if not images:
                        continue
                    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    images[0].save(temp_file.name, "PNG")
                    temp_files.append((page_number, temp_file))
            else:
                for page_number, image in enumerate(convert_from_path(pdf_path), start=1):
                    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    image.save(temp_file.name, "PNG")
                    temp_files.append((page_number, temp_file))
            return temp_files
        except Exception as exc:
            if "poppler" in str(exc).lower():
                self.logger.error("Poppler error: Make sure Poppler is installed and in PATH")
            raise

    def _instructions(self, enforce_schema: bool) -> str:
        if enforce_schema:
            return EXTRACTION_INSTRUCTIONS
        return (
            f"{EXTRACTION_INSTRUCTIONS} Return only valid JSON that matches this schema exactly: "
            f"{json.dumps(RESPONSE_SCHEMA['schema'], separators=(',', ':'))}"
        )

    def _input_payload(self, encoded_image: str) -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": EXTRACTION_PROMPT},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{encoded_image}",
                        "detail": "high",
                    },
                ],
            }
        ]

    @staticmethod
    def _response_text(response: Any) -> str:
        response_text = getattr(response, "output_text", None)
        if response_text:
            return response_text

        texts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content_item in getattr(item, "content", []) or []:
                text_value = getattr(content_item, "text", None)
                if text_value:
                    texts.append(text_value)
        return "\n".join(texts)

    def _create_response(self, encoded_image: str) -> Any:
        payload = {
            "model": self.model,
            "instructions": self._instructions(enforce_schema=True),
            "input": self._input_payload(encoded_image),
            "text": {
                "format": {
                    "type": "json_schema",
                    **RESPONSE_SCHEMA,
                }
            },
            "max_output_tokens": 4096,
        }

        try:
            return self.client.responses.create(**payload)
        except BadRequestError as exc:
            error_text = str(exc).lower()
            unsupported_schema = any(
                snippet in error_text for snippet in ("json_schema", "structured", "text.format")
            )
            if not unsupported_schema:
                raise

            self.logger.warning(
                "Model %s rejected json_schema output; retrying with prompt-only JSON enforcement",
                self.model,
            )
            fallback_payload = {
                "model": self.model,
                "instructions": self._instructions(enforce_schema=False),
                "input": self._input_payload(encoded_image),
                "max_output_tokens": 4096,
            }
            return self.client.responses.create(**fallback_payload)

    @staticmethod
    def _coerce_json_payload(response_text: str) -> dict[str, Any]:
        normalized = response_text.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            normalized = "\n".join(lines).strip()

        if not normalized.startswith("{"):
            start = normalized.find("{")
            end = normalized.rfind("}")
            if start != -1 and end != -1 and end > start:
                normalized = normalized[start : end + 1]

        return json.loads(normalized)

    @staticmethod
    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if "genes" not in payload or not isinstance(payload["genes"], list):
            payload["genes"] = []
        if "content" not in payload or not isinstance(payload["content"], dict):
            payload["content"] = {}
        return payload

    def analyze_image(self, image_path: Path) -> dict[str, Any]:
        try:
            with image_path.open("rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode()
            response = self._create_response(encoded_image)
            response_text = self._response_text(response)
            payload = self._coerce_json_payload(response_text)
            return self._normalize_payload(payload)
        except Exception as exc:
            self.logger.error("Error analyzing image %s: %s", image_path, exc)
            return {"content": {"error": str(exc)}, "genes": []}

    def process_single_pdf(
        self,
        pdf_path: Path,
        selected_pages: Optional[Sequence[int]] = None,
        overwrite_existing: bool = False,
    ) -> None:
        self.logger.info("Processing PDF: %s", pdf_path)
        pdf_output_dir = self.get_pdf_output_dir(pdf_path)
        temp_files = self.convert_pdf_to_images(pdf_path, pages=selected_pages)

        if selected_pages is None:
            last_processed_page = self.get_last_processed_page(pdf_output_dir)
            temp_files = [
                (page_number, temp_file)
                for page_number, temp_file in temp_files
                if page_number > last_processed_page
            ]

        with tqdm(total=len(temp_files), desc=pdf_path.stem[:40], unit="page") as progress_bar:
            for page_number, temp_file in temp_files:
                try:
                    page_output_path = pdf_output_dir / f"{page_number}.json"
                    if page_output_path.exists() and not overwrite_existing:
                        progress_bar.update(1)
                        continue

                    result = self.analyze_image(Path(temp_file.name))
                    page_output_path.write_text(
                        json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    progress_bar.update(1)
                    time.sleep(self.sleep_seconds)
                finally:
                    os.unlink(temp_file.name)

    def iter_pdf_paths(self) -> list[Path]:
        return sorted(
            (path for path in self.pdf_dir.rglob("*.pdf") if path.is_file()),
            key=lambda path: str(path).lower(),
        )

    def process_pdf_paths(
        self,
        pdf_paths: Sequence[Path],
        *,
        rerun_error_pages: bool = False,
    ) -> None:
        for pdf_path in pdf_paths:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                self.logger.warning("Skipping missing PDF path: %s", pdf_path)
                continue
            try:
                if rerun_error_pages:
                    pdf_output_dir = self.get_pdf_output_dir(pdf_path)
                    error_pages = self.find_error_pages(pdf_output_dir)
                    if not error_pages:
                        continue
                    self.logger.info("Reprocessing error pages for %s: %s", pdf_path, error_pages)
                    self.process_single_pdf(
                        pdf_path,
                        selected_pages=error_pages,
                        overwrite_existing=True,
                    )
                else:
                    self.process_single_pdf(pdf_path)
            except Exception as exc:
                self.logger.error("Failed to process %s: %s", pdf_path, exc)

    def process_all_pdfs(self, rerun_error_pages: bool = False) -> None:
        self.process_pdf_paths(self.iter_pdf_paths(), rerun_error_pages=rerun_error_pages)

    def aggregate_outputs(self) -> dict[str, dict[str, Any]]:
        all_results: dict[str, dict[str, Any]] = {}

        for pdf_dir in sorted(directory for directory in self.output_dir.iterdir() if directory.is_dir()):
            pdf_name = pdf_dir.name
            all_results[pdf_name] = {"content": [], "genes": {}}
            json_files = sorted(
                [file_path for file_path in pdf_dir.glob("*.json") if file_path.stem.isdigit()],
                key=lambda path: int(path.stem),
            )

            for json_file_path in json_files:
                try:
                    page_data = json.loads(json_file_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    self.logger.error("Error loading page JSON from %s: %s", json_file_path, exc)
                    continue

                all_results[pdf_name]["content"].append(page_data)
                genes = page_data.get("genes", [])
                if not genes and isinstance(page_data, dict):
                    for value in page_data.values():
                        if isinstance(value, list) and value and isinstance(value[0], dict):
                            if any("Gene" in item or "gene" in item for item in value):
                                genes = value
                                break

                for gene_entry in genes:
                    gene_name = gene_entry.get("Gene") or gene_entry.get("gene")
                    if not gene_name:
                        continue

                    occurrences = gene_entry.get("Occurrences") or gene_entry.get("occurrences") or 1
                    conditions = gene_entry.get("Associated Conditions") or gene_entry.get(
                        "associated_conditions"
                    ) or []
                    context = gene_entry.get("context") or gene_entry.get("Context") or []

                    if isinstance(conditions, str):
                        conditions = [conditions]
                    if isinstance(context, str):
                        context = [context]

                    if gene_name not in all_results[pdf_name]["genes"]:
                        all_results[pdf_name]["genes"][gene_name] = {
                            "Gene": gene_name,
                            "Associated Conditions": list(conditions),
                            "Occurrences": occurrences,
                            "context": list(context),
                        }
                        continue

                    target = all_results[pdf_name]["genes"][gene_name]
                    target["Occurrences"] += occurrences
                    for condition in conditions:
                        if condition not in target["Associated Conditions"]:
                            target["Associated Conditions"].append(condition)
                    for context_value in context:
                        if context_value not in target["context"]:
                            target["context"].append(context_value)

            all_results[pdf_name]["genes"] = list(all_results[pdf_name]["genes"].values())
            output_path = self.output_dir / f"{pdf_name}_aggregated.json"
            output_path.write_text(
                json.dumps(all_results[pdf_name], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.logger.info(
                "Saved aggregated data for %s with %s genes",
                pdf_name,
                len(all_results[pdf_name]["genes"]),
            )

        return all_results
