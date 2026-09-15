"""Catálogo e importação segura de datasets sintéticos JSONL."""

import hashlib
import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from src.dataset import DATASET_PATH, load_dataset
from src.models import DatasetCase, DatasetDocument, DatasetImportRequest, DatasetMetadata
from src.storage import SQLiteStore

MAX_DATASET_BYTES = 2 * 1024 * 1024
MAX_DATASET_CASES = 500


class DatasetValidationError(ValueError):
    """Agrupa erros auditáveis por linha da importação."""

    def __init__(self, errors: list[dict[str, object]]) -> None:
        super().__init__("O JSONL contém casos inválidos.")
        self.errors = errors


def _validate_case_semantics(case: DatasetCase, line_number: int) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    chunk_ids = {chunk.id for chunk in case.reference_context}
    if len(chunk_ids) != len(case.reference_context):
        errors.append(
            {
                "line": line_number,
                "field": "reference_context",
                "message": "IDs de chunks duplicados.",
            }
        )
    if case.retrieval:
        missing = sorted(set(case.retrieval.expected_context_ids) - chunk_ids)
        if missing:
            errors.append(
                {
                    "line": line_number,
                    "field": "retrieval.expected_context_ids",
                    "message": f"Chunks inexistentes: {', '.join(missing)}",
                }
            )
    for field, patterns in (
        ("deterministic_assertions", [item.pattern for item in case.deterministic_assertions]),
        ("forbidden_patterns", case.forbidden_patterns),
    ):
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                errors.append(
                    {"line": line_number, "field": field, "message": f"Regex inválida: {error}"}
                )
    if case.category == "retrieval" and (not case.reference_context or case.retrieval is None):
        errors.append(
            {
                "line": line_number,
                "field": "retrieval",
                "message": "Caso retrieval exige chunks e configuração de recuperação.",
            }
        )
    if case.category == "tool_use" and case.tool is None:
        errors.append(
            {
                "line": line_number,
                "field": "tool",
                "message": "Caso tool_use exige contrato de ferramenta.",
            }
        )
    return errors


def parse_import(request: DatasetImportRequest) -> DatasetDocument:
    """Valida tamanho, JSON, schema, regex, referências e IDs do JSONL."""
    raw = request.content.encode("utf-8")
    if len(raw) > MAX_DATASET_BYTES:
        raise DatasetValidationError(
            [{"line": 0, "field": "content", "message": "O arquivo excede 2 MiB."}]
        )
    cases: list[DatasetCase] = []
    errors: list[dict[str, object]] = []
    seen: set[str] = set()
    lines = [line for line in request.content.splitlines() if line.strip()]
    if len(lines) > MAX_DATASET_CASES:
        raise DatasetValidationError(
            [{"line": 0, "field": "content", "message": "O dataset excede 500 casos."}]
        )
    for number, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
            case = DatasetCase.model_validate(value)
        except (json.JSONDecodeError, ValidationError) as error:
            errors.append({"line": number, "field": "case", "message": str(error)})
            continue
        if case.id in seen:
            errors.append({"line": number, "field": "id", "message": f"ID duplicado: {case.id}"})
        seen.add(case.id)
        errors.extend(_validate_case_semantics(case, number))
        cases.append(case)
    if not cases and not errors:
        errors.append({"line": 0, "field": "content", "message": "O JSONL está vazio."})
    if errors:
        raise DatasetValidationError(errors)
    checksum = hashlib.sha256(raw).hexdigest()
    now = datetime.now(UTC)
    return DatasetDocument(
        metadata=DatasetMetadata(
            dataset_id=f"dataset_{uuid4().hex[:12]}",
            name=request.name,
            source="imported",
            case_count=len(cases),
            checksum=checksum,
            created_at=now,
        ),
        cases=cases,
    )


def builtin_document() -> DatasetDocument:
    content = DATASET_PATH.read_bytes()
    cases = list(load_dataset())
    return DatasetDocument(
        metadata=DatasetMetadata(
            dataset_id="builtin-v2",
            name="Suíte profissional sintética v2",
            source="builtin",
            case_count=len(cases),
            checksum=hashlib.sha256(content).hexdigest(),
            created_at=datetime.fromtimestamp(DATASET_PATH.stat().st_mtime, UTC),
        ),
        cases=cases,
    )


async def get_dataset(store: SQLiteStore, dataset_id: str) -> DatasetDocument | None:
    if dataset_id == "builtin-v2":
        return builtin_document()
    document = await store.get_dataset(dataset_id)
    return None if document is None else DatasetDocument.model_validate_json(document)


async def list_datasets(store: SQLiteStore) -> list[DatasetMetadata]:
    imported = [
        DatasetDocument.model_validate_json(item).metadata for item in await store.list_datasets()
    ]
    return [builtin_document().metadata, *imported]
