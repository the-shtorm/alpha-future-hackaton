"""Run from fastapi: uv run --project scoring_training python -m scoring_training.export_contracts."""

import json
from pathlib import Path

from app.scoring.contracts import ScoringRequest, ScoringResponse


def main():
    destination = Path(__file__).resolve().parents[1] / "contracts"
    for name, model in (("scoring-request", ScoringRequest), ("scoring-response", ScoringResponse)):
        (destination / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
