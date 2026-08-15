from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from m01_test_support import make_project
from planminpy.modules.m01.artifacts import write_m01_artifacts
from planminpy.modules.m01.technical_summary import (
    build_technical_summary,
    render_technical_summary_markdown,
    render_technical_summary_text,
)


def summary(reference_enabled: bool = False):
    reference = {
        "reference_grade_analysis_enabled": reference_enabled,
        "reference_grade": 0.2,
        "intercept_count": 2,
        "intercept_metres": 20.0,
        "drillholes_represented": 1,
    }
    return build_technical_summary(
        project_name="Quebrada Verde",
        dataset_id="DS00",
        release_id="EXP03",
        drilling={"hole_count": 2, "total_drilled_metres": 100.0},
        validation={
            "verdict": "PASS_WITH_WARNINGS",
            "finding_counts": {"blocking_error_count": 0, "warning_count": 1},
        },
        drillhole_geometry={
            "survey_record_count": 4,
            "drillholes_desurveyed": 2,
            "trajectory_station_count": 5,
            "assays_positioned_xyz": 3,
            "terminal_extension_count": 1,
            "maximum_dogleg_deg_per_30m": 0.5,
        },
        observed_grade={
            "source_record_count": 3,
            "assayed_metres": 30.0,
            "minimum": 0.0,
            "maximum": 0.4,
            "mean": 0.2,
            "median": 0.2,
            "population_stddev": 0.1,
            "coefficient_of_variation": 0.5,
            "p10": 0.02,
            "p50": 0.2,
            "p90": 0.38,
        },
        topography={
            "source_point_count": 4,
            "consistency_class_counts": {"OK": 1, "WARNING": 1},
            "residual_statistics_m": {"maximum_absolute": 2.0},
        },
        density={
            "record_count": 1,
            "holes_represented": 1,
            "statistics": {"mean": 2.5, "minimum": 2.5, "maximum": 2.5},
        },
        reference=reference,
    )


class TechnicalSummaryTests(unittest.TestCase):
    def test_all_required_categories_are_present(self) -> None:
        categories = {row["category"] for row in summary()["rows"]}
        self.assertEqual(
            categories,
            {"PROJECT", "DRILLING", "VALIDATION", "DESURVEY", "OBSERVED Cu", "TOPOGRAPHY", "DENSITY", "REFERENCE"},
        )

    def test_renderer_only_uses_supplied_normalized_values(self) -> None:
        rendered = render_technical_summary_text(summary())
        self.assertIn("0.50000", rendered)
        self.assertIn("Quebrada Verde", rendered)

    def test_markdown_is_deterministic(self) -> None:
        first = render_technical_summary_markdown(summary())
        second = render_technical_summary_markdown(summary())
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_no_reference_branch_is_explicit(self) -> None:
        self.assertIn("NOT REQUESTED", render_technical_summary_markdown(summary()))

    def test_reference_branch_uses_along_hole_language(self) -> None:
        rendered = render_technical_summary_markdown(summary(True))
        self.assertIn("Reference grade", rendered)
        self.assertIn("ALONG-HOLE", rendered)

    def test_summary_artifact_is_registered_and_confined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context, _ = make_project(root)
            markdown = render_technical_summary_markdown(summary())
            records = write_m01_artifacts(
                context,
                dataset_summary={},
                findings=[],
                readiness={},
                source_hashes={},
                trajectory_rows=[],
                collar_topography_rows=[],
                assay_statistics_rows=[],
                assay_xyz_rows=[],
                grade_distribution_rows=[],
                reference_grade_intercept_rows=None,
                exploration_3d_html="<html></html>",
                technical_summary_markdown=markdown,
            )
            record = next(item for item in records if item.artifact_id == "m01-technical-summary")
            path = context.output_root / record.relative_path
            self.assertTrue(path.is_relative_to(context.output_root))
            self.assertFalse(path.is_relative_to(context.data_root))
            self.assertEqual(path.read_text(encoding="utf-8"), markdown)


if __name__ == "__main__":
    unittest.main()
