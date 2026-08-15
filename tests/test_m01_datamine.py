from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from interactive_test_support import make_interactive_project
from planminpy.core.artifacts import ArtifactWorkspace
from planminpy.modules.m01.artifacts import (
    ASSAY_XYZ_FIELDS,
    TOPOGRAPHY_TIN_TRIANGLE_FIELDS,
    TOPOGRAPHY_TIN_VERTEX_FIELDS,
    TRAJECTORY_FIELDS,
)
from planminpy.modules.m01.datamine import (
    DRILLHOLE_FIELDS,
    PT_FIELDS,
    TR_FIELDS,
    DatamineBackendInfo,
    export_static_drillholes,
    export_topographic_wireframe,
)


class _UnavailableBackend:
    info = DatamineBackendInfo(False, "NOT_AVAILABLE", None, None)

    def write_static_drillholes(self, _staging, _target):
        raise AssertionError("unavailable backend must not be invoked")

    def write_wireframe(self, _pt, _tr, _pt_target, _tr_target):
        raise AssertionError("unavailable backend must not be invoked")


class _SuccessfulBackend:
    info = DatamineBackendInfo(True, "AVAILABLE", "Mock official backend", "1.0")

    def write_static_drillholes(self, _staging, target):
        target.write_bytes(b"mock-native-static")
        return True

    def write_wireframe(self, _pt, _tr, pt_target, tr_target):
        pt_target.write_bytes(b"mock-native-pt")
        tr_target.write_bytes(b"mock-native-tr")
        return True


class _PartialBackend(_SuccessfulBackend):
    def write_wireframe(self, _pt, _tr, pt_target, _tr_target):
        pt_target.write_bytes(b"partial")
        return False


def _row(fields, **values):
    result = {field: "" for field in fields}
    result.update(values)
    return result


class DatamineExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths, active = make_interactive_project(self.root)
        self.context = active.create_context(self.paths, {})
        workspace = ArtifactWorkspace(self.context, "m01")
        workspace.write_csv(
            "drillhole_trajectory.csv",
            TRAJECTORY_FIELDS,
            [
                _row(
                    TRAJECTORY_FIELDS,
                    hole_id="H1", md_m=0.0, x=0.0, y=0.0, z=100.0,
                    azimuth_deg=0.0, dip_deg=-90.0, interval_md_m=0.0,
                ),
                _row(
                    TRAJECTORY_FIELDS,
                    hole_id="H1", md_m=20.0, x=0.0, y=0.0, z=80.0,
                    azimuth_deg=0.0, dip_deg=-90.0, interval_md_m=20.0,
                ),
            ],
        )
        workspace.write_csv(
            "assay_xyz.csv",
            ASSAY_XYZ_FIELDS,
            [
                _row(
                    ASSAY_XYZ_FIELDS,
                    sample_id="S2", hole_id="H1", from_m=10.0, to_m=20.0,
                    length_m=10.0, mid_m=15.0, x_mid=0.0, y_mid=0.0, z_mid=85.0,
                    cu_pct=0.3, mo_pct=0.02, au_gt=0.5,
                ),
                _row(
                    ASSAY_XYZ_FIELDS,
                    sample_id="S1", hole_id="H1", from_m=0.0, to_m=10.0,
                    length_m=10.0, mid_m=5.0, x_mid=0.0, y_mid=0.0, z_mid=95.0,
                    cu_pct=0.1, mo_pct=0.01, au_gt=0.25,
                ),
            ],
        )
        workspace.write_csv(
            "topography_tin_vertices.csv",
            TOPOGRAPHY_TIN_VERTEX_FIELDS,
            [
                {"vertex_index": 0, "source_pid": 1, "x": 0, "y": 0, "z": 100},
                {"vertex_index": 1, "source_pid": 3, "x": 0, "y": 1, "z": 100},
                {"vertex_index": 2, "source_pid": 2, "x": 1, "y": 0, "z": 100},
                {"vertex_index": 3, "source_pid": 4, "x": 1, "y": 1, "z": 100},
            ],
        )
        workspace.write_csv(
            "topography_tin_triangles.csv",
            TOPOGRAPHY_TIN_TRIANGLE_FIELDS,
            [
                {"triangle_index": 0, "vertex_index_1": 0, "vertex_index_2": 2, "vertex_index_3": 1},
                {"triangle_index": 1, "vertex_index_1": 2, "vertex_index_2": 3, "vertex_index_3": 1},
            ],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _csv(path: Path):
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return tuple(reader.fieldnames or ()), list(reader)

    def test_static_staging_exact_fields_mapping_sort_and_dip_conversion(self) -> None:
        result = export_static_drillholes(self.context, backend=_UnavailableBackend())
        fields, rows = self._csv(result.staging_paths[0])
        self.assertEqual(fields, DRILLHOLE_FIELDS)
        self.assertEqual([float(row["FROM"]) for row in rows], [0.0, 10.0])
        first = rows[0]
        self.assertEqual(first["BHID"], "H1")
        self.assertEqual((float(first["FROM"]), float(first["TO"]), float(first["LENGTH"])), (0.0, 10.0, 10.0))
        self.assertEqual((float(first["X"]), float(first["Y"]), float(first["Z"])), (0.0, 0.0, 95.0))
        self.assertEqual(float(first["A0"]), 0.0)
        self.assertEqual(float(first["B0"]), 90.0)
        self.assertEqual((float(first["CU"]), float(first["MO"]), float(first["AU"])), (0.1, 0.01, 0.25))

    def test_static_staging_and_manifest_are_deterministic_and_hashed(self) -> None:
        first = export_static_drillholes(self.context, backend=_UnavailableBackend())
        before = (first.staging_paths[0].read_bytes(), first.manifest_path.read_bytes())
        second = export_static_drillholes(self.context, backend=_UnavailableBackend())
        after = (second.staging_paths[0].read_bytes(), second.manifest_path.read_bytes())
        self.assertEqual(before, after)
        manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(second.staging_paths[0].read_bytes()).hexdigest()
        self.assertEqual(manifest["staging_csv_hash"], digest)
        self.assertEqual(set(manifest["source_artifact_hashes"]), {"assay_xyz.csv", "drillhole_trajectory.csv"})

    def test_no_fake_static_dm_without_backend(self) -> None:
        result = export_static_drillholes(self.context, backend=_UnavailableBackend())
        self.assertEqual(result.backend_status, "NOT_AVAILABLE")
        self.assertFalse(result.native_created)
        self.assertFalse(result.native_paths[0].exists())

    def test_mocked_static_native_export_is_verified(self) -> None:
        result = export_static_drillholes(self.context, backend=_SuccessfulBackend())
        self.assertTrue(result.native_created)
        self.assertEqual(result.native_paths[0].name, "drillholes_m01.dm")

    def test_pt_tr_schemas_references_extents_and_full_tin(self) -> None:
        result = export_topographic_wireframe(self.context, backend=_UnavailableBackend())
        pt_fields, points = self._csv(result.staging_paths[0])
        tr_fields, triangles = self._csv(result.staging_paths[1])
        self.assertEqual(pt_fields, PT_FIELDS)
        self.assertEqual(tr_fields, TR_FIELDS)
        self.assertEqual((result.point_count, result.triangle_count), (4, 2))
        pids = [int(row["PID"]) for row in points]
        triangle_ids = [int(row["TRIANGLE"]) for row in triangles]
        self.assertEqual(len(pids), len(set(pids)))
        self.assertEqual(len(triangle_ids), len(set(triangle_ids)))
        for row in triangles:
            refs = [int(row[field]) for field in ("PID1", "PID2", "PID3")]
            self.assertEqual(len(refs), len(set(refs)))
            self.assertTrue(set(refs).issubset(set(pids)))
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["coordinate_extents"], {"x_min": 0.0, "x_max": 1.0, "y_min": 0.0, "y_max": 1.0, "z_min": 100.0, "z_max": 100.0})

    def test_pt_tr_staging_and_manifest_are_deterministic(self) -> None:
        first = export_topographic_wireframe(self.context, backend=_UnavailableBackend())
        before = tuple(path.read_bytes() for path in (*first.staging_paths, first.manifest_path))
        second = export_topographic_wireframe(self.context, backend=_UnavailableBackend())
        after = tuple(path.read_bytes() for path in (*second.staging_paths, second.manifest_path))
        self.assertEqual(before, after)

    def test_no_fake_wireframe_pair_without_backend(self) -> None:
        result = export_topographic_wireframe(self.context, backend=_UnavailableBackend())
        self.assertFalse(result.native_created)
        self.assertTrue(all(not path.exists() for path in result.native_paths))

    def test_mocked_native_wireframe_uses_paired_base_names(self) -> None:
        result = export_topographic_wireframe(self.context, backend=_SuccessfulBackend())
        self.assertTrue(result.native_created)
        self.assertEqual([path.name for path in result.native_paths], ["topography_m01pt.dm", "topography_m01tr.dm"])

    def test_mocked_partial_wireframe_never_reports_success(self) -> None:
        result = export_topographic_wireframe(self.context, backend=_PartialBackend())
        self.assertFalse(result.native_created)
        self.assertEqual(result.backend_status, "ERROR")
        self.assertTrue(all(not path.exists() for path in result.native_paths))

    def test_exports_do_not_modify_source_data(self) -> None:
        sources = sorted(path for path in self.paths.data_root.rglob("*") if path.is_file())
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        export_static_drillholes(self.context, backend=_UnavailableBackend())
        export_topographic_wireframe(self.context, backend=_UnavailableBackend())
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
