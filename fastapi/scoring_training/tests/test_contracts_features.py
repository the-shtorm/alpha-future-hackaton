import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
from app.scoring.contracts import (
    FEATURE_VERSION,
    BusinessAge,
    BusinessType,
    ScoringRequest,
    ScoringResponse,
    probability_score,
)
from app.scoring.features import (
    BUSINESS_AGES,
    BUSINESS_TYPES,
    CATEGORICAL,
    FEATURES,
    NUMERIC,
    age_category,
    canonical_features,
    request_features,
)
from pydantic import ValidationError


@pytest.fixture
def scoring_payload():
    return {
        "schemaVersion": "sba-scoring-1",
        "requestId": str(uuid4()),
        "loanAmountUsd": "125000.00",
        "termMonths": 120,
        "initialInterestRatePct": "28.00",
        "interestRateType": "FIXED",
        "isRevolving": False,
        "hasCollateral": True,
        "businessType": "CORPORATION",
        "businessAgeCategory": "Existing, 5 or more years",
        "naicsCode": "445110",
    }


@pytest.fixture
def csv_features():
    return {
        "GrossApproval": "125000.00",
        "InitialInterestRate": "28.00",
        "FixedorVariableInterestInd": "F",
        "TermInMonths": "120.0",
        "NaicsCode": "445110",
        "BusinessType": "1.0",
        "BusinessAge": "7.0",
        "RevolverStatus": "N",
        "CollateralInd": "Y",
        "LoanStatus": "1",
        "ApprovalFY": "2010",
        "ChargeOffDate": "2020-01-01",
    }


@pytest.mark.parametrize("mode", ["full", "prefix2"])
@pytest.mark.parametrize("age", list(BusinessAge))
@pytest.mark.parametrize("kind", list(BusinessType))
def test_csv_and_http_have_identical_vectors(scoring_payload, csv_features, mode, age, kind):
    scoring_payload.update(businessAgeCategory=age, businessType=kind)
    csv_features.update(BusinessAge=BUSINESS_AGES[age], BusinessType=BUSINESS_TYPES[kind])
    actual = request_features(ScoringRequest.model_validate(scoring_payload), mode)
    assert actual == canonical_features(csv_features, mode)
    assert tuple(actual) == FEATURES
    assert set(actual) == set(NUMERIC) | set(CATEGORICAL)
    assert actual["InitialInterestRate"] == 28
    assert actual["NaicsCode"] == ("445110" if mode == "full" else "44")
    assert "LoanStatus" not in actual and "ApprovalFY" not in actual


@pytest.mark.parametrize(
    "rate_type,revolving,collateral", [("VARIABLE", True, False), ("FIXED", False, True)]
)
def test_flags_zero_rate_and_leading_naics_zeros(scoring_payload, rate_type, revolving, collateral):
    scoring_payload.update(
        initialInterestRatePct="0",
        naicsCode="012345",
        interestRateType=rate_type,
        isRevolving=revolving,
        hasCollateral=collateral,
    )
    values = request_features(ScoringRequest.model_validate(scoring_payload))
    assert values["InitialInterestRate"] == 0
    assert values["NaicsCode"] == "012345"
    assert values["FixedorVariableInterestInd"] == ("F" if rate_type == "FIXED" else "V")
    assert values["RevolverStatus"] == ("Y" if revolving else "N")
    assert values["CollateralInd"] == ("Y" if collateral else "N")


@pytest.mark.parametrize(
    "field,value",
    [
        ("schemaVersion", "sba-scoring-2"),
        ("requestId", "not-a-uuid"),
        ("loanAmountUsd", 125000),
        ("loanAmountUsd", "0.00"),
        ("loanAmountUsd", "1.0"),
        ("loanAmountUsd", "1e3"),
        ("loanAmountUsd", "NaN"),
        ("loanAmountUsd", "-1.00"),
        ("termMonths", True),
        ("termMonths", 12.0),
        ("termMonths", "12"),
        ("termMonths", 0),
        ("termMonths", 361),
        ("initialInterestRatePct", 28),
        ("initialInterestRatePct", "-1"),
        ("initialInterestRatePct", "0.000001"),
        ("initialInterestRatePct", "Infinity"),
        ("initialInterestRatePct", "2.8e1"),
        ("interestRateType", "F"),
        ("isRevolving", 0),
        ("hasCollateral", "false"),
        ("businessType", "LLC"),
        ("businessAgeCategory", "UNKNOWN"),
        ("naicsCode", 445110),
        ("naicsCode", "44511"),
        ("naicsCode", "４４５１１０"),
        ("extra", "disallowed"),
    ],
)
def test_http_rejects_invalid_or_coerced_values(scoring_payload, field, value):
    scoring_payload[field] = value
    with pytest.raises(ValidationError):
        ScoringRequest.model_validate(scoring_payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("GrossApproval", None),
        ("GrossApproval", "NaN"),
        ("GrossApproval", "Infinity"),
        ("GrossApproval", "1e999"),
        ("GrossApproval", True),
        ("GrossApproval", "0"),
        ("InitialInterestRate", "-1"),
        ("TermInMonths", "1.5"),
        ("TermInMonths", "0"),
        ("BusinessType", "1.2"),
        ("BusinessType", "4"),
        ("BusinessAge", "0"),
        ("FixedorVariableInterestInd", "FIXED"),
        ("RevolverStatus", "true"),
        ("CollateralInd", ""),
        ("NaicsCode", 445110),
        ("NaicsCode", "445110.0"),
    ],
)
def test_csv_rejects_missing_unknown_and_invalid_values(csv_features, field, value):
    csv_features[field] = value
    with pytest.raises(ValueError):
        canonical_features(csv_features)


def test_no_silent_population_filter_or_unknown_transform(csv_features):
    csv_features["TermInMonths"] = "480"
    assert canonical_features(csv_features)["TermInMonths"] == 480
    with pytest.raises(ValueError, match="NAICS"):
        canonical_features(csv_features, "unknown")
    del csv_features["BusinessAge"]
    with pytest.raises(ValueError, match="Missing"):
        canonical_features(csv_features)


@pytest.mark.parametrize(
    "months,code",
    [
        (0, "2"),
        (11, "2"),
        (12, "3"),
        (23, "3"),
        (24, "4"),
        (35, "4"),
        (36, "5"),
        (47, "5"),
        (48, "6"),
        (59, "6"),
        (60, "7"),
        (240, "7"),
    ],
)
def test_backend_age_boundaries(months, code):
    assert BUSINESS_AGES[age_category(months)] == code


@pytest.mark.parametrize("months", [-1, True, 12.0])
def test_invalid_age(months):
    with pytest.raises(ValueError):
        age_category(months)


@pytest.mark.parametrize(
    "probability,score", [(0, 100), (1, 0), (0.155, 85), (Decimal("0.005"), 100), (0.35, 65), (0.15, 85)]
)
def test_half_up_score(probability, score):
    assert probability_score(probability) == score


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.01, 1.01])
def test_invalid_probability(probability):
    with pytest.raises(ValueError):
        probability_score(probability)


def test_response_and_published_schemas(scoring_payload):
    response = dict(
        schemaVersion="sba-scoring-1",
        requestId=scoring_payload["requestId"],
        sbaDefaultProbability=0.155,
        score=85,
        modelVersion="fixture-only",
        featureVersion=FEATURE_VERSION,
        calibrationVersion="sigmoid-fixture-only",
        domainStatus="IN_RANGE",
        isDemo=True,
        warnings=[],
    )
    for model, payload, filename in (
        (ScoringRequest, scoring_payload, "scoring-request.schema.json"),
        (ScoringResponse, response, "scoring-response.schema.json"),
    ):
        schema = json.loads((Path(__file__).resolve().parents[2] / "contracts" / filename).read_text())
        assert schema == model.model_json_schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(payload, schema)
        assert set(schema["required"]) == set(model.model_fields)
        assert schema["additionalProperties"] is False
        model.model_validate(payload)
    response["score"] = 84
    with pytest.raises(ValidationError, match="Score"):
        ScoringResponse.model_validate(response)
