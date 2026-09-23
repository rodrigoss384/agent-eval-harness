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
    *,
    model: str,
    pricing_profile: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_input_tokens: int | None = None,
) -> CostEstimate:
    """Calcula uma estimativa; nunca a apresenta como cobrança real."""
    catalog = _catalog()
    # Provider snapshots retain their family price; never substitute a different model.
    price_model = "gpt-4.1-mini" if model.startswith("gpt-4.1-mini-") else model
    if model.startswith("typesafe/jev-1.13-"):
        price_model = "typesafe/jev-1.13"
    entry = catalog["models"].get(price_model, {}).get(pricing_profile)
    if not entry or input_tokens is None or output_tokens is None:
        return CostEstimate("unavailable", None, "", str(catalog["version"]), None)
    input_rate = Decimal(str(entry["input_per_million_usd"]))
    output_rate = Decimal(str(entry["output_per_million_usd"]))
    cached = min(input_tokens, max(0, cached_input_tokens or 0))
    cache_rate = Decimal(str(entry.get("cached_input_per_million_usd", input_rate)))
    value = (
        Decimal(input_tokens - cached) * input_rate
        + Decimal(cached) * cache_rate
        + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)
    formula = (
        f"(({input_tokens} - {cached}) × {input_rate} + {cached} × "
        f"{cache_rate} + {output_tokens} × {output_rate}) / 1.000.000"
    )
    return CostEstimate(
        "estimated",
        float(value.quantize(Decimal("0.0000000001"))),
        formula,
        str(catalog["version"]),
        str(entry["source_url"]),
    )
