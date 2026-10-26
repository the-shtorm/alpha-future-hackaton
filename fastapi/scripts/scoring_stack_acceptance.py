"""Disposable four-service HTTP credit journey with real E5 and SBA packages."""

import argparse
import copy
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "fastapi/experiments/sba-full-stack-v2.json")
    parser.add_argument(
        "--source-smoke",
        action="store_true",
        help="Check HF/source integration with decline and missing-data journeys, without v1 approval fixtures",
    )
    args = parser.parse_args()
    project = "sba-journey-" + secrets.token_hex(5)
    env = dict(os.environ)
    env.update(
        ML_TEST_IMAGE="alpha-future-fastapi:scoring-acceptance",
        ML_TEST_BACKEND_IMAGE="alpha-future-backend:scoring-acceptance",
        ML_TEST_FRONTEND_IMAGE="alpha-future-frontend:scoring-acceptance",
        ML_TEST_MODEL_VARIANT="finetuned",
        ML_TEST_MODEL_PATH=str(ROOT / "fastapi/models/e5-credit-finetune-v1/final"),
        ML_TEST_SCORING_ENABLED="true",
        ML_TEST_SCORING_MODEL_PATH=os.getenv("SCORING_MODEL_PATH", "thedauns/sba-scoring-v2"),
    )
    for name in ("API_KEY", "DB_PASSWORD", "DB_APP_PASSWORD", "DB_MIGRATOR_PASSWORD", "DEMO_PASSWORD"):
        env["ML_TEST_" + name] = secrets.token_hex(24)
    base = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(ROOT / "compose.ml-test.yaml"),
        "--profile",
        "scoring",
    ]
    opener = build_opener(ProxyHandler({}))

    def compose(*arguments):
        result = subprocess.run([*base, *arguments], cwd=ROOT, env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(
                "Isolated Compose operation failed: " + " ".join(arguments[:2]) + "\n" + result.stderr[-2000:]
            )
        return result.stdout.strip()

    def address(service, port):
        value = compose("port", service, str(port))
        assert value.startswith("127.0.0.1:")
        return "http://" + value

    def call(url, method="GET", body=None, token=None, headers=None, raw=False):
        values = {"Content-Type": "application/json", **(headers or {})}
        if token:
            values["Authorization"] = "Bearer " + token
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        with opener.open(Request(url, data=data, method=method, headers=values), timeout=30) as response:
            result = response.read()
            return result if raw else json.loads(result)

    try:
        compose("up", "-d", "--wait", "--wait-timeout", "180")
        java, ml, frontend = address("backend", 8080), address("fastapi", 8000), address("frontend", 8080)
        deadline = time.monotonic() + 90
        while True:
            try:
                call(java + "/health")
                break
            except (URLError, TimeoutError, ConnectionError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        assert b"<html" in call(frontend + "/", raw=True).lower()
        call(frontend + "/api/health")
        owner = call(
            java + "/auth/login", "POST", {"login": "demo-owner", "password": env["ML_TEST_DEMO_PASSWORD"]}
        )["accessToken"]
        bank = call(
            java + "/auth/login", "POST", {"login": "demo-bank", "password": env["ML_TEST_DEMO_PASSWORD"]}
        )["accessToken"]
        stable = next(
            row for row in call(java + "/demo/scenarios", token=owner)["items"] if row["code"] == "STABLE"
        )
        products = {row["code"]: row for row in call(java + "/products?size=50", token=owner)["content"]}
        now = datetime.now(timezone.utc)
        call(
            java + "/bank/macroeconomic-contexts",
            "POST",
            {
                "keyRatePct": "10.00000",
                "validFrom": (now - timedelta(seconds=1)).isoformat(),
                "expiresAt": (now + timedelta(days=1)).isoformat(),
                "sourceCode": "SCORING_ACCEPTANCE_FIXTURE_NOT_CBR",
            },
            bank,
        )
        outcomes = []
        scenarios = (
            ("DECLINED", "REQUEST_INFO")
            if args.source_smoke
            else ("APPROVED", "COUNTEROFFERED", "DECLINED", "REQUEST_INFO")
        )
        for scenario in scenarios:
            # Synthetic branch fixtures exercise the frozen v2/Java integration;
            # they are not a held-out ML quality evaluation or threshold selection.
            product_code = "P07" if scenario == "APPROVED" else "P01"
            product = products[product_code]
            answers = copy.deepcopy(stable["preliminaryAnswers"])
            additions = copy.deepcopy(stable["applicationAdditionalAnswers"])
            answers["request"]["amount"] = "1000000.00" if scenario == "COUNTEROFFERED" else "300000.00"
            if scenario == "APPROVED":
                answers["request"].update(amount="500000.00", termMonths=60, purpose="EQUIPMENT")
                answers["security"]["collateralReady"] = "YES"
                additions["security"]["collateralValue"] = "1000000.00"
                additions["project"]["ownContributionPct"] = "20.00"
            if scenario == "COUNTEROFFERED":
                answers["financial"]["revenue"] = "6000000.00"
                additions["financial"]["monthlyDebtPayment"] = "170000.00"
            if scenario == "DECLINED":
                answers["request"]["termMonths"] = 6
            if scenario == "REQUEST_INFO":
                additions["financial"].pop("monthlyDebtPayment", None)
            profile = call(
                java + "/selection-profiles",
                "POST",
                {"partyId": stable["partyId"], "answers": answers},
                owner,
            )
            prefix = java + "/selection-profiles/" + profile["id"]
            automatic = call(prefix + "/automatic-selection", "POST", {}, owner)
            assert automatic["rankingStatus"] == "READY"
            assert sum(row["isRecommended"] for row in automatic["results"]) <= 3
            eligible = call(prefix + "/eligibility", "POST", {}, owner)
            selected = call(
                prefix + "/selected-product",
                "PUT",
                {
                    "expectedVersion": profile["rowVersion"],
                    "runId": eligible["runId"],
                    "productVersionId": product["versionId"],
                },
                owner,
            )
            app = call(
                java + "/applications",
                "POST",
                {
                    "profileId": selected["id"],
                    "expectedProfileVersion": selected["rowVersion"],
                    "answers": additions,
                },
                owner,
            )
            path = java + "/applications/" + app["id"]
            for requirement in call(path + "/requirements", token=owner):
                boundary = "sba-" + uuid4().hex
                content = (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="typeCode"\r\n\r\n{requirement["type_code"]}\r\n'
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="fixture.pdf"\r\nContent-Type: application/pdf\r\n\r\n%PDF-1.7\nacceptance fixture\r\n--{boundary}--\r\n'
                ).encode()
                document = call(
                    path + "/documents",
                    "POST",
                    content,
                    owner,
                    {"Content-Type": "multipart/form-data; boundary=" + boundary},
                )
                call(
                    java
                    + "/bank/applications/"
                    + app["id"]
                    + "/documents/"
                    + document["versionId"]
                    + "/review",
                    "POST",
                    {"result": "PASS", "reason": "Synthetic acceptance verification"},
                    bank,
                )
            app = call(path, token=owner)
            call(
                path + "/submit",
                "POST",
                {"expectedVersion": app["rowVersion"], "confirmed": True},
                owner,
                {"Idempotency-Key": uuid4().hex},
            )
            journey = call(java + "/bank/applications/" + app["id"] + "/process", "POST", {}, bank)
            assert journey["decision"]["kind"] == scenario, (scenario, journey["decision"]["kind"])
            conditions = journey["decision"]["conditions"]
            entry = {
                "decision": scenario,
                "productCode": product_code,
                "rankingStatus": automatic["rankingStatus"],
                "assessmentCount": len(conditions.get("assessmentIds", [])),
            }
            if scenario != "REQUEST_INFO":
                assert conditions["modelVersion"] == "sba-scoring-v2"
                assert conditions["policyVersion"] == "data-policy-3.0-sba-annuity-1"
                assert {"TERM_HISTORY_UNCONFIRMED", "RATE_OUT_OF_RANGE", "SBA_US_TO_RU_DEMO"} <= set(
                    conditions["warnings"]
                )
                entry.update(
                    probability=conditions["sbaDefaultProbability"],
                    finalRiskScore=conditions["finalRiskScore"],
                    pti=conditions["pti"],
                    selectedVariant=conditions["selectedVariant"],
                )
            if scenario in ("APPROVED", "COUNTEROFFERED"):
                if scenario == "COUNTEROFFERED":
                    proposal = journey["counteroffer"]
                    call(
                        path + "/counteroffers/accept",
                        "POST",
                        {
                            "proposalId": proposal["id"],
                            "termsSha256": proposal["termsSha256"],
                            "confirmed": True,
                        },
                        owner,
                    )
                else:
                    call(
                        path + "/offers/accept",
                        "POST",
                        {"offerId": journey["offer"]["id"], "confirmed": True},
                        owner,
                    )
                call(path + "/contract/sign", "POST", {"confirmed": True}, owner)
                journey = call(
                    java + "/bank/applications/" + app["id"] + "/disburse", "POST", {"confirmed": True}, bank
                )
                assert journey["application"]["status"] == "DISBURSED"
                entry["finalStatus"] = "DISBURSED"
            outcomes.append(entry)
        audit = json.loads(
            compose(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "postgres",
                "-d",
                "recsys_acceptance",
                "-tAc",
                "SELECT json_build_object('assessments',(SELECT count(*) FROM credit.assessment_run),'linkedDecisions',(SELECT count(*) FROM credit.credit_decision WHERE assessment_id IS NOT NULL),'models',(SELECT json_agg(DISTINCT model_version) FROM credit.assessment_run))",
            )
        )
        expected_assessments, expected_links = (1, 1) if args.source_smoke else (4, 3)
        assert audit["assessments"] == expected_assessments and audit["linkedDecisions"] == expected_links
        benchmark_path = (
            args.output.with_name(args.output.stem + "-http.json")
            if args.source_smoke
            else ROOT / "fastapi/experiments/sba-scoring-http-acceptance-v2.json"
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "fastapi/scripts/scoring_acceptance.py"),
                "--url",
                ml,
                "--output",
                str(benchmark_path),
            ],
            env={**env, "ML_INTERNAL_API_KEY": env["ML_TEST_API_KEY"]},
            check=True,
            stdout=subprocess.DEVNULL,
        )
        stats = {}
        for service in ("frontend", "backend", "fastapi", "postgres"):
            container = compose("ps", "-q", service)
            limits = int(
                subprocess.check_output(
                    ["docker", "inspect", "--format", "{{.HostConfig.Memory}}", container], text=True
                )
            )
            current, peak = map(
                int,
                compose(
                    "exec",
                    "-T",
                    service,
                    "cat",
                    "/sys/fs/cgroup/memory.current",
                    "/sys/fs/cgroup/memory.peak",
                ).split(),
            )
            stats[service] = {"currentBytes": current, "peakBytes": peak, "limitBytes": limits}
        reserve, budget = 2 * 1024**3, 6 * 1024**3
        memory_budget = {
            "budgetBytes": budget,
            "osReserveBytes": reserve,
            "sumContainerLimitsBytes": sum(row["limitBytes"] for row in stats.values()),
            "sumObservedPeaksBytes": sum(row["peakBytes"] for row in stats.values()),
            "osReserveIsMeasured": False,
        }
        assert memory_budget["sumContainerLimitsBytes"] + reserve <= budget
        report = {
            "passed": True,
            "scope": "source-smoke" if args.source_smoke else "four-decision-journey",
            "transport": "real nginx HTTP -> Java 21 -> FastAPI CPU E5/SBA -> PostgreSQL 17",
            "cases": outcomes,
            "audit": audit,
            "scoringInfo": call(ml + "/api/v1/scoring/model-info", token=env["ML_TEST_API_KEY"]),
            "containerStats": stats,
            "memoryBudget": memory_budget,
            "httpBenchmark": json.loads(benchmark_path.read_text()),
            "isDemo": True,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps({"passed": True, "decisions": [row["decision"] for row in outcomes], "audit": audit})
        )
    except Exception:
        failure = ROOT / "fastapi/reports/sba-full-stack-failure.log"
        failure.parent.mkdir(parents=True, exist_ok=True)
        failure.write_text(compose("logs", "--no-color", "--tail", "80"), encoding="utf-8")
        raise
    finally:
        assert project.startswith("sba-journey-") and len(project) == 22
        compose("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
