"""Strict, non-destructive CSV preparation using a reviewed dataset lock."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from contextlib import ExitStack
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory

from app.scoring.contracts import FEATURE_VERSION
from app.scoring.features import FEATURES, canonical_features

DATE_ROLES = ("approval", "asOf", "paidInFull", "chargeOff")
PREPARED_COLUMNS = (*FEATURES, "LoanStatus", "ApprovalFY", "sourceRowIndex")
LIMITATIONS = [
    "Retrospective completed-loan evaluation; labels may become known after later cohort approvals.",
    "No borrower identifier; company overlap between splits cannot be excluded.",
    "US SBA outcomes are not validated Russian banking PD.",
    "Historical availability of mutable TermInMonths is unconfirmed.",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def integer(value: str) -> int:
    try:
        number = Decimal(value)
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError("Expected finite integer")
        return int(number)
    except InvalidOperation:
        raise ValueError("Expected finite integer") from None


def component_date(row: dict, columns: list[str], required: bool) -> date | None:
    values = [row[column] for column in columns]
    empty = [value == "" for value in values]
    if all(empty) and not required:
        return None
    if any(empty):
        raise ValueError("Missing or partially populated date")
    return date(*(integer(value) for value in values))


def row_metadata(row: dict, date_columns: dict) -> tuple[int, int]:
    target = integer(row["LoanStatus"])
    if target not in (0, 1):
        raise ValueError("Unknown LoanStatus")
    approval = component_date(row, date_columns["approval"], required=True)
    as_of = component_date(row, date_columns["asOf"], required=True)
    year = integer(row["ApprovalFY"])
    if year != approval.year + (approval.month >= 10):
        raise ValueError("ApprovalFY does not match US fiscal year")
    if approval > as_of:
        raise ValueError("Approval is later than snapshot")
    for role, expected_target in (("paidInFull", 0), ("chargeOff", 1)):
        event = component_date(row, date_columns[role], required=target == expected_target)
        if event is not None and not approval <= event <= as_of:
            raise ValueError("Outcome date is outside approval/snapshot interval")
    return target, year


def validate_lock(lock: dict):
    """Reject an unbound schema rather than guessing source column names."""
    if lock.get("schemaStatus") != "verified" or not lock.get("columns") or not lock.get("dateColumns"):
        raise ValueError("Dataset schema awaits the original CSV header and review")
    columns = lock["columns"]
    dates = lock["dateColumns"]
    if set(dates) != set(DATE_ROLES) or any(len(value) != 3 for value in dates.values()):
        raise ValueError("Date schema must map four year/month/day triples")
    expected = [
        *FEATURES,
        "LoanStatus",
        "ApprovalFY",
        *(name for triple in dates.values() for name in triple),
    ]
    if (
        len(columns) != lock["columnCount"]
        or len(columns) != len(set(columns))
        or len(expected) != len(set(expected))
        or set(columns) != set(expected)
    ):
        raise ValueError("Unexpected dataset schema")
    if lock["target"] != {"column": "LoanStatus", "positiveClass": 1, "meaning": "CHGOFF"}:
        raise ValueError("Unexpected target definition")
    if set(lock["splits"]) != {"train", "validation", "calibration", "test", "transfer"}:
        raise ValueError("Expected five named temporal splits")
    years = []
    for spec in lock["splits"].values():
        start, end = spec["years"]
        if start > end:
            raise ValueError("Invalid temporal split")
        years.extend(range(start, end + 1))
    if len(years) != len(set(years)):
        raise ValueError("Overlapping temporal splits")


def split_for(year: int, splits: dict) -> str:
    for name, spec in splits.items():
        if spec["years"][0] <= year <= spec["years"][1]:
            return name
    raise ValueError("ApprovalFY outside locked cohorts")


def prepare(source: Path, destination: Path, lock: dict) -> dict:
    validate_lock(lock)
    if destination.exists():
        raise FileExistsError("Preparation destination already exists; use a new directory")
    if sha256_file(source) != lock["sha256"]:
        raise ValueError("Source SHA-256 does not match dataset lock")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".sba-prepare-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "prepared"
        staging.mkdir()
        summary = _write_prepared(source, staging, lock)
        if sha256_file(source) != lock["sha256"]:
            raise ValueError("Source changed during preparation")
        (staging / "manifest.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    return summary


def _write_prepared(source: Path, destination: Path, lock: dict) -> dict:
    class_counts, counts, positives, feature_counts = Counter(), Counter(), Counter(), Counter()
    with ExitStack() as stack:
        writers = {}
        for name in lock["splits"]:
            file = stack.enter_context((destination / f"{name}.csv").open("w", encoding="utf-8", newline=""))
            writers[name] = csv.DictWriter(file, fieldnames=PREPARED_COLUMNS)
            writers[name].writeheader()
        index_file = stack.enter_context(
            (destination / "split-index.csv").open("w", encoding="utf-8", newline="")
        )
        index_writer = csv.writer(index_file)
        index_writer.writerow(("sourceRowIndex", "ApprovalFY", "split"))
        input_file = stack.enter_context(source.open(encoding="utf-8-sig", newline=""))
        reader = csv.DictReader(input_file, strict=True)
        if reader.fieldnames != lock["columns"]:
            raise ValueError("CSV header does not match locked column order")
        for index, row in enumerate(reader):
            try:
                if None in row or None in row.values():
                    raise ValueError("CSV row width mismatch")
                values = canonical_features(row)
                target, year = row_metadata(row, lock["dateColumns"])
                split = split_for(year, lock["splits"])
            except (ValueError, KeyError):
                # No raw values, dates or personal data in diagnostic messages.
                raise ValueError(f"Invalid source row at zero-based index {index}") from None
            writers[split].writerow(
                {**values, "LoanStatus": target, "ApprovalFY": year, "sourceRowIndex": index}
            )
            index_writer.writerow((index, year, split))
            class_counts[str(target)] += 1
            counts[split] += 1
            positives[split] += target
            feature_counts[tuple(values.values())] += 1
    if dict(class_counts) != lock["classCounts"] or sum(counts.values()) != lock["rowCount"]:
        raise ValueError("Dataset row count or class balance mismatch")
    for name, spec in lock["splits"].items():
        if counts[name] != spec["rows"] or positives[name] != spec["positives"]:
            raise ValueError(f"Temporal cohort count mismatch: {name}")
    return {
        "preparationVersion": "sba-preparation-1",
        "datasetVersion": lock["datasetVersion"],
        "sourceSha256": lock["sha256"],
        "featureVersion": FEATURE_VERSION,
        "featureOrder": list(FEATURES),
        "target": lock["target"],
        "rowIndexBase": 0,
        "rowCount": sum(counts.values()),
        "classCounts": dict(class_counts),
        "columns": lock["columns"],
        "dateColumns": lock["dateColumns"],
        "splits": lock["splits"],
        "duplicateFeatureRowsBeyondFirst": sum(count - 1 for count in feature_counts.values()),
        "duplicatesRemoved": 0,
        "limitations": LIMITATIONS,
        "files": {file.name: sha256_file(file) for file in sorted(destination.glob("*.csv"))},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path(__file__).parent / "config/dataset.lock.json")
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    summary = prepare(args.csv, args.output, lock)
    print(json.dumps({"rows": summary["rowCount"], "datasetVersion": summary["datasetVersion"]}))


if __name__ == "__main__":
    main()
