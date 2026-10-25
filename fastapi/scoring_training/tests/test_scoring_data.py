import copy
import csv
import json
import sys
from pathlib import Path

import pytest
from app.scoring.features import FEATURES, canonical_features
from scoring_training import data


@pytest.fixture
def dataset(tmp_path):
    # Small artificial fixture, never the SBA release dataset or measured metrics.
    dates = {
        role: [f"{role}_{component}" for component in ("year", "month", "day")] for role in data.DATE_ROLES
    }
    columns = [*FEATURES, "LoanStatus", "ApprovalFY", *(key for triple in dates.values() for key in triple)]
    rows = []
    splits = {}
    for name, year in (
        ("train", 2010),
        ("validation", 2015),
        ("calibration", 2017),
        ("test", 2018),
        ("transfer", 2020),
    ):
        splits[name] = {"years": [year, year], "rows": 2, "positives": 1}
        for target in (0, 1):
            row = dict(
                zip(FEATURES, ("125000.00", "6.25", "F", "120", "445110", "1", "7", "N", "Y"), strict=True)
            )
            row.update(LoanStatus=str(target), ApprovalFY=str(year))
            for role, names in dates.items():
                values = {
                    "approval": (year - 1, 10, 1),
                    "asOf": (2026, 6, 30),
                    "paidInFull": (year + 1, 1, 1) if target == 0 else ("", "", ""),
                    "chargeOff": (year + 1, 2, 1) if target == 1 else ("", "", ""),
                }[role]
                row.update(zip(names, map(str, values), strict=True))
            rows.append(row)
    source = tmp_path / "source.csv"
    write_csv(source, columns, rows)
    lock = {
        "schemaStatus": "verified",
        "datasetVersion": "synthetic-fixture-only",
        "columns": columns,
        "columnCount": 23,
        "dateColumns": dates,
        "rowCount": 10,
        "classCounts": {"0": 5, "1": 5},
        "sha256": data.sha256_file(source),
        "target": {"column": "LoanStatus", "positiveClass": 1, "meaning": "CHGOFF"},
        "splits": splits,
    }
    return source, lock, rows


def write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, columns)
        writer.writeheader()
        writer.writerows(rows)


def test_preparation_keeps_source_and_exact_row_membership(dataset, tmp_path):
    source, lock, rows = dataset
    original = source.read_bytes()
    destination = tmp_path / "runs" / "prepared-v1"
    manifest = data.prepare(source, destination, lock)
    assert source.read_bytes() == original
    assert json.loads((destination / "manifest.json").read_text()) == manifest
    assert manifest["featureOrder"] == list(FEATURES)
    assert manifest["duplicateFeatureRowsBeyondFirst"] == 9
    assert manifest["duplicatesRemoved"] == 0
    assert manifest["rowIndexBase"] == 0
    assert manifest["target"]["positiveClass"] == 1
    index = list(csv.DictReader((destination / "split-index.csv").open()))
    assert [int(row["sourceRowIndex"]) for row in index] == list(range(10))
    for split, spec in lock["splits"].items():
        with (destination / f"{split}.csv").open() as stream:
            prepared = list(csv.DictReader(stream))
        assert len(prepared) == spec["rows"]
        assert sum(int(row["LoanStatus"]) for row in prepared) == spec["positives"]
        for row in prepared:
            original_row = rows[int(row["sourceRowIndex"])]
            assert canonical_features(row) == canonical_features(original_row)
            assert set(row) == set(data.PREPARED_COLUMNS)
        assert data.sha256_file(destination / f"{split}.csv") == manifest["files"][f"{split}.csv"]
    with pytest.raises(FileExistsError):
        data.prepare(source, destination, lock)


def test_large_file_checksum_is_streamed(tmp_path):
    import hashlib

    source = tmp_path / "large"
    content = b"a" * (1024 * 1024 + 13)
    source.write_bytes(content)
    assert data.sha256_file(source) == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda spec: spec.update(schemaStatus="awaiting-source-header"),
        lambda spec: spec["columns"].append("unexpected"),
        lambda spec: spec["columns"].__setitem__(0, spec["columns"][1]),
        lambda spec: spec["dateColumns"].update(approval=["bad", "schema"]),
        lambda spec: spec["dateColumns"].update(approval=spec["dateColumns"]["asOf"]),
        lambda spec: spec["target"].update(positiveClass=0),
        lambda spec: spec["splits"].update(train={"years": [2015, 2014]}),
        lambda spec: spec["splits"]["train"].update(years=[2010, 2015]),
        lambda spec: spec["splits"].__setitem__("../../bad", spec["splits"].pop("train")),
    ],
)
def test_lock_integrity_errors_are_rejected(dataset, mutation):
    _, lock, _ = dataset
    mutation(lock)
    with pytest.raises(ValueError):
        data.validate_lock(lock)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ApprovalFY", "2009"),
        ("ApprovalFY", "NaN"),
        ("LoanStatus", "2"),
        ("LoanStatus", "false"),
        ("LoanStatus", "0.1"),
        ("approval_month", ""),
        ("paidInFull_year", ""),
        ("paidInFull_year", "2008"),
        ("paidInFull_year", "2027"),
        ("paidInFull_day", "32"),
        ("asOf_year", "2008"),
        ("chargeOff_month", "1"),
        ("asOf_year", "Infinity"),
    ],
)
def test_row_dates_targets_and_fiscal_year(dataset, field, value):
    _, lock, rows = dataset
    row = copy.deepcopy(rows[0])
    row[field] = value
    with pytest.raises(ValueError):
        data.row_metadata(row, lock["dateColumns"])


def test_fiscal_year_before_october_and_integral_csv_numbers(dataset):
    _, lock, rows = dataset
    row = rows[0].copy()
    row.update(approval_month="9.0", approval_year="2010.0", LoanStatus="0.0")
    assert data.row_metadata(row, lock["dateColumns"]) == (0, 2010)
    with pytest.raises(ValueError, match="cohorts"):
        data.split_for(2027, lock["splits"])


def test_hash_mismatch_writes_nothing(dataset, tmp_path):
    source, lock, _ = dataset
    lock["sha256"] = "0" * 64
    destination = tmp_path / "prepared"
    with pytest.raises(ValueError, match="SHA-256"):
        data.prepare(source, destination, lock)
    assert not destination.exists()


@pytest.mark.parametrize(
    "failure", ["header", "row", "width-extra", "width-missing", "classes", "cohort", "count"]
)
def test_failed_preparation_is_not_published(dataset, tmp_path, failure):
    source, lock, rows = dataset
    if failure == "header":
        write_csv(source, list(reversed(lock["columns"])), rows)
    elif failure == "row":
        rows[3]["CollateralInd"] = "unknown-private-value"
        write_csv(source, lock["columns"], rows)
    elif failure.startswith("width"):
        lines = source.read_text().splitlines()
        lines[1] = lines[1] + ",extra" if failure == "width-extra" else lines[1].rsplit(",", 1)[0]
        source.write_text("\n".join(lines) + "\n")
    elif failure == "classes":
        lock["classCounts"] = {"0": 4, "1": 6}
    elif failure == "count":
        lock["rowCount"] += 1
    else:
        lock["splits"]["test"]["positives"] = 0
    lock["sha256"] = data.sha256_file(source)
    destination = tmp_path / "prepared"
    with pytest.raises(ValueError) as error:
        data.prepare(source, destination, lock)
    assert "unknown-private-value" not in str(error.value)
    assert not destination.exists()
    assert not list(tmp_path.glob(".sba-prepare-*"))


def test_mutating_source_during_preparation_is_rejected(dataset, tmp_path, monkeypatch):
    source, lock, _ = dataset
    original = data._write_prepared

    def mutate(*args):
        result = original(*args)
        source.write_text(source.read_text() + "\n")
        return result

    monkeypatch.setattr(data, "_write_prepared", mutate)
    with pytest.raises(ValueError, match="changed"):
        data.prepare(source, tmp_path / "prepared", lock)
    assert not (tmp_path / "prepared").exists()


def test_cli_accepts_explicit_paths(dataset, tmp_path, monkeypatch, capsys):
    source, lock, _ = dataset
    config = tmp_path / "dataset.lock.json"
    config.write_text(json.dumps(lock))
    monkeypatch.setattr(
        sys,
        "argv",
        ["prepare", "--csv", str(source), "--lock", str(config), "--output", str(tmp_path / "prepared")],
    )
    data.main()
    assert json.loads(capsys.readouterr().out) == {"rows": 10, "datasetVersion": "synthetic-fixture-only"}


def test_release_lock_intentionally_requires_source_header():
    lock = json.loads((Path(__file__).resolve().parents[1] / "config/dataset.lock.json").read_text())
    assert sum(spec["rows"] for spec in lock["splits"].values()) == lock["rowCount"]
    assert sum(spec["positives"] for spec in lock["splits"].values()) == lock["classCounts"]["1"]
    with pytest.raises(ValueError, match="original CSV"):
        data.validate_lock(lock)
