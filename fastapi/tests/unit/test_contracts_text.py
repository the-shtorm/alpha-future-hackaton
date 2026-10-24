import copy
import json

import jsonschema
import pytest
from conftest import ROOT
from pydantic import ValidationError

from app.schemas.requests import Business, FundingRequest, Product, Profile, RankRequest, Security, clean_text
from app.services.text_builder import LABELS, build_passage, build_query


def test_complete_field_coverage_and_openapi(application):
    fields = json.loads((ROOT / "contracts/field-coverage.json").read_text())
    actual = [
        f"{prefix}.{field}"
        for prefix, cls in (("business", Business), ("request", FundingRequest), ("security", Security))
        for field in cls.model_fields
    ]
    assert set(actual) == set(fields["queryProfileFields"])
    assert set(Product.model_fields) == set(fields["productFields"])
    schemas = application.openapi()["components"]["schemas"]
    for cls in (Business, FundingRequest, Security, Product):
        assert set(schemas[cls.__name__]["properties"]) == set(cls.model_fields)
    schema = json.loads((ROOT / "contracts/rank-request.schema.json").read_text())
    profile = schema["properties"]["profile"]["properties"]
    assert {f"{k}.{f}" for k, v in profile.items() for f in v["properties"]} == set(actual)
    assert set(schema["properties"]["candidates"]["items"]["properties"]["product"]["properties"]) == set(
        Product.model_fields
    )


@pytest.mark.parametrize("path", sorted((ROOT / "examples").glob("rank-request*.json")))
def test_fixtures_follow_both_contracts(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(raw, json.loads((ROOT / "contracts/rank-request.schema.json").read_text()))
    RankRequest.model_validate(raw)


@pytest.mark.parametrize("value", ["YES", "NO", "DISCUSS", "UNKNOWN"])
def test_query_security_exact_phrases(payload, value):
    payload["profile"]["security"] = dict(collateralReady=value, guarantorReady=value)
    query = build_query(Profile.model_validate(payload["profile"]))
    for label in ("collateralReadyQuery", "guarantorReadyQuery"):
        if LABELS[label][value]:
            assert LABELS[label][value] in query
    assert "UNKNOWN" not in query and query.count("query:") == 1
    assert "предпочита" not in query


@pytest.mark.parametrize("collateral", ["NONE", "REQUIRED", "CONDITIONAL"])
@pytest.mark.parametrize("guarantor", ["NONE", "REQUIRED", "CONDITIONAL"])
def test_passage_security_requirements(payload, collateral, guarantor):
    raw = payload["candidates"][0]["product"]
    raw.update(
        collateralRequirement=collateral,
        guarantorRequirement=guarantor,
        securityNote="Требования уточняются.",
    )
    product = Product.model_validate(raw)
    text = build_passage(product)
    assert LABELS["collateralRequirementPassage"][collateral] in text
    assert LABELS["guarantorRequirementPassage"][guarantor] in text
    assert text.endswith("Требования уточняются.")
    for value in (product.id, product.version, product.name):
        assert value not in text
    assert ".." not in text and text.count("passage:") == 1


@pytest.mark.parametrize("field", ["collateralRequirement", "guarantorRequirement"])
@pytest.mark.parametrize("note", [None, "", "  \n "])
def test_conditional_requires_note(payload, field, note):
    raw = payload["candidates"][0]["product"]
    raw.update({field: "CONDITIONAL", "securityNote": note})
    with pytest.raises(ValidationError):
        Product.model_validate(raw)


def test_optional_defaults_and_determinism(payload):
    raw = payload["profile"]
    raw["business"]["sector"] = None
    raw["request"].pop("description", None)
    raw["request"]["usageMode"] = "UNKNOWN"
    raw["security"] = dict(collateralReady="UNKNOWN", guarantorReady="UNKNOWN")
    assert build_query(Profile.model_validate(raw)).startswith("query: Цель финансирования")
    assert "None" not in build_query(Profile.model_validate(raw))
    product = payload["candidates"][0]["product"]
    for key in ("targetSectors", "specialization", "securityNote"):
        product.pop(key, None)
    product.update(collateralRequirement="NONE", guarantorRequirement="NONE")
    assert Product.model_validate(product).targetSectors == []
    assert "Специализация" not in build_passage(Product.model_validate(product))
    product["purposes"] = ["EQUIPMENT", "CASH_GAP"]
    product["usageModes"] = ["ONE_TIME", "IN_PARTS"]
    product["targetSectors"] = ["TRADE", "IT"]
    p1 = Product.model_validate(product)
    other = copy.deepcopy(product)
    for field in ("purposes", "usageModes", "targetSectors"):
        other[field].reverse()
    assert build_passage(p1) == build_passage(Product.model_validate(other))
    assert clean_text("  е\u0308\x00  a\n b ") == "ё a b"
    raw["request"]["description"] = "  "
    assert Profile.model_validate(raw).request.description is None


@pytest.mark.parametrize("sector", ["OTHER", "UNKNOWN"])
def test_unknown_sector_omitted(payload, sector):
    payload["profile"]["business"]["sector"] = sector
    assert "Бизнес занимается" not in build_query(Profile.model_validate(payload["profile"]))


@pytest.mark.parametrize("array", ["purposes", "usageModes", "targetSectors"])
def test_duplicate_codes_rejected(payload, array):
    raw = payload["candidates"][0]["product"]
    values = {"purposes": "EQUIPMENT", "usageModes": "ONE_TIME", "targetSectors": "TRADE"}
    raw[array] = [values[array]] * 2
    with pytest.raises(ValidationError):
        Product.model_validate(raw)
