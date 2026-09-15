"""Leitura do dataset sintético da fatia representativa."""

import json
from functools import lru_cache
from pathlib import Path

from src.models import DatasetCase

DATASET_PATH = Path(__file__).parent.parent / "data" / "dataset_sintetico.jsonl"


@lru_cache(maxsize=1)
def load_dataset() -> tuple[DatasetCase, ...]:
    """Carrega e valida todos os casos antes de disponibilizá-los."""
    with DATASET_PATH.open(encoding="utf-8") as dataset_file:
        return tuple(
            DatasetCase.model_validate(json.loads(line)) for line in dataset_file if line.strip()
        )


def find_case(case_id: str) -> DatasetCase | None:
    """Localiza um caso pelo identificador estável."""
    return next((case for case in load_dataset() if case.id == case_id), None)
