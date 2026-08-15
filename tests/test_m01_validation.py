from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from m01_test_support import collar, interval, make_project, survey, table
from planminpy.modules.m01.loaders import M01DataError, SCHEMAS, load_table
from planminpy.modules.m01.validation import (
    validate_collars,
    validate_density_values,
    validate_intervals,
    validate_surveys,
)


class M01ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.context, self.config = make_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_source_schema_loader_accepts_exact_header(self) -> None:
        path = self.root / "collar.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SCHEMAS["collar.csv"])
            writer.writeheader()
            writer.writerow(collar())
        loaded = load_table(path, SCHEMAS["collar.csv"])
        self.assertEqual(len(loaded.rows), 1)

    def test_source_schema_loader_rejects_reordered_header(self) -> None:
        path = self.root / "collar.csv"
        path.write_text("dataset_id,hole_id\nDS00,H1\n", encoding="utf-8")
        with self.assertRaises(M01DataError):
            load_table(path, SCHEMAS["collar.csv"])

    def test_campaign_alias_matching_is_explicit_and_valid(self) -> None:
        findings = validate_collars(
            table(self.root, "collar.csv", [collar()]), self.context, self.config
        )
        self.assertFalse(any("CAMPAIGN" in item.rule_id for item in findings))

    def test_malformed_campaign_identity_is_blocking(self) -> None:
        findings = validate_collars(
            table(
                self.root,
                "collar.csv",
                [collar(campaign_id="CAMPAIGN_03")],
            ),
            self.context,
            self.config,
        )
        match = next(item for item in findings if item.rule_id == "COLLAR_CAMPAIGN_ALIAS_MISMATCH")
        self.assertTrue(match.blocking)

    def test_collar_numeric_identity_and_duplicate_rules(self) -> None:
        rows = [collar(), collar(hole_id="QV-C01-001", dip_deg="5")]
        findings = validate_collars(
            table(self.root, "collar.csv", rows), self.context, self.config
        )
        rules = {item.rule_id for item in findings}
        self.assertIn("COLLAR_DUPLICATE_HOLE_ID", rules)
        self.assertIn("COLLAR_DUPLICATE_XY", rules)
        self.assertIn("COLLAR_INVALID_DIP", rules)

    def test_survey_missing_md0_and_terminal_gap_require_review(self) -> None:
        collar_row = collar(final_depth_m="200")
        rows = [survey(depth_m="25"), survey(depth_m="100")]
        findings = validate_surveys(
            table(self.root, "survey.csv", rows),
            {collar_row["hole_id"]: collar_row},
            self.context,
            self.config,
        )
        rules = {item.rule_id for item in findings if item.requires_review}
        self.assertIn("SURVEY_MISSING_MD0", rules)
        self.assertIn("SURVEY_TERMINAL_GAP_REVIEW", rules)

    def test_survey_duplicate_and_beyond_depth_are_blocking(self) -> None:
        collar_row = collar(final_depth_m="50")
        rows = [survey(depth_m="60"), survey(depth_m="60")]
        findings = validate_surveys(
            table(self.root, "survey.csv", rows),
            {collar_row["hole_id"]: collar_row},
            self.context,
            self.config,
        )
        blocking_rules = {item.rule_id for item in findings if item.blocking}
        self.assertIn("SURVEY_DUPLICATE_MD", blocking_rules)
        self.assertIn("SURVEY_BEYOND_FINAL_DEPTH", blocking_rules)

    def test_interval_gap_is_nonblocking_but_overlap_is_blocking(self) -> None:
        collar_row = collar(final_depth_m="30")
        rows = [
            interval("assay.csv", sample_id="S1", from_m="0", to_m="10", length_m="10"),
            interval("assay.csv", sample_id="S2", from_m="15", to_m="25", length_m="10"),
        ]
        gaps = validate_intervals(
            table(self.root, "assay.csv", rows),
            {collar_row["hole_id"]: collar_row},
            self.context,
            self.config,
            primary_id="sample_id",
            gap_kind="UNSAMPLED_GAP",
        )
        self.assertTrue(any(item.rule_id == "INTERVAL_UNSAMPLED_GAP" and not item.blocking for item in gaps))
        rows[1].update(from_m="9", length_m="16")
        overlaps = validate_intervals(
            table(self.root, "assay.csv", rows),
            {collar_row["hole_id"]: collar_row},
            self.context,
            self.config,
            primary_id="sample_id",
            gap_kind="UNSAMPLED_GAP",
        )
        self.assertTrue(any(item.rule_id == "INTERVAL_OVERLAP" and item.blocking for item in overlaps))

    def test_density_invalid_and_outside_review_range(self) -> None:
        rows = [
            interval("density.csv", density_sample_id="D1", density_t_m3="0"),
            interval("density.csv", density_sample_id="D2", density_t_m3="5"),
        ]
        findings = validate_density_values(
            table(self.root, "density.csv", rows), self.config
        )
        by_rule = {item.rule_id: item for item in findings}
        self.assertTrue(by_rule["DENSITY_INVALID_VALUE"].blocking)
        self.assertTrue(by_rule["DENSITY_PHYSICAL_REVIEW"].requires_review)

    def test_empty_alteration_is_valid_info(self) -> None:
        findings = validate_intervals(
            table(self.root, "alteration.csv", []),
            {"QV-C01-001": collar()},
            self.context,
            self.config,
            primary_id=None,
            gap_kind="ALTERATION_GAP",
        )
        self.assertEqual([item.rule_id for item in findings], ["ALTERATION_NO_OBSERVATIONS"])
        self.assertFalse(findings[0].blocking)


if __name__ == "__main__":
    unittest.main()
