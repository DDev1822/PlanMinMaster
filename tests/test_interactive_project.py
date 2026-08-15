from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from interactive_test_support import make_interactive_project, terminal_with_inputs
from planminpy.interactive.project import (
    ProjectInspectionError,
    configure_active_project,
    inspect_exploration_directory,
    inspect_topography,
    resolve_user_path,
)


class InteractiveProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths, self.active = make_interactive_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_exploration_directory_is_inspected_read_only(self) -> None:
        result = inspect_exploration_directory(self.active.exploration_data_path)
        self.assertEqual(result.counts["collar.csv"], 1)
        self.assertEqual(result.counts["assay.csv"], 2)
        self.assertEqual(result.analytical_variables["cu_pct"], "VARIABLE")
        self.assertEqual(result.analytical_variables["mo_pct"], "CONSTANT_ZERO")

    def test_missing_required_source_is_rejected(self) -> None:
        (self.active.exploration_data_path / "survey.csv").unlink()
        with self.assertRaisesRegex(ProjectInspectionError, "survey.csv"):
            inspect_exploration_directory(self.active.exploration_data_path)

    def test_optional_files_are_not_required(self) -> None:
        result = inspect_exploration_directory(self.active.exploration_data_path)
        self.assertFalse((result.path / "data_dictionary.csv").exists())
        self.assertEqual(result.manifest["dataset_id"], "DS00")

    def test_explicit_topography_path_is_accepted(self) -> None:
        result = inspect_topography(self.active.topography_path)
        self.assertEqual(result.path, self.active.topography_path)
        self.assertEqual(result.point_count, 4)

    def test_invalid_topography_schema_is_rejected(self) -> None:
        invalid = self.root / "invalid.csv"
        invalid.write_text("X,Y,ELEVATION\n0,0,1\n", encoding="utf-8")
        with self.assertRaisesRegex(ProjectInspectionError, "schema"):
            inspect_topography(invalid)

    def test_relative_source_path_resolves_from_project_root(self) -> None:
        resolved = resolve_user_path(self.root, "Data/arbitrary_release_folder")
        self.assertEqual(resolved, self.active.exploration_data_path)

    def test_user_can_reject_confirmation_without_activating_inputs(self) -> None:
        io, output = terminal_with_inputs(["y", "n", "0"])
        selected = configure_active_project(self.paths, io)
        self.assertIsNone(selected)
        self.assertIn("Dataset was not activated", "\n".join(output))

    def test_active_context_accepts_confirmed_explicit_sources(self) -> None:
        context = self.active.create_context(
            self.paths,
            {"execution_mode": "INTERACTIVE"},
        )
        self.assertEqual(context.dataset_path, self.active.exploration_data_path)
        self.assertEqual(context.topography_path, self.active.topography_path)
        self.assertTrue(context.dataset_path.is_relative_to(context.data_root))

    def test_inspection_does_not_change_source_hashes(self) -> None:
        files = sorted(self.active.exploration_data_path.iterdir()) + [
            self.active.topography_path
        ]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        inspect_exploration_directory(self.active.exploration_data_path)
        inspect_topography(self.active.topography_path)
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
