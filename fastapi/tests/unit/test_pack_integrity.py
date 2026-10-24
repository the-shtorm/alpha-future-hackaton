import json
import tomllib

from conftest import ROOT

from app.schemas.requests import Product, RankRequest


def test_scenarios_and_products_are_valid_and_unconfirmed():
    products = json.loads((ROOT / "examples/demo-products.json").read_text(encoding="utf-8"))["products"]
    catalog = {p["id"]: p for p in products}
    for product in products:
        Product.model_validate(product)
    scenarios = json.loads((ROOT / "evaluation/scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    assert len(scenarios) == 40 and len({s["id"] for s in scenarios}) == 40
    for scenario in scenarios:
        assert scenario["labelStatus"] == "MANUAL_REVIEW_REQUIRED"
        assert set(scenario["proposedRelevantProductIds"]) <= set(scenario["candidateProductIds"])
        RankRequest.model_validate(
            {
                "requestId": scenario["id"],
                "profile": scenario["profile"],
                "candidates": [
                    {"product": catalog[pid], "eligibilityStatus": "ELIGIBLE", "pendingConditions": []}
                    for pid in scenario["candidateProductIds"]
                ],
            }
        )


def test_cpu_lock_has_windows_and_linux_wheels_and_no_cuda_packages():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = lock["package"]
    assert not any(p["name"].startswith("nvidia-") for p in packages)
    torch = next(p for p in packages if p["name"] == "torch")
    assert torch["version"].endswith("+cpu")
    urls = [w["url"] for w in torch["wheels"]]
    assert any("manylinux" in u and "x86_64" in u for u in urls)
    assert any("win_amd64" in u for u in urls)


def test_openapi_describes_key_errors_and_conditional_security(application):
    schema = application.openapi()
    rank = schema["paths"]["/api/v1/recommendations/rank"]["post"]
    assert rank["security"] == [{"APIKeyHeader": []}]
    for status in (401, 413, 422, 503, 500):
        assert rank["responses"][str(status)]["content"]["application/json"]["schema"]["$ref"].endswith(
            "ErrorResponse"
        )
    assert "allOf" in schema["components"]["schemas"]["Product"]
