"""Check a running server using only the standard library (also usable in the runtime image)."""

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--java", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    with urlopen(base + "/health/ready", timeout=5) as response:
        assert response.status == 200
    body = Path("examples/java-rank-request.json" if args.java else "examples/rank-request.json").read_bytes()
    endpoint = "/api/v1/recommendations/rank-java" if args.java else "/api/v1/recommendations/rank"
    auth = (
        {"Authorization": "Bearer " + os.environ["ML_INTERNAL_API_KEY"]}
        if args.java
        else {"X-Internal-API-Key": os.environ["ML_INTERNAL_API_KEY"]}
    )
    request = Request(
        base + endpoint,
        data=body,
        headers={"Content-Type": "application/json", **auth},
    )
    with urlopen(request, timeout=60) as response:
        result = json.load(response)
    assert len(result["results"]) == len(json.loads(body)["candidates"])
    if args.java:
        assert set(result["metadata"]) == {
            "model",
            "modelVersion",
            "queryTemplateVersion",
            "passageTemplateVersion",
        }
    else:
        assert result["metadata"]["rankingMode"] == "semantic_only"
    print(
        json.dumps(
            {
                "httpSmoke": "passed",
                "modelRevision": result["metadata"]["modelVersion" if args.java else "modelRevision"],
                "productIds": [p["productId"] for p in result["results"]],
            }
        )
    )


if __name__ == "__main__":
    main()
