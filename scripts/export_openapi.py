"""Exporta o contrato OpenAPI gerado pelo FastAPI de forma reproduzível."""

import json
from pathlib import Path

from src.main import app

output = Path("openapi/openapi.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(output)
