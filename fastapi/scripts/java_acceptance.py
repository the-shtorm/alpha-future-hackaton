"""Run a disposable real Java -> E5 -> Java acceptance stack, then remove only that stack."""

import argparse
import copy
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def call(url, method="GET", body=None, token=None, internal_key=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if internal_key:
        headers["X-Internal-API-Key"] = internal_key
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    with urlopen(Request(url, data=data, method=method, headers=headers), timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "work/ml-acceptance/java-e2e.json")
    parser.add_argument("--max-cosine-distance", type=float, default=None)
    args = parser.parse_args()
    project = "recsys-java-" + secrets.token_hex(5)
    env = dict(os.environ)
    env["ML_TEST_MAX_COSINE_DISTANCE"] = (
        str(args.max_cosine_distance) if args.max_cosine_distance is not None else ""
    )
    for name in ("API_KEY", "DB_PASSWORD", "DB_APP_PASSWORD", "DB_MIGRATOR_PASSWORD", "DEMO_PASSWORD"):
        env["ML_TEST_" + name] = secrets.token_hex(24)
    base = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.ml-test.yaml")]

    def compose(*arguments):
        result = subprocess.run(
            [*base, *arguments],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            # Do not print environment/secrets or render Compose config.
            raise RuntimeError(
                "Compose operation failed: " + " ".join(arguments[:2]) + "\n" + result.stderr[-3000:]
            )
        return result.stdout.strip()

    try:
        compose("up", "-d", "--wait", "--wait-timeout", "180")

        def address(service, port):
            container = compose("ps", "-q", service)
            published = json.loads(
                subprocess.check_output(
                    ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container], text=True
                )
            )
            binding = published[f"{port}/tcp"][0]
            assert binding["HostIp"] == "127.0.0.1" and binding["HostPort"].isdigit()
            return "http://127.0.0.1:" + binding["HostPort"]

        java_url = address("backend", 8080)
        ml_url = address("fastapi", 8000)
        threshold = call(ml_url + "/api/v1/model-info", internal_key=env["ML_TEST_API_KEY"])[
            "maxCosineDistance"
        ]
        deadline = time.monotonic() + 90
        while True:
            try:
                call(java_url + "/health")
                break
            except (URLError, TimeoutError, ConnectionError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Isolated Java backend did not become ready") from None
                time.sleep(0.5)
        token = call(
            java_url + "/auth/login",
            "POST",
            {"login": "demo-owner", "password": env["ML_TEST_DEMO_PASSWORD"]},
        )["accessToken"]
        scenarios = call(java_url + "/demo/scenarios", token=token)["items"]
        stable = next(s for s in scenarios if s["code"] == "STABLE")
        results = []
        for variant in ("conditional", "unknown_context", "logistics", "empty"):
            answers = copy.deepcopy(stable["preliminaryAnswers"])
            answers["security"]["guarantorReady"] = "DISCUSS"
            if variant == "unknown_context":
                answers["business"].pop("sector", None)
                answers.pop("security", None)
                answers["request"].pop("description", None)
            elif variant == "logistics":
                answers["business"]["sector"] = "LOGISTICS"
            elif variant == "empty":
                answers["request"]["amount"] = "99999999999999999.99"
            profile = call(
                java_url + "/selection-profiles",
                "POST",
                {"partyId": stable["partyId"], "answers": answers},
                token,
            )
            prefix = java_url + "/selection-profiles/" + profile["id"]
            selection = call(prefix + "/automatic-selection", "POST", {}, token)
            expected = "EMPTY" if variant == "empty" else "READY"
            assert selection["rankingStatus"] == expected, (variant, selection["rankingStatus"])
            if variant != "empty":
                run = prefix + "/recommendations/" + selection["runId"]
                packet = call(run + "/ranking-export", token=token)
                imported = call(run + "/ranking-result", token=token)
                originals = {c["productId"]: c for c in packet["candidates"]}
                assert len(imported["results"]) == len(originals) > 0
                recommended_count = sum(r["isRecommended"] for r in imported["results"])
                assert recommended_count <= min(3, len(originals))
                for item in imported["results"]:
                    if item["isRecommended"]:
                        assert threshold is not None
                        # HTTP scores are rounded; boundary decisions use full precision inside ML.
                        assert item["similarityScore"] >= 1 - threshold - 0.000001
                if threshold is None:
                    assert recommended_count == 0
                assert set(imported["metadata"]) == {
                    "model",
                    "modelVersion",
                    "queryTemplateVersion",
                    "passageTemplateVersion",
                }
                assert imported["metadata"]["modelVersion"] == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
                for item in imported["results"]:
                    original = originals[item["productId"]]
                    assert item["pendingConditions"] == original["pendingConditions"]
                    assert item["eligibilityStatus"] == original["eligibilityStatus"]
                    assert item["productVersion"] == original["productVersion"]
                assert call(run + "/retry", "POST", {}, token)["results"] == selection["results"]
                # Direct ML request uses the actual Java envelope and is accepted idempotently by Java.
                wire = {
                    k: packet[k]
                    for k in (
                        "schemaVersion",
                        "requestId",
                        "topK",
                        "semanticsVersion",
                        "queryFields",
                        "dictionaries",
                    )
                }
                wire["candidates"] = [
                    {k: v for k, v in c.items() if k != "checks"} for c in packet["candidates"]
                ]
                reply = call(
                    ml_url + "/api/v1/recommendations/rank-java", "POST", wire, env["ML_TEST_API_KEY"]
                )
                assert call(run + "/ranking-result", "POST", reply, token)["results"] == imported["results"]
                if variant == "conditional":
                    assert any(r["pendingConditions"] for r in imported["results"])
                    call(
                        prefix,
                        "PATCH",
                        {
                            "expectedVersion": profile["rowVersion"],
                            "answers": {"request": {"description": "Synthetic changed request"}},
                        },
                        token,
                    )
                    try:
                        call(run + "/ranking-result", "POST", reply, token)
                    except HTTPError as error:
                        assert error.code == 409
                    else:
                        raise AssertionError("Stale import accepted")
            results.append(
                {
                    "variant": variant,
                    "status": selection["rankingStatus"],
                    "candidateCount": len(selection["results"]),
                    "recommendedCount": sum(r.get("isRecommended", False) for r in selection["results"]),
                }
            )
        stats = json.loads(
            subprocess.check_output(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", compose("ps", "-q", "fastapi")],
                text=True,
            )
        )
        report = {
            "passed": True,
            "maxCosineDistance": threshold,
            "transport": "real Java HTTP gateway -> CPU E5 -> Java immutable import",
            "cases": results,
            "mlContainerStats": stats,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    except Exception:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        (args.output.parent / "java-e2e-failure.log").write_text(
            compose("logs", "--no-color", "--tail", "100"), encoding="utf-8"
        )
        raise
    finally:
        # Project is generated locally with this prefix; never target the user's normal project.
        assert project.startswith("recsys-java-") and len(project) == 22
        compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
