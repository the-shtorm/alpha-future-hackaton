import copy
import json
from uuid import uuid4

import jsonschema
import pytest
from conftest import ROOT

URL = "/api/v1/recommendations/rank-java"
BEARER = {"Authorization": "Bearer test-key"}


@pytest.fixture
def java_payload():
    return json.loads((ROOT / "examples/java-rank-request.json").read_text(encoding="utf-8"))


def test_java_reply_matches_contract_and_preserves_conditions(client, java_payload, encoder):
    response = client.post(URL, json=java_payload, headers=BEARER)
    assert response.status_code == 200, response.text
    reply = response.json()
    jsonschema.validate(
        reply,
        json.loads((ROOT / "contracts/java-rank-response.schema.json").read_text(encoding="utf-8")),
        format_checker=jsonschema.FormatChecker(),
    )
    assert set(reply["metadata"]) == {
        "model",
        "modelVersion",
        "queryTemplateVersion",
        "passageTemplateVersion",
    }
    assert reply["metadata"]["modelVersion"] == encoder.revision
    assert len(reply["results"]) == len(java_payload["candidates"])
    originals = {c["productId"]: c for c in java_payload["candidates"]}
    for item in reply["results"]:
        original = originals[item["productId"]]
        assert item["productVersion"] == original["productVersion"]
        assert item["pendingConditions"] == original["pendingConditions"]
        assert item["eligibilityStatus"] == original["eligibilityStatus"]
    texts = " ".join(t for batch in encoder.calls for t in batch)
    assert "транспорт и логистика" in texts
    assert "Synthetic condition" not in texts and "LOGISTICS" not in texts
    assert java_payload["candidates"][0]["pendingConditions"][0]["message"].startswith("  ")


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_null_optional_answers_omit_only_sentences(client, java_payload, encoder, missing):
    query = java_payload["queryFields"]
    if missing:
        query.pop("business")
        query.pop("security")
    else:
        query["business"]["sector"] = None
        query["security"] = {"collateralReady": None, "guarantorReady": None}
    assert client.post(URL, json=java_payload, headers=BEARER).status_code == 200
    text = encoder.calls[-1][0]
    assert "Бизнес занимается" not in text and "залог" not in text and "поручител" not in text
    assert "Цель финансирования" in text


@pytest.mark.parametrize(
    "auth,code",
    [
        ({}, "AUTH_REQUIRED"),
        ({"X-Internal-API-Key": "test-key"}, "AUTH_REQUIRED"),
        ({"Authorization": "Basic test-key"}, "AUTH_INVALID"),
        ({"Authorization": "Bearer bad"}, "AUTH_INVALID"),
    ],
)
def test_java_requires_internal_bearer(client, java_payload, auth, code):
    response = client.post(URL, json=java_payload, headers=auth)
    assert response.status_code == 401 and response.json()["error"]["code"] == code


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "semantics",
        "dictionary",
        "sector",
        "readiness",
        "uuid",
        "product_id",
        "product_version",
        "duplicate",
        "condition_extra",
        "extra_financial",
        "purpose_missing",
        "too_many",
    ],
)
def test_invalid_java_contract_rejected_before_model(client, java_payload, encoder, change):
    c = java_payload["candidates"][0]
    if change == "schema":
        java_payload["schemaVersion"] = "unsupported"
    elif change == "semantics":
        java_payload["semanticsVersion"] = "unknown"
    elif change == "dictionary":
        java_payload["dictionaries"]["version"] = "unknown"
    elif change == "sector":
        java_payload["queryFields"]["business"]["sector"] = "TRANSPORT"
    elif change == "readiness":
        java_payload["queryFields"]["security"]["collateralReady"] = False
    elif change == "uuid":
        java_payload["requestId"] = "not-a-uuid"
    elif change == "product_id":
        c["productId"] = str(uuid4())
    elif change == "product_version":
        c["productVersion"] = str(uuid4())
    elif change == "duplicate":
        java_payload["candidates"].append(copy.deepcopy(c))
    elif change == "condition_extra":
        c["pendingConditions"][0]["comment"] = "not permitted"
    elif change == "extra_financial":
        java_payload["queryFields"]["financial"] = {"revenue": "1000.00"}
    elif change == "purpose_missing":
        del java_payload["queryFields"]["request"]["purpose"]
    else:
        java_payload["candidates"] = [copy.deepcopy(c)] * 101
    response = client.post(URL, json=java_payload, headers=BEARER)
    assert response.status_code == 422, response.text
    assert not encoder.calls


def test_java_empty_not_ready_and_encoder_failure(client, application, java_payload, encoder):
    original = java_payload["candidates"]
    java_payload["candidates"] = []
    response = client.post(URL, json=java_payload, headers=BEARER)
    assert response.status_code == 200 and response.json()["results"] == [] and not encoder.calls
    application.state.ready = False
    assert client.post(URL, json=java_payload, headers=BEARER).status_code == 503
    application.state.ready = True
    java_payload["candidates"] = original
    encoder.encode = lambda _: (_ for _ in ()).throw(RuntimeError("PRIVATE_FAIL"))
    response = client.post(URL, json=java_payload, headers=BEARER)
    assert response.status_code == 500 and "PRIVATE_FAIL" not in response.text


def test_long_many_conditions_are_opaque_and_unchanged(client, java_payload, encoder):
    c = java_payload["candidates"][0]
    c["product"]["targetSectors"] = ["LOGISTICS"]
    c["pendingConditions"] = [
        {
            "code": "x",
            "field": "",
            "result": "REVIEW",
            "message": " " * 400,
            "actual": [False, 0, None, "  unchanged  ", {"list": []}],
            "expected": {"n": 123456789012345678901234567890},
        }
        for _ in range(25)
    ]
    response = client.post(URL, json=java_payload, headers=BEARER)
    assert response.status_code == 200, response.text
    item = next(r for r in response.json()["results"] if r["productId"] == c["productId"])
    assert item["pendingConditions"] == c["pendingConditions"]
    assert "Специализация по отраслям: транспорт и логистика." in encoder.calls[0][0]
