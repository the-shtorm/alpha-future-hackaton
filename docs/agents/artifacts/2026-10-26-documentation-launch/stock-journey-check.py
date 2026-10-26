"""Four synthetic journeys against an already running isolated stock Docker Compose stack."""

import argparse
import copy
import http.cookiejar
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import uuid4

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "compose.yaml").is_file())

def main():
    parser = argparse.ArgumentParser(description="Four synthetic journeys against an already running isolated stock Compose stack")
    parser.add_argument("--env-file",type=Path,required=True)
    parser.add_argument("--api-url",default="http://localhost:8080")
    parser.add_argument("--frontend-url",default="http://localhost:3000")
    parser.add_argument("--output",type=Path,default=ROOT/"work/documentation-launch/stock-journey-results.json")
    args=parser.parse_args()
    args.cookie_auth=True
    args.source_smoke=False
    env=dict(line.split("=",1) for line in args.env_file.read_text().splitlines() if line and not line.startswith("#") and "=" in line)
    java, frontend = args.api_url, args.frontend_url
    opener=build_opener(ProxyHandler({})); browsers={}
    pdf_bytes=(ROOT/"docs/demo/sample-document.pdf").read_bytes()
    def call(url, method="GET", body=None, token=None, headers=None, raw=False):
        values = {"Content-Type": "application/json", **(headers or {})}
        selected = opener
        if token in browsers:
            selected, csrf = browsers[token]
            assert url.startswith(java + "/")
            url = frontend + "/api" + url.removeprefix(java)
            if method not in ("GET", "HEAD", "OPTIONS"):
                values[csrf["headerName"]] = csrf["token"]
        elif token:
            values["Authorization"] = "Bearer " + token
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        with selected.open(Request(url, data=data, method=method, headers=values), timeout=30) as response:
            result = response.read()
            return result if raw else json.loads(result)

    def login(name):
        body = {"login": name, "password": env["DEMO_BANK_PASSWORD" if name == "demo-bank" else "DEMO_PASSWORD"]}
        if not args.cookie_auth:
            return call(java + "/auth/login", "POST", body)["accessToken"]
        jar = http.cookiejar.CookieJar()
        browser = build_opener(ProxyHandler({}), HTTPCookieProcessor(jar))

        def request(path, payload=None, csrf=None):
            headers = {"Content-Type": "application/json"}
            if csrf:
                headers[csrf["headerName"]] = csrf["token"]
            data = json.dumps(payload).encode() if payload is not None else None
            with browser.open(
                Request(frontend + "/api" + path, data=data, headers=headers), timeout=30
            ) as response:
                return json.load(response)

        csrf = request("/auth/csrf")
        try:
            request("/auth/session", body)
        except HTTPError as error:
            assert error.code == 403
            error.close()
        else:
            raise AssertionError("Cookie login must reject missing CSRF")
        result = request("/auth/session", body, csrf)
        assert result["status"] == "ok" and "accessToken" not in result
        assert any(
            cookie.name == "ALPHA_SESSION" and cookie.has_nonstandard_attr("HttpOnly") for cookie in jar
        )
        browsers[name] = (browser, request("/auth/csrf"))
        call(java + "/me", token=name)
        return name

    assert b"<html" in call(frontend + "/",raw=True).lower()
    call(frontend + "/api/health")
    owner, bank=login("demo-owner"),login("demo-bank")
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
            ).encode().replace(b"%PDF-1.7\nacceptance fixture", pdf_bytes)
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
        listed = call(path + "/documents", token=owner)
        assert listed and all(row["current"] for row in listed)
        first = listed[0]
        first_id = str(first.get("versionId") or first.get("id"))
        assert call(path + "/documents/" + first_id, token=owner, raw=True) == pdf_bytes
        if scenario == "APPROVED":
            boundary = "replace-" + uuid4().hex
            payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="typeCode"\r\n\r\n{first["typeCode"]}\r\n'
                       f'--{boundary}\r\nContent-Disposition: form-data; name="replacesVersionId"\r\n\r\n{first_id}\r\n'
                       f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="replacement.pdf"\r\nContent-Type: application/pdf\r\n\r\n').encode() + pdf_bytes + f'\r\n--{boundary}--\r\n'.encode()
            replacement = call(path + "/documents", "POST", payload, owner, {"Content-Type":"multipart/form-data; boundary=" + boundary})
            versions = call(path + "/documents", token=owner)
            assert len(versions) == len(listed)+1
            assert next(row for row in versions if str(row.get("versionId") or row.get("id")) == first_id)["current"] is False
            call(java + "/bank/applications/" + app["id"] + "/documents/" + replacement["versionId"] + "/review", "POST", {"result":"PASS","reason":"Synthetic current-version review"}, bank)
        call(java + "/bank/applications/" + app["id"] + "/assign", "POST", {}, bank)
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
    evidence={"compose":"compose.yaml","cookieCsrf":True,"actualPdfUploadDownloadAndReplacement":True,"outcomes":outcomes}
    out=args.output; out.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps(evidence,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
