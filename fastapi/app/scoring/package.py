"""Load exactly one trusted, pinned scoring package after verifying every file."""

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.special import expit

from app.scoring.contracts import FEATURE_VERSION, ScoringRequest, ScoringResponse, probability_score
from app.scoring.features import CATEGORICAL, FEATURES, NUMERIC, request_features


class PackageDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Manifest(PackageDTO):
    packageFormat: Literal["sba-package-1"]
    modelVersion: str = Field(min_length=1, max_length=120)
    featureVersion: Literal["sba-features-1"]
    calibrationVersion: str = Field(min_length=1, max_length=120)
    # Legacy packages predate explicit provenance and used FY2017 only.
    calibrationYears: list[Annotated[int, Field(ge=2010, le=2100, strict=True)]] | None = Field(
        default=None, min_length=2, max_length=2
    )
    operatingThreshold: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    featureOrder: list[str]
    positiveClass: Literal[1]
    modelType: Literal["logistic", "catboost"]
    naicsMode: Literal["full", "prefix2"]
    datasetSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pythonVersion: list[str]
    libraries: dict[str, str]
    files: dict[str, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]]
    releaseApproved: bool
    isDemo: Literal[True]


class Sigmoid(PackageDTO):
    type: Literal["sigmoid"]
    slope: float = Field(allow_inf_nan=False)
    bias: float = Field(allow_inf_nan=False)
    version: str
    years: list[int]
    rows: int = Field(ge=1)


class Bounds(PackageDTO):
    min: float = Field(allow_inf_nan=False)
    max: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.min > self.max:
            raise ValueError("Invalid feature bounds")
        return self


class Domain(PackageDTO):
    numeric: dict[str, Bounds]
    categorical: dict[str, dict[str, Annotated[int, Field(ge=1, strict=True)]]]
    rareThreshold: Literal[50]
    rows: int = Field(ge=1)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class ScoringPackage:
    def __init__(self, path: Path, expected_sha256: str, *, allow_unreleased=False):
        path = Path(path)
        if not expected_sha256 or digest(path / "manifest.json") != expected_sha256:
            raise ValueError("Untrusted scoring manifest")
        manifest = Manifest.model_validate_json((path / "manifest.json").read_bytes())
        self.manifest = manifest
        if manifest.featureOrder != list(FEATURES) or manifest.pythonVersion != list(
            platform.python_version_tuple()[:2]
        ):
            raise ValueError("Incompatible feature or Python version")
        if not manifest.releaseApproved and not allow_unreleased:
            raise ValueError("Scoring release gates have not passed")
        expected_libraries = {"scikit-learn", "catboost", "numpy", "pandas"}
        if set(manifest.libraries) != expected_libraries or any(
            importlib.metadata.version(name) != version for name, version in manifest.libraries.items()
        ):
            raise ValueError("Scoring dependency versions differ from training")
        model_file = "model.cbm" if manifest.modelType == "catboost" else "model.joblib"
        required = {model_file, "calibration.json", "domain.json", "training.json"}
        if manifest.releaseApproved:
            required.add("evaluation.json")
        if set(manifest.files) != required:
            raise ValueError("Unexpected scoring package files")
        for name, checksum in manifest.files.items():
            file = path / name
            if file.resolve().parent != path.resolve() or digest(file) != checksum:
                raise ValueError("Scoring file integrity check failed")
        self.calibration = Sigmoid.model_validate_json((path / "calibration.json").read_bytes())
        self.domain = Domain.model_validate_json((path / "domain.json").read_bytes())
        expected_years = manifest.calibrationYears if manifest.calibrationYears is not None else [2017, 2017]
        if (
            expected_years[0] > expected_years[1]
            or self.calibration.version != manifest.calibrationVersion
            or self.calibration.years != expected_years
        ):
            raise ValueError("Calibration provenance mismatch")
        if set(self.domain.numeric) != set(NUMERIC) or set(self.domain.categorical) != set(CATEGORICAL):
            raise ValueError("Incomplete applicability domain")
        if any(sum(counts.values()) != self.domain.rows for counts in self.domain.categorical.values()):
            raise ValueError("Invalid training category frequencies")
        if manifest.releaseApproved:
            evaluation = json.loads((path / "evaluation.json").read_text(encoding="utf-8"))
            if (
                evaluation.get("releaseApproved") is not True
                or not evaluation.get("releaseGates")
                or not all(evaluation["releaseGates"].values())
            ):
                raise ValueError("Evaluation has failed release gates")
        # Deserialization only after manifest pin, all file hashes and versions are checked.
        if manifest.modelType == "catboost":
            from catboost import CatBoostClassifier

            self.model = CatBoostClassifier()
            self.model.load_model(str(path / model_file))
            names = self.model.feature_names_
        else:
            import joblib

            self.model = joblib.load(path / model_file)
            names = list(self.model.feature_names_in_)
        if list(self.model.classes_) != [0, 1] or names != list(FEATURES):
            raise ValueError("Model inputs or class ordering mismatch")

    def predict_frame(self, values):
        from threadpoolctl import threadpool_limits

        if list(values.columns) != list(FEATURES):
            raise ValueError("Inference feature order mismatch")
        with threadpool_limits(limits=1):
            raw = (
                self.model.predict(values, prediction_type="RawFormulaVal", thread_count=1)
                if self.manifest.modelType == "catboost"
                else self.model.decision_function(values)
            )
        probability = np.asarray(expit(self.calibration.slope * np.asarray(raw) + self.calibration.bias))
        if not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
            raise ValueError("Invalid model probability")
        return probability

    def evaluate(self, request: ScoringRequest) -> ScoringResponse:
        import pandas as pd

        values = request_features(request, self.manifest.naicsMode)
        probability = float(self.predict_frame(pd.DataFrame([values], columns=list(FEATURES)))[0])
        warnings = ["SBA_US_TO_RU_DEMO", "TERM_HISTORY_UNCONFIRMED"]
        outside = False
        for field, code in (
            ("GrossApproval", "AMOUNT"),
            ("InitialInterestRate", "RATE"),
            ("TermInMonths", "TERM"),
        ):
            bounds = self.domain.numeric[field]
            if not bounds.min <= values[field] <= bounds.max:
                warnings.append(f"{code}_OUT_OF_RANGE")
                outside = True
        for field in CATEGORICAL:
            count = self.domain.categorical[field].get(values[field], 0)
            if count == 0:
                warnings.append("UNSEEN_NAICS" if field == "NaicsCode" else f"UNSEEN_CATEGORY_{field}")
                outside = True
            elif count < self.domain.rareThreshold:
                warnings.append(f"RARE_CATEGORY_{field}")
        return ScoringResponse(
            schemaVersion="sba-scoring-1",
            requestId=request.requestId,
            sbaDefaultProbability=probability,
            score=probability_score(probability),
            modelVersion=self.manifest.modelVersion,
            featureVersion=FEATURE_VERSION,
            calibrationVersion=self.manifest.calibrationVersion,
            domainStatus="EXTRAPOLATION" if outside else "IN_RANGE",
            isDemo=True,
            warnings=warnings,
        )
