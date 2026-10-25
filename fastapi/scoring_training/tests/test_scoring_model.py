"""Real, tiny fitted packages validate training/serving and integrity boundaries."""

import asyncio
import importlib.metadata
import platform
import threading
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
import pytest
from app.scoring.contracts import FEATURE_VERSION, ScoringRequest
from app.scoring.features import CATEGORICAL, FEATURES
from app.scoring.package import Bounds, ScoringPackage, digest
from app.scoring.runner import ScoringRunner
from scoring_training import train
from scoring_training.data import PREPARED_COLUMNS
from scoring_training.metrics import metrics, release_gates


def frame(rows=100):
    rng = np.random.default_rng(42)
    y = np.arange(rows) % 2
    return pd.DataFrame(
        {
            "GrossApproval": np.where(y, 150000, 10000) + rng.random(rows) * 1000,
            "InitialInterestRate": rng.uniform(4, 10, rows),
            "FixedorVariableInterestInd": ["F"] * rows,
            "TermInMonths": rng.integers(12, 60, rows),
            "NaicsCode": ["445110"] * rows,
            "BusinessType": ["1"] * rows,
            "BusinessAge": ["7"] * rows,
            "RevolverStatus": ["N"] * rows,
            "CollateralInd": ["Y"] * rows,
            "LoanStatus": y,
            "ApprovalFY": [2010] * rows,
            "sourceRowIndex": range(rows),
        }
    )


@pytest.fixture(params=["logistic", "catboost"])
def package_fixture(tmp_path, request):
    family = request.param
    package = tmp_path / family
    package.mkdir()
    data = frame()
    config = next(config for config in train.configurations() if config["family"] == family)
    model = train.fit(config, data, iterations=5)
    model_file = "model.cbm" if family == "catboost" else "model.joblib"
    train.save_model(model, package / model_file, family)
    calibration = {
        "type": "sigmoid",
        "slope": 1.0,
        "bias": 0.0,
        "version": "fixture-sigmoid",
        "years": [2017, 2017],
        "rows": 100,
    }
    domain = {
        "numeric": {
            key: {"min": float(data[key].min()), "max": float(data[key].max())}
            for key in ("GrossApproval", "InitialInterestRate", "TermInMonths")
        },
        "categorical": {
            key: {"445110" if key == "NaicsCode" else str(data[key][0]): 100} for key in CATEGORICAL
        },
        "rareThreshold": 50,
        "rows": 100,
    }
    train.write_json(package / "calibration.json", calibration)
    train.write_json(package / "domain.json", domain)
    train.write_json(package / "training.json", {"fixtureOnly": True})
    train.write_json(
        package / "evaluation.json", {"releaseApproved": True, "releaseGates": {"fixtureGateOnly": True}}
    )
    manifest = {
        "packageFormat": "sba-package-1",
        "modelVersion": "fixture-only",
        "featureVersion": FEATURE_VERSION,
        "calibrationVersion": "fixture-sigmoid",
        "featureOrder": list(FEATURES),
        "positiveClass": 1,
        "modelType": family,
        "naicsMode": config["naicsMode"],
        "datasetSha256": "0" * 64,
        "pythonVersion": list(platform.python_version_tuple()[:2]),
        "libraries": {
            name: importlib.metadata.version(name) for name in ("scikit-learn", "catboost", "numpy", "pandas")
        },
        "files": {file.name: digest(file) for file in package.iterdir()},
        "releaseApproved": True,
        "isDemo": True,
    }
    train.write_json(package / "manifest.json", manifest)
    return package, data, model, manifest


def request_payload():
    return ScoringRequest(
        schemaVersion="sba-scoring-1",
        requestId=uuid4(),
        loanAmountUsd="10001.00",
        termMonths=24,
        initialInterestRatePct="6.25",
        interestRateType="FIXED",
        isRevolving=False,
        hasCollateral=True,
        businessType="CORPORATION",
        businessAgeCategory="Existing, 5 or more years",
        naicsCode="445110",
    )


def test_real_fitted_model_roundtrip_and_ood(package_fixture):
    package, data, model, manifest = package_fixture
    scorer = ScoringPackage(package, digest(package / "manifest.json"))
    prediction = scorer.predict_frame(train.view(data, manifest["naicsMode"]))
    from scipy.special import expit

    assert np.allclose(
        prediction,
        expit(train.raw_scores(model, train.view(data, manifest["naicsMode"]), manifest["modelType"])),
    )
    assert scorer.evaluate(request_payload()).modelVersion == "fixture-only"
    payload = request_payload().model_copy(
        update={
            "initialInterestRatePct": "28.00",
            "loanAmountUsd": "1.00",
            "termMonths": 360,
            "naicsCode": "999999",
        }
    )
    response = scorer.evaluate(payload)
    assert response.domainStatus == "EXTRAPOLATION"
    assert {
        "RATE_OUT_OF_RANGE",
        "AMOUNT_OUT_OF_RANGE",
        "TERM_OUT_OF_RANGE",
        "UNSEEN_NAICS",
        "SBA_US_TO_RU_DEMO",
        "TERM_HISTORY_UNCONFIRMED",
    } <= set(response.warnings)
    with pytest.raises(ValueError, match="feature order"):
        scorer.predict_frame(train.view(data, "full").drop(columns=["TermInMonths"]))


@pytest.mark.parametrize(
    "corruption",
    [
        "pin",
        "file",
        "schema",
        "python",
        "library",
        "file-list",
        "release",
        "calibration",
        "domain",
        "frequency",
        "gates",
        "classes",
        "names",
    ],
)
def test_integrity_rejected_before_serving(package_fixture, corruption):
    package, _, _, manifest = package_fixture
    if corruption == "pin":
        with pytest.raises(ValueError, match="manifest"):
            ScoringPackage(package, "0" * 64)
        return
    if corruption == "schema":
        manifest["featureOrder"].reverse()
    elif corruption == "python":
        manifest["pythonVersion"] = ["3", "10"]
    elif corruption == "library":
        manifest["libraries"]["numpy"] = "invalid"
    elif corruption == "file-list":
        manifest["files"]["../../unknown"] = "0" * 64
    elif corruption == "release":
        manifest["releaseApproved"] = False
    elif corruption == "file":
        (package / "domain.json").write_text("{}")
    elif corruption in ("classes", "names"):
        if manifest["modelType"] == "catboost":
            # Corruption of native model file must be rejected before parsing it.
            (package / "model.cbm").write_bytes(b"invalid")
        else:
            fitted = joblib.load(package / "model.joblib")
            if corruption == "classes":
                fitted.named_steps["classifier"].classes_ = np.array([1, 0])
            else:
                fitted.named_steps["preprocess"].feature_names_in_ = np.array(list(reversed(FEATURES)))
            joblib.dump(fitted, package / "model.joblib")
            manifest["files"]["model.joblib"] = digest(package / "model.joblib")
    else:
        name = (
            "calibration.json"
            if corruption == "calibration"
            else "evaluation.json"
            if corruption == "gates"
            else "domain.json"
        )
        content = train.read_json(package / name)
        if corruption == "calibration":
            content["years"] = [2018, 2019]
        elif corruption == "gates":
            content["releaseApproved"] = False
        elif corruption == "domain":
            content["numeric"].pop("GrossApproval")
        else:
            content["categorical"]["NaicsCode"]["445110"] = 5
        train.write_json(package / name, content)
        manifest["files"][name] = digest(package / name)
    train.write_json(package / "manifest.json", manifest)
    with pytest.raises((ValueError, AttributeError)):
        ScoringPackage(package, digest(package / "manifest.json"))


def test_rare_categories_and_unreleased_package(package_fixture):
    package, _, _, manifest = package_fixture
    domain = train.read_json(package / "domain.json")
    domain["rows"] = 10
    for counts in domain["categorical"].values():
        for key in counts:
            counts[key] = 10
    train.write_json(package / "domain.json", domain)
    manifest["files"]["domain.json"] = digest(package / "domain.json")
    manifest["releaseApproved"] = False
    manifest["files"].pop("evaluation.json")
    train.write_json(package / "manifest.json", manifest)
    scorer = ScoringPackage(package, digest(package / "manifest.json"), allow_unreleased=True)
    assert "RARE_CATEGORY_NaicsCode" in scorer.evaluate(request_payload()).warnings
    with pytest.raises(ValueError):
        Bounds(min=2, max=1)


def test_candidates_selection_and_metrics():
    configs = list(train.configurations())
    assert len(configs) == 32
    assert sum(row["family"] == "catboost" for row in configs) == 24
    def candidate(loss, family):
        return {"config": {"family": family}, "metrics": {"logLoss": loss}}
    assert (
        train.choose([candidate(0.1, "catboost"), candidate(0.1004, "logistic")])["config"]["family"]
        == "logistic"
    )
    assert (
        train.choose([candidate(0.1, "catboost"), candidate(0.101, "logistic")])["config"]["family"]
        == "catboost"
    )
    actual = metrics([0, 0, 1, 1], [0, 0.1, 0.9, 1])
    baseline = metrics([0, 0, 1, 1], [0.5] * 4)
    assert all(release_gates(actual, baseline).values())
    assert sum(row["count"] for row in actual["calibrationBins"]) == 4
    assert metrics([0, 0], [0.0, 0.0])["averagePrecision"] is None
    assert metrics([1, 1], [0.0, 0.0])["thresholds"]["0.15"]["precision"] is None
    for labels, values in [([], []), ([0], [float("nan")]), ([0], [2]), ([2], [0.5])]:
        with pytest.raises(ValueError):
            metrics(labels, values)
    with pytest.raises(ValueError):
        train.view(frame(), "unknown")
    assert "TermInMonths" not in train.view(frame(), "prefix2", False)


def test_runner_keeps_slot_until_cancelled_job_really_finishes():
    entered, finish = threading.Event(), threading.Event()

    class SlowScorer:
        def evaluate(self, request):
            entered.set()
            finish.wait(timeout=3)
            return request

    async def scenario():
        runner = ScoringRunner(SlowScorer(), capacity=1, timeout=0.01)
        task = asyncio.create_task(runner.run("request"))
        await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        try:
            with pytest.raises(Exception, match="Scoring capacity"):
                await runner.run("excess")
        finally:
            finish.set()
            await runner.close()
        with pytest.raises(Exception, match="not ready"):
            await runner.run("closed")

    asyncio.run(scenario())


def test_small_real_training_pipeline_never_selects_on_test(tmp_path, monkeypatch):
    prepared, experiment, package = (tmp_path / name for name in ("prepared", "experiment", "package"))
    prepared.mkdir()
    manifest = {
        "featureVersion": FEATURE_VERSION,
        "featureOrder": list(FEATURES),
        "sourceSha256": "0" * 64,
        "splits": {},
        "files": {},
    }
    for name, year in [
        ("train", 2010),
        ("validation", 2015),
        ("calibration", 2017),
        ("test", 2018),
        ("transfer", 2020),
    ]:
        values = frame()
        values["ApprovalFY"] = year
        values.to_csv(prepared / f"{name}.csv", index=False, columns=PREPARED_COLUMNS)
        manifest["splits"][name] = {"years": [year, year], "rows": 100, "positives": 50}
        manifest["files"][f"{name}.csv"] = digest(prepared / f"{name}.csv")
    train.write_json(prepared / "manifest.json", manifest)
    configs = list(train.configurations())
    monkeypatch.setattr(train, "configurations", lambda: iter([configs[0], configs[8]]))
    original_make = train.make_model
    monkeypatch.setattr(
        train,
        "make_model",
        lambda config, include_term=True, iterations=1500: original_make(config, include_term, 5),
    )
    accessed = []
    original_load = train.load_split

    def audit_load(folder, name):
        accessed.append(name)
        return original_load(folder, name)

    monkeypatch.setattr(train, "load_split", audit_load)
    train.tune(prepared, experiment)
    assert set(accessed) == {"train", "validation"}
    train.freeze(prepared, experiment, package, "fixture-training")
    assert set(accessed) == {"train", "validation", "calibration"}
    train.evaluate(prepared, experiment, package)
    assert set(accessed) == {"train", "validation", "calibration", "test", "transfer"}
    report = train.read_json(package / "evaluation.json")
    assert report["releaseApproved"]
    scorer = ScoringPackage(package, digest(package / "manifest.json"))
    assert scorer.evaluate(request_payload()).isDemo
    assert (package / "calibration.png").exists()
    with pytest.raises(ValueError, match="changed"):
        train.evaluate(prepared, experiment, package)
