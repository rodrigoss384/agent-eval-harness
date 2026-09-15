"""Estimativa monetária rastreável por catálogo versionado."""

import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

CATALOG_PATH = Path(__file__).parent.parent.parent / "data" / "model_pricing.json"


@dataclass(frozen=True, slots=True)
class CostEstimate:
    status: str
    usd: float | None
    formula: str
    catalog_version: str | None
    source_url: str | None


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


def estimate_cost(
    *, model: str, pricing_profile: str, input_tokens: int | None, output_tokens: int | None
) -> CostEstimate:
    """Calcula uma estimativa; nunca a apresenta como cobrança real."""
    catalog = _catalog()
    entry = catalog["models"].get(model, {}).get(pricing_profile)
    if not entry or input_tokens is None or output_tokens is None:
        return CostEstimate("unavailable", None, "", str(catalog["version"]), None)
    input_rate = Decimal(str(entry["input_per_million_usd"]))
    output_rate = Decimal(str(entry["output_per_million_usd"]))
    value = (Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate) / Decimal(
        1_000_000
    )
    formula = f"({input_tokens} × {input_rate} + {output_tokens} × {output_rate}) / 1.000.000"
    return CostEstimate(
        "estimated",
        float(value.quantize(Decimal("0.0000000001"))),
        formula,
        str(catalog["version"]),
        str(entry["source_url"]),
    )
