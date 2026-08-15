from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from m01_test_support import collar, interval, make_project, survey
from planminpy.core.artifacts import ArtifactWorkspace
from planminpy.core.contracts import ModuleResult, ModuleStatus
from planminpy.core.paths import ProjectPaths
from planminpy.modules.m01.artifacts import write_m01_artifacts
from planminpy.modules.m01.geometry import desurvey_hole
from planminpy.modules.m01.inventory import (
    build_reference_grade_intercepts,
    delaunay_nodal_influence_areas,
    position_assays_xyz,
)
from planminpy.modules.m01.statistics import (
    grade_distribution_rows,
    observed_grade_distribution,
)
from planminpy.modules.m01.topography import (
    TopographySurface,
    classify_topography_consistency,
)
from planminpy.modules.m01.visualization import build_exploration_3d_html
from planminpy.reporting.reporter import Reporter


IDENTITY = {"project_id": "project", "dataset_id": "DS00", "release_id": "EXP03"}
BOUNDARIES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def trajectory(*, curved: bool = False) -> list[dict[str, object]]:
    collar_row = collar(
        x="0",
        y="0",
        z="100",
        final_depth_m="100",
        azimuth_deg="0",
        dip_deg="-45" if curved else "-90",
    )
    rows = [
        survey(depth_m="0", azimuth_deg="0", dip_deg="-45" if curved else "-90"),
        survey(
            depth_m="100",
            azimuth_deg="90" if curved else "0",
            dip_deg="-45" if curved else "-90",
        ),
    ]
    return desurvey_hole(collar_row, rows, zero_dogleg_epsilon_rad=1e-7)


def assay_row(sample_id: str, from_m: float, to_m: float, cu_pct: object) -> dict[str, str]:
    return interval(
        "assay.csv",
        sample_id=sample_id,
        from_m=str(from_m),
        to_m=str(to_m),
        length_m=str(to_m - from_m),
        cu_pct=str(cu_pct),
    )


def positioned(rows: list[dict[str, str]], *, curved: bool = False) -> list[dict[str, object]]:
    return position_assays_xyz(
        rows,
        {"QV-C01-001": trajectory(curved=curved)},
        **IDENTITY,
        zero_dogleg_epsilon_rad=1e-7,
        md_tolerance_m=1e-6,
    )


def reference_intercepts(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    return build_reference_grade_intercepts(
        rows,
        {"QV-C01-001": trajectory()},
        **IDENTITY,
        reference_grade=0.20,
        interval_tolerance_m=1e-6,
        zero_dogleg_epsilon_rad=1e-7,
    )


def bins(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    return grade_distribution_rows(
        rows,
        variable="cu_pct",
        unit="%",
        boundaries=BOUNDARIES,
        **IDENTITY,
    )


def artifact_arguments(*, reference_rows=None):
    return {
        "dataset_summary": {},
        "findings": [],
        "readiness": {"verdict": "PASS"},
        "source_hashes": {"Data/source.csv": "0" * 64},
        "trajectory_rows": [],
        "collar_topography_rows": [],
        "assay_statistics_rows": [],
        "assay_xyz_rows": [],
        "grade_distribution_rows": [],
        "reference_grade_intercept_rows": reference_rows,
        "exploration_3d_html": "<html></html>",
    }


class M01V11ScientificContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        surface = TopographySurface(
            np.array([1, 2, 3, 4]),
            np.array([[0.0, 0.0], [2.0, 0.0], [0.0, 2.0], [2.0, 2.0]]),
            np.array([100.0, 100.0, 100.0, 100.0]),
        )
        trajectory_rows = [
            {
                **IDENTITY,
                "campaign_id": "CAMPAIGN_01",
                "hole_id": "QV-C01-001",
                **row,
            }
            for row in trajectory()
        ]
        assay_xyz = positioned([assay_row("S1", 0, 10, 0.25)])
        cls.no_reference_html, cls.no_reference_metadata = build_exploration_3d_html(
            surface,
            trajectory_rows,
            assay_xyz,
            reference_grade=None,
            maximum_topography_vertices=4,
            **IDENTITY,
        )
        cls.reference_html, cls.reference_metadata = build_exploration_3d_html(
            surface,
            trajectory_rows,
            assay_xyz,
            reference_grade=0.20,
            maximum_topography_vertices=4,
            **IDENTITY,
        )

    def test_01_assay_xyz_from_coordinate(self) -> None:
        self.assertAlmostEqual(float(positioned([assay_row("S1", 20, 40, 0.3)])[0]["z_from"]), 80.0)

    def test_02_assay_xyz_mid_coordinate(self) -> None:
        self.assertAlmostEqual(float(positioned([assay_row("S1", 20, 40, 0.3)])[0]["z_mid"]), 70.0)

    def test_03_assay_xyz_to_coordinate(self) -> None:
        self.assertAlmostEqual(float(positioned([assay_row("S1", 20, 40, 0.3)])[0]["z_to"]), 60.0)

    def test_04_assay_xyz_curved_synthetic_hole(self) -> None:
        row = positioned([assay_row("S1", 40, 60, 0.3)], curved=True)[0]
        self.assertGreater(float(row["x_mid"]), 0.0)
        self.assertGreater(float(row["y_mid"]), 0.0)

    def test_05_reference_grade_equality_is_included(self) -> None:
        self.assertEqual(len(reference_intercepts([assay_row("S1", 0, 10, 0.20)])), 1)

    def test_06_contiguous_reference_intervals_merge(self) -> None:
        result = reference_intercepts(
            [assay_row("S1", 0, 10, 0.2), assay_row("S2", 10, 20, 0.3)]
        )
        self.assertEqual((len(result), result[0]["sample_count"]), (1, 2))

    def test_07_below_reference_internal_assay_breaks_intercept(self) -> None:
        result = reference_intercepts(
            [
                assay_row("S1", 0, 10, 0.3),
                assay_row("S2", 10, 20, 0.1),
                assay_row("S3", 20, 30, 0.4),
            ]
        )
        self.assertEqual(len(result), 2)

    def test_08_reference_intercept_grade_is_length_weighted(self) -> None:
        result = reference_intercepts(
            [assay_row("S1", 0, 10, 0.2), assay_row("S2", 10, 40, 0.4)]
        )
        self.assertAlmostEqual(float(result[0]["length_weighted_grade"]), 0.35)

    def test_09_reference_interpretation_is_explicit(self) -> None:
        row = reference_intercepts([assay_row("S1", 0, 10, 0.2)])[0]
        self.assertEqual(row["interpretation"], "ALONG_HOLE_REFERENCE_GRADE_INTERCEPT")
        self.assertEqual(row["thickness_semantic"], "NOT_TRUE_GEOLOGICAL_THICKNESS")

    def test_10_all_valid_assays_are_in_observed_distribution(self) -> None:
        rows = [assay_row("S1", 0, 10, 0.0), assay_row("S2", 10, 20, 0.8)]
        self.assertEqual(observed_grade_distribution(rows, variable="cu_pct", unit="%")["record_count"], 2)

    def test_11_zero_grade_assays_are_retained(self) -> None:
        rows = [assay_row("S1", 0, 10, 0.0), assay_row("S2", 10, 20, 0.2)]
        result = observed_grade_distribution(rows, variable="cu_pct", unit="%")
        self.assertEqual((result["zero_count"], result["minimum"]), (1, 0.0))

    def test_12_negative_grades_are_counted_not_silently_filtered(self) -> None:
        result = observed_grade_distribution(
            [assay_row("S1", 0, 10, -0.01)], variable="cu_pct", unit="%"
        )
        self.assertEqual((result["record_count"], result["negative_count"]), (1, 1))

    def test_13_missing_grades_are_reported(self) -> None:
        row = assay_row("S1", 0, 10, 0.1)
        row["cu_pct"] = ""
        result = observed_grade_distribution([row], variable="cu_pct", unit="%")
        self.assertEqual((result["record_count"], result["missing_count"]), (0, 1))

    def test_14_observed_distribution_has_required_percentiles(self) -> None:
        rows = [assay_row(f"S{i}", i, i + 1, i / 10) for i in range(10)]
        result = observed_grade_distribution(rows, variable="cu_pct", unit="%")
        for field in ("p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99"):
            self.assertIn(field, result)

    def test_15_default_grade_scheme_has_ten_bins(self) -> None:
        self.assertEqual(len(bins([assay_row("S1", 0, 1, 0.1)])), 10)

    def test_16_grade_bin_counts_reconcile(self) -> None:
        rows = [assay_row("S1", 0, 1, 0.0), assay_row("S2", 1, 3, 0.95)]
        self.assertEqual(sum(int(row["assay_count"]) for row in bins(rows)), 2)

    def test_17_grade_bin_metres_use_interval_lengths(self) -> None:
        rows = [assay_row("S1", 0, 1, 0.0), assay_row("S2", 1, 4, 0.15)]
        result = bins(rows)
        self.assertEqual((result[0]["assayed_metres"], result[1]["assayed_metres"]), (1.0, 3.0))

    def test_18_grade_bin_percentages_sum_to_one_hundred(self) -> None:
        rows = [assay_row("S1", 0, 1, 0.0), assay_row("S2", 1, 4, 0.95)]
        self.assertAlmostEqual(sum(float(row["percentage_of_assayed_metres"]) for row in bins(rows)), 100.0)

    def test_19_grade_bin_metres_reconcile_with_all_assay_metres(self) -> None:
        rows = [assay_row("S1", 0, 2, 0.0), assay_row("S2", 2, 7, 0.95)]
        result = bins(rows)
        self.assertEqual(sum(float(row["assayed_metres"]) for row in result), 7.0)

    def test_20_final_grade_bin_is_open_ended(self) -> None:
        result = bins([assay_row("S1", 0, 2, 4.5)])[-1]
        self.assertIsNone(result["grade_to"])
        self.assertEqual(result["assay_count"], 1)

    def test_21_grade_bin_grade_is_length_weighted(self) -> None:
        rows = [assay_row("S1", 0, 1, 0.11), assay_row("S2", 1, 4, 0.19)]
        self.assertAlmostEqual(float(bins(rows)[1]["length_weighted_grade"]), 0.17)

    def test_22_offline_3d_html_is_generated(self) -> None:
        self.assertIn("<html", self.no_reference_html.lower())
        self.assertTrue(self.no_reference_metadata["offline"])

    def test_23_3d_without_reference_has_exactly_three_traces(self) -> None:
        self.assertEqual(len(self.no_reference_metadata["trace_names"]), 3)
        self.assertFalse(self.no_reference_metadata["reference_grade_analysis_enabled"])

    def test_24_3d_with_reference_has_fourth_trace(self) -> None:
        self.assertEqual(len(self.reference_metadata["trace_names"]), 4)
        self.assertIn("Reference-grade intervals >= 0.20% Cu", self.reference_metadata["trace_names"])

    def test_25_base_artifact_contract_has_eight_module_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _ = make_project(Path(temporary))
            records = write_m01_artifacts(context, **artifact_arguments())
            self.assertEqual(len(records), 8)

    def test_26_optional_reference_artifact_is_conditional(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _ = make_project(Path(temporary))
            records = write_m01_artifacts(context, **artifact_arguments(reference_rows=[]))
            self.assertEqual(len(records), 9)
            self.assertIn("m01-reference-grade-intercepts", {row.artifact_id for row in records})

    def test_27_v10_stale_artifacts_are_removed_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _ = make_project(Path(temporary))
            workspace = ArtifactWorkspace(context, "m01")
            workspace.write_text("preliminary_inventory.csv", "obsolete")
            workspace.write_text("mineralized_intercepts.csv", "obsolete")
            write_m01_artifacts(context, **artifact_arguments())
            self.assertFalse(workspace.resolve("preliminary_inventory.csv").exists())
            self.assertFalse(workspace.resolve("mineralized_intercepts.csv").exists())

    def test_28_no_resource_tonnage_artifact_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _ = make_project(Path(temporary))
            names = {Path(row.relative_path).name for row in write_m01_artifacts(context, **artifact_arguments())}
            self.assertNotIn("preliminary_inventory.csv", names)
            self.assertNotIn("mineralized_intercepts.csv", names)

    def test_29_topography_two_and_five_metre_classification_is_preserved(self) -> None:
        classify = lambda value: classify_topography_consistency(
            value,
            "TIN_INTERPOLATED",
            warning_tolerance_m=2.0,
            review_tolerance_m=5.0,
        )
        self.assertEqual([classify(value) for value in (2.0, 2.01, 5.0, 5.01)], ["OK", "WARNING", "WARNING", "REQUIRES_REVIEW"])

    def test_30_rerun_upserts_one_m01_report_section(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Data").mkdir()
            reporter = Reporter(ProjectPaths.from_project_root(root))
            now = datetime.now(timezone.utc)
            result = ModuleResult(
                module_id="m01",
                module_version="1.1.0",
                status=ModuleStatus.COMPLETED,
                project_id="project",
                dataset_id="DS00",
                release_id="EXP03",
                started_at=now,
                completed_at=now,
                summary="M01",
            )
            reporter.update(result)
            self.assertEqual(len(reporter.update(result).state.sections), 1)

    def test_31_scientific_csv_output_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _ = make_project(Path(temporary))
            workspace = ArtifactWorkspace(context, "m01")
            first, _ = workspace.write_csv("proof.csv", ("value",), ({"value": 1.25},))
            first_hash = hashlib.sha256(first.read_bytes()).hexdigest()
            second, _ = workspace.write_csv("proof.csv", ("value",), ({"value": 1.25},))
            self.assertEqual(first_hash, hashlib.sha256(second.read_bytes()).hexdigest())


class LegacyDelaunayUtilityTests(unittest.TestCase):
    """Detached utility tests; these functions are not the M01 v1.1 workflow."""

    def test_triangle_area_utility(self) -> None:
        collars = [collar(hole_id="H1", x="0", y="0"), collar(hole_id="H2", x="3", y="0"), collar(hole_id="H3", x="0", y="2")]
        _, area = delaunay_nodal_influence_areas(collars)
        self.assertAlmostEqual(area, 3.0)

    def test_one_third_nodal_allocation_utility(self) -> None:
        collars = [collar(hole_id="H1", x="0", y="0"), collar(hole_id="H2", x="3", y="0"), collar(hole_id="H3", x="0", y="2")]
        areas, _ = delaunay_nodal_influence_areas(collars)
        self.assertTrue(all(abs(value - 1.0) < 1e-12 for value in areas.values()))

    def test_influence_sum_equals_convex_hull_utility(self) -> None:
        collars = [collar(hole_id="H1", x="0", y="0"), collar(hole_id="H2", x="2", y="0"), collar(hole_id="H3", x="2", y="2"), collar(hole_id="H4", x="0", y="2")]
        areas, hull = delaunay_nodal_influence_areas(collars)
        self.assertAlmostEqual(sum(areas.values()), hull)


if __name__ == "__main__":
    unittest.main()
