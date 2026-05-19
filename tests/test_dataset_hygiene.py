from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gnome_auditor.dataset_hygiene import (
    audit_records,
    load_csv_records,
    summarize_issues,
    write_issues_jsonl,
)


class DatasetHygieneTests(unittest.TestCase):
    def test_audit_records_flags_deterministic_row_issues(self) -> None:
        records = [
            {"material_id": "m1", "formula": "Li2 O1", "n_sites": "3", "volume": "20.5"},
            {"material_id": "m1", "formula": "DefinitelyNotAFormula", "n_sites": "0"},
            {"material_id": "", "formula": "", "volume": "-1"},
        ]

        issues = audit_records(records)
        summary = summarize_issues(issues)

        self.assertEqual(summary["by_code"]["duplicate_material_id"], 2)
        self.assertEqual(summary["by_code"]["unparseable_formula"], 1)
        self.assertEqual(summary["by_code"]["missing_material_id"], 1)
        self.assertEqual(summary["by_code"]["missing_formula"], 1)
        self.assertEqual(summary["by_code"]["invalid_n_sites"], 1)
        self.assertEqual(summary["by_code"]["invalid_volume"], 1)

    def test_csv_round_trip_and_jsonl_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "materials.csv"
            out_path = Path(tmpdir) / "issues.jsonl"
            csv_path.write_text(
                "material_id,formula,n_sites\n"
                "m1,Si O2,3\n"
                "m2,,2\n",
                encoding="utf-8",
            )

            records = load_csv_records(csv_path)
            issues = audit_records(records)
            count = write_issues_jsonl(issues, out_path)

            self.assertEqual(len(records), 2)
            self.assertEqual(count, 1)
            parsed = json.loads(out_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(parsed["code"], "missing_formula")


if __name__ == "__main__":
    unittest.main()

