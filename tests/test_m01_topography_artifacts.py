from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from m01_test_support import make_project
from planminpy.core.artifacts import ArtifactWorkspace, ArtifactWorkspaceError
from planminpy.modules.m01.topography import TopographySurface


class M01TopographyArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.context, _ = make_project(self.root)
        self.topography = self.root / "surface.csv"
        self.topography.write_text(
            "PID,X,Y,Z\n1,0,0,10\n2,1,0,12\n3,0,1,13\n4,1,1,15\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_exact_xy_returns_exact_source_z(self) -> None:
        result = TopographySurface.from_csv(self.topography).evaluate(1, 1)
        self.assertEqual(result.topography_z, 15.0)
        self.assertEqual(result.support_status, "EXACT_XY")

    def test_delaunay_barycentric_interpolation_on_plane(self) -> None:
        result = TopographySurface.from_csv(self.topography).evaluate(0.25, 0.5)
        self.assertAlmostEqual(result.topography_z, 12.0, places=12)
        self.assertEqual(result.support_status, "TIN_INTERPOLATED")

    def test_outside_hull_has_no_extrapolated_z(self) -> None:
        result = TopographySurface.from_csv(self.topography).evaluate(2, 2)
        self.assertIsNone(result.topography_z)
        self.assertEqual(result.support_status, "OUTSIDE_CONVEX_HULL")
        self.assertGreater(result.nearest_support_distance_m, 0)

    def test_artifact_path_confinement_rejects_escape_and_absolute(self) -> None:
        workspace = ArtifactWorkspace(self.context, "m01")
        with self.assertRaises(ArtifactWorkspaceError):
            workspace.write_json("../escape.json", {})
        with self.assertRaises(ArtifactWorkspaceError):
            workspace.write_json(self.root / "outside.json", {})

    def test_artifact_record_hash_matches_written_bytes(self) -> None:
        workspace = ArtifactWorkspace(self.context, "m01")
        path = workspace.write_json("proof.json", {"value": 1})
        record = workspace.record(
            path,
            artifact_id="proof",
            artifact_type="application/json",
            description="proof",
            schema_version="1.0",
            record_count=None,
        )
        self.assertEqual(record.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertTrue(path.is_relative_to(self.context.output_root))
        self.assertFalse(path.is_relative_to(self.context.data_root))


if __name__ == "__main__":
    unittest.main()
