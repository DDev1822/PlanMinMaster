from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from m01_test_support import make_project
from planminpy.modules.m01.artifacts import write_m01_artifacts
from planminpy.modules.m01.models import Finding, Severity


class M01DeterminismTests(unittest.TestCase):
    def test_deterministic_artifact_rerun_replaces_identical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            context, _ = make_project(Path(temporary))
            arguments = {
                "dataset_summary": {"drilling": {"hole_count": 1}},
                "findings": [Finding.create("W", Severity.WARNING, "warning")],
                "readiness": {"verdict": "PASS_WITH_WARNINGS"},
                "source_hashes": {"Data/fixture.csv": "0" * 64},
                "trajectory_rows": [],
                "collar_topography_rows": [],
                "assay_statistics_rows": [],
                "assay_xyz_rows": [],
                "grade_distribution_rows": [],
                "reference_grade_intercept_rows": None,
                "exploration_3d_html": "<html>deterministic</html>",
            }
            first = write_m01_artifacts(context, **arguments)
            first_hashes = {item.artifact_id: item.sha256 for item in first}
            second = write_m01_artifacts(context, **arguments)
            second_hashes = {item.artifact_id: item.sha256 for item in second}
            self.assertEqual(first_hashes, second_hashes)
            self.assertEqual(len(list((context.output_root / "project" / "DS00" / "EXP03" / "m01").glob("*"))), 8)


if __name__ == "__main__":
    unittest.main()
