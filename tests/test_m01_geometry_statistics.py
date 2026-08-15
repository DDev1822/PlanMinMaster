from __future__ import annotations

import math
import unittest

from m01_test_support import collar, interval, survey
from planminpy.modules.m01.geometry import (
    desurvey_hole,
    minimum_curvature_increment,
)
from planminpy.modules.m01.statistics import (
    analytical_classification,
    assay_statistics_rows,
    linear_percentile,
)


class M01GeometryStatisticsTests(unittest.TestCase):
    def test_minimum_curvature_straight_vertical_hole(self) -> None:
        increment = minimum_curvature_increment(
            100, 0, -90, 0, -90, zero_dogleg_epsilon_rad=1e-12
        )
        self.assertAlmostEqual(increment.delta_easting_m, 0.0, places=12)
        self.assertAlmostEqual(increment.delta_northing_m, 0.0, places=12)
        self.assertAlmostEqual(increment.delta_z_m, -100.0, places=12)

    def test_minimum_curvature_curved_synthetic_hole(self) -> None:
        increment = minimum_curvature_increment(
            100, 0, -45, 90, -45, zero_dogleg_epsilon_rad=1e-12
        )
        self.assertAlmostEqual(math.degrees(increment.dogleg_rad), 60.0, places=10)
        self.assertAlmostEqual(increment.delta_easting_m, 38.984840062, places=8)
        self.assertAlmostEqual(increment.delta_northing_m, 38.984840062, places=8)
        self.assertAlmostEqual(increment.delta_z_m, -77.969680123, places=8)

    def test_zero_dogleg_uses_safe_ratio_factor(self) -> None:
        increment = minimum_curvature_increment(
            30, 38.012787504, -83.937183959, 38.012787504, -83.937183959,
            zero_dogleg_epsilon_rad=1e-7,
        )
        self.assertEqual(increment.dogleg_rad, 0.0)
        self.assertEqual(increment.ratio_factor, 1.0)

    def test_terminal_extension_preserves_last_orientation(self) -> None:
        stations = desurvey_hole(
            collar(final_depth_m="100", dip_deg="-45"),
            [survey(depth_m="0", dip_deg="-45"), survey(depth_m="60", dip_deg="-50")],
            zero_dogleg_epsilon_rad=1e-12,
        )
        self.assertEqual(stations[-1]["station_type"], "TERMINAL_EXTENSION")
        self.assertEqual(stations[-1]["orientation_provenance"], "TERMINAL_EXTENSION")
        self.assertEqual(stations[-1]["md_m"], 100.0)

    def test_assay_variable_and_constant_zero_classification(self) -> None:
        self.assertEqual(analytical_classification([1, 2, 3]), "VARIABLE")
        self.assertEqual(analytical_classification([0, 0]), "CONSTANT_ZERO")
        self.assertEqual(analytical_classification([2, 2]), "CONSTANT_NONZERO")
        self.assertEqual(analytical_classification([]), "EMPTY")

    def test_percentile_uses_frozen_linear_index_convention(self) -> None:
        self.assertEqual(linear_percentile([0, 10, 20, 30], 0.25), 7.5)
        self.assertAlmostEqual(linear_percentile([0, 10, 20, 30], 0.95), 28.5)

    def test_assay_statistics_are_raw_not_length_weighted(self) -> None:
        rows = [
            interval("assay.csv", sample_id="S1", length_m="1", to_m="1", cu_pct="1"),
            interval("assay.csv", sample_id="S2", from_m="1", to_m="10", length_m="9", cu_pct="3"),
        ]
        output = assay_statistics_rows(
            rows, project_id="project", dataset_id="DS00", release_id="EXP03"
        )
        copper = next(row for row in output if row["scope_type"] == "ALL" and row["element"] == "cu_pct")
        self.assertEqual(copper["mean"], 2.0)
        self.assertEqual(copper["assay_metres"], 10.0)
        molybdenum = next(row for row in output if row["scope_type"] == "ALL" and row["element"] == "mo_pct")
        self.assertEqual(molybdenum["classification"], "CONSTANT_ZERO")


if __name__ == "__main__":
    unittest.main()
