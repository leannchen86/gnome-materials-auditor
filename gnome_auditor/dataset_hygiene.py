"""Deterministic dataset hygiene checks for materials tables."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from pymatgen.core import Composition


@dataclass(frozen=True)
class HygieneIssue:
    """A deterministic, reproducible dataset issue."""

    code: str
    severity: str
    row_index: int
    material_id: str | None
    field: str
    message: str
    value: str | None = None
    reference: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_records(
    records: Iterable[dict[str, Any]],
    *,
    id_field: str = "material_id",
    formula_field: str = "formula",
    n_sites_field: str = "n_sites",
    volume_field: str = "volume",
) -> list[HygieneIssue]:
    """Run deterministic row-level hygiene checks over table-like records."""
    rows = list(records)
    issues: list[HygieneIssue] = []
    id_to_rows: dict[str, list[int]] = defaultdict(list)

    for idx, row in enumerate(rows):
        material_id = _clean(row.get(id_field))
        formula = _clean(row.get(formula_field))

        if material_id is None:
            issues.append(
                HygieneIssue(
                    code="missing_material_id",
                    severity="error",
                    row_index=idx,
                    material_id=None,
                    field=id_field,
                    value=_string_or_none(row.get(id_field)),
                    message=f"Missing required material ID field {id_field!r}.",
                )
            )
        else:
            id_to_rows[material_id].append(idx)

        if formula is None:
            issues.append(
                HygieneIssue(
                    code="missing_formula",
                    severity="error",
                    row_index=idx,
                    material_id=material_id,
                    field=formula_field,
                    value=_string_or_none(row.get(formula_field)),
                    message=f"Missing required formula field {formula_field!r}.",
                )
            )
        else:
            issues.extend(_formula_issues(idx, material_id, formula_field, formula))

        if n_sites_field in row:
            issues.extend(_positive_number_issues(
                idx,
                material_id,
                row,
                field=n_sites_field,
                code="invalid_n_sites",
                integer=True,
            ))
        if volume_field in row:
            issues.extend(_positive_number_issues(
                idx,
                material_id,
                row,
                field=volume_field,
                code="invalid_volume",
                integer=False,
            ))

    for material_id, row_indices in sorted(id_to_rows.items()):
        if len(row_indices) <= 1:
            continue
        reference = ",".join(str(row_idx) for row_idx in row_indices)
        for row_idx in row_indices:
            issues.append(
                HygieneIssue(
                    code="duplicate_material_id",
                    severity="error",
                    row_index=row_idx,
                    material_id=material_id,
                    field=id_field,
                    value=material_id,
                    reference=reference,
                    message=(
                        f"Material ID {material_id!r} appears in rows {reference}."
                    ),
                )
            )

    return sorted(issues, key=lambda issue: (issue.row_index, issue.code, issue.field))


def load_csv_records(path: str | Path) -> list[dict[str, str]]:
    """Load records from a CSV file using the header row as field names."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_issues_jsonl(issues: Iterable[HygieneIssue], path: str | Path) -> int:
    """Write hygiene issues to JSONL and return the number written."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for issue in issues:
            handle.write(json.dumps(issue.as_dict(), sort_keys=True) + "\n")
            count += 1
    return count


def summarize_issues(issues: Iterable[HygieneIssue]) -> dict[str, Any]:
    """Return compact counts for terminal output and tests."""
    issue_list = list(issues)
    return {
        "total": len(issue_list),
        "by_severity": dict(Counter(issue.severity for issue in issue_list)),
        "by_code": dict(Counter(issue.code for issue in issue_list)),
    }


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach dataset-audit CLI arguments."""
    parser.add_argument("--csv", required=True, help="CSV file to audit.")
    parser.add_argument("--id-field", default="material_id", help="Material ID column.")
    parser.add_argument("--formula-field", default="formula", help="Formula column.")
    parser.add_argument("--n-sites-field", default="n_sites", help="Site-count column.")
    parser.add_argument("--volume-field", default="volume", help="Volume column.")
    parser.add_argument(
        "--output",
        default="data/dataset_hygiene_issues.jsonl",
        help="Output JSONL path for audit issues.",
    )


def main(args: argparse.Namespace) -> None:
    """Run the dataset hygiene CLI command."""
    records = load_csv_records(args.csv)
    issues = audit_records(
        records,
        id_field=args.id_field,
        formula_field=args.formula_field,
        n_sites_field=args.n_sites_field,
        volume_field=args.volume_field,
    )
    count = write_issues_jsonl(issues, args.output)
    summary = summarize_issues(issues)

    print(f"dataset-audit checked {len(records)} rows")
    print(f"dataset-audit wrote {count} issues to {args.output}")
    for severity, severity_count in sorted(summary["by_severity"].items()):
        print(f"  {severity}: {severity_count}")
    for code, code_count in sorted(summary["by_code"].items()):
        print(f"  {code}: {code_count}")


def _formula_issues(
    row_index: int,
    material_id: str | None,
    field: str,
    formula: str,
) -> list[HygieneIssue]:
    try:
        composition = Composition(formula)
    except Exception as exc:
        return [
            HygieneIssue(
                code="unparseable_formula",
                severity="error",
                row_index=row_index,
                material_id=material_id,
                field=field,
                value=formula,
                message=f"Formula could not be parsed by pymatgen: {exc}",
            )
        ]

    if composition.num_atoms <= 0:
        return [
            HygieneIssue(
                code="empty_formula",
                severity="error",
                row_index=row_index,
                material_id=material_id,
                field=field,
                value=formula,
                message="Formula parsed to zero atoms.",
            )
        ]
    return []


def _positive_number_issues(
    row_index: int,
    material_id: str | None,
    row: dict[str, Any],
    *,
    field: str,
    code: str,
    integer: bool,
) -> list[HygieneIssue]:
    raw_value = _clean(row.get(field))
    if raw_value is None:
        return []
    try:
        value = int(raw_value) if integer else float(raw_value)
    except ValueError:
        return [
            HygieneIssue(
                code=code,
                severity="error",
                row_index=row_index,
                material_id=material_id,
                field=field,
                value=raw_value,
                message=f"{field!r} must be a positive number.",
            )
        ]

    if value <= 0:
        return [
            HygieneIssue(
                code=code,
                severity="error",
                row_index=row_index,
                material_id=material_id,
                field=field,
                value=raw_value,
                message=f"{field!r} must be positive.",
            )
        ]
    return []


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

