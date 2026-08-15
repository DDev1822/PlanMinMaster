from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from planminpy.core.paths import (
    DatasetNotFoundError,
    DuplicateDatasetError,
    MalformedManifestError,
    ProjectPaths,
    resolve_dataset,
)


def write_manifest(
    data_root: Path,
    physical_folder: str,
    *,
    project_id: str = "quebrada_verde",
    dataset_id: str = "DS00",
    release_id: str = "EXP03",
) -> Path:
    dataset_path = data_root / physical_folder
    dataset_path.mkdir(parents=True)
    manifest_path = dataset_path / "release_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "dataset_id": dataset_id,
                "release_id": release_id,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


class DatasetResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary.name)
        self.data_root = self.project_root / "Data"
        self.data_root.mkdir()
        self.paths = ProjectPaths.from_project_root(self.project_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_canonical_dataset_resolves_from_different_physical_folder(self) -> None:
        write_manifest(self.data_root, "PL00")
        resolved = resolve_dataset(self.paths, "DS00", "EXP03")
        self.assertEqual(resolved.dataset_path.name, "PL00")
        self.assertEqual(resolved.dataset_id, "DS00")
        self.assertEqual(resolved.release_id, "EXP03")

    def test_optional_project_identity_is_validated(self) -> None:
        write_manifest(self.data_root, "PL00")
        resolved = resolve_dataset(
            self.paths, "DS00", "EXP03", project_id="quebrada_verde"
        )
        self.assertEqual(resolved.project_id, "quebrada_verde")
        with self.assertRaises(DatasetNotFoundError):
            resolve_dataset(self.paths, "DS00", "EXP03", project_id="other_project")

    def test_missing_dataset_fails(self) -> None:
        write_manifest(self.data_root, "PL00", dataset_id="DS01")
        with self.assertRaises(DatasetNotFoundError):
            resolve_dataset(self.paths, "DS00", "EXP03")

    def test_duplicate_canonical_identity_fails(self) -> None:
        write_manifest(self.data_root, "PL00")
        write_manifest(self.data_root, "PL01")
        with self.assertRaises(DuplicateDatasetError):
            resolve_dataset(self.paths, "DS00", "EXP03")

    def test_malformed_manifest_fails(self) -> None:
        folder = self.data_root / "PL00"
        folder.mkdir()
        (folder / "release_manifest.json").write_text(
            json.dumps({"dataset_id": "DS00", "release_id": "EXP03"}),
            encoding="utf-8",
        )
        with self.assertRaises(MalformedManifestError):
            resolve_dataset(self.paths, "DS00", "EXP03")


if __name__ == "__main__":
    unittest.main()
