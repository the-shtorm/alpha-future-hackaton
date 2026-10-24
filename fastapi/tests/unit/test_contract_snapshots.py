"""Check shipped contracts against the application and the Java-owned response schema."""

import json

import jsonschema
import pytest
from conftest import ROOT

from app.schemas.java_exchange import Condition, JavaMetadata, JavaRankedProduct, JavaRankResponse


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_published_openapi_matches_runtime(application):
    assert read_json(ROOT / "contracts/openapi.json") == application.openapi()


@pytest.mark.parametrize("path", sorted((ROOT / "contracts").glob("*.schema.json")))
def test_published_json_schemas_are_valid(path):
    schema = read_json(path)
    jsonschema.validators.validator_for(schema).check_schema(schema)


def test_java_response_schema_covers_every_transport_field():
    schema = read_json(ROOT / "contracts/java-rank-response.schema.json")
    for model, part in (
        (JavaRankResponse, schema),
        (JavaMetadata, schema["properties"]["metadata"]),
        (JavaRankedProduct, schema["properties"]["results"]["items"]),
        (Condition, schema["$defs"]["condition"]),
    ):
        assert set(part["properties"]) == set(part["required"]) == set(model.model_fields)
        assert part["additionalProperties"] is False
