from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from interactive_test_support import make_interactive_project, terminal_with_inputs
from planminpy.interactive.project import (
    configure_active_project,
    discover_exploration_datasets,
    discover_topographies,
)


class DataDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths, self.active = make_interactive_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _add_dataset(self) -> Path:
        target = self.paths.data_root / "not_a_hardcoded_dataset_name"
        shutil.copytree(self.active.exploration_data_path, target)
        manifest_path = target / "release_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(
            {
                "project_id": "cerro_azul",
                "project_name": "Cerro Azul",
                "dataset_id": "DS01",
                "release_id": "EXP01",
            }
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return target

    def _add_topography(self) -> Path:
        target = self.paths.data_root / "unusual_surface_name.csv"
        target.write_bytes(self.active.topography_path.read_bytes())
        return target

    def test_data_root_is_project_relative_standard_location(self) -> None:
        self.assertEqual(self.paths.data_root, (self.root / "Data").resolve())

    def test_exactly_one_valid_dataset_is_auto_detected(self) -> None:
        candidates = discover_exploration_datasets(self.paths.data_root)
        self.assertEqual([item.path for item in candidates], [self.active.exploration_data_path])

    def test_multiple_datasets_produce_selection_menu(self) -> None:
        selected_path = self._add_dataset()
        io, output = terminal_with_inputs(["y", "2", "y", "y", "y"])
        selected = configure_active_project(self.paths, io)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.exploration_data_path, selected_path)
        self.assertIn("EXPLORATION DATASETS DETECTED", "\n".join(output))

    def test_dataset_detection_is_content_based_not_folder_named(self) -> None:
        self.assertEqual(
            discover_exploration_datasets(self.paths.data_root)[0].path.name,
            "arbitrary_release_folder",
        )

    def test_invalid_directory_is_ignored(self) -> None:
        invalid = self.paths.data_root / "PL00"
        invalid.mkdir()
        (invalid / "release_manifest.json").write_text("{}", encoding="utf-8")
        self.assertEqual(len(discover_exploration_datasets(self.paths.data_root)), 1)

    def test_no_dataset_has_useful_rescan_message(self) -> None:
        (self.active.exploration_data_path / "survey.csv").unlink()
        io, output = terminal_with_inputs(["y", "0"])
        self.assertIsNone(configure_active_project(self.paths, io))
        rendered = "\n".join(output)
        self.assertIn("No valid exploration dataset", rendered)
        self.assertIn("release_manifest.json", rendered)
        self.assertIn("[R] Rescan Data", rendered)

    def test_exactly_one_topography_is_auto_detected_by_schema(self) -> None:
        candidates = discover_topographies(self.paths.data_root)
        self.assertEqual([item.path for item in candidates], [self.active.topography_path])
        self.assertEqual(candidates[0].point_count, 4)

    def test_multiple_topographies_produce_selection_menu(self) -> None:
        selected_path = self._add_topography()
        io, output = terminal_with_inputs(["y", "y", "2", "y", "y"])
        selected = configure_active_project(self.paths, io)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.topography_path, selected_path)
        self.assertIn("TOPOGRAPHY FILES DETECTED", "\n".join(output))

    def test_topography_filename_is_only_a_hint(self) -> None:
        self.active.topography_path.rename(
            self.paths.data_root / "coordinates_2026_final.csv"
        )
        candidates = discover_topographies(self.paths.data_root)
        self.assertEqual(candidates[0].path.name, "coordinates_2026_final.csv")

    def test_no_topography_is_handled_safely(self) -> None:
        self.active.topography_path.unlink()
        io, output = terminal_with_inputs(["y", "y", "0"])
        self.assertIsNone(configure_active_project(self.paths, io))
        self.assertIn("No valid topography CSV", "\n".join(output))

    def test_rejecting_dataset_does_not_activate_it(self) -> None:
        io, _ = terminal_with_inputs(["y", "n", "0"])
        self.assertIsNone(configure_active_project(self.paths, io))

    def test_rejecting_topography_does_not_activate_it(self) -> None:
        io, _ = terminal_with_inputs(["y", "y", "n", "0"])
        self.assertIsNone(configure_active_project(self.paths, io))

    def test_confirmed_sources_become_active_session(self) -> None:
        io, _ = terminal_with_inputs(["y", "y", "y", "y"])
        selected = configure_active_project(self.paths, io)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.dataset_id, "DS00")
        self.assertEqual(selected.source_counts["topography.csv"], 4)

    def test_standard_workflow_never_prompts_for_arbitrary_path(self) -> None:
        io, output = terminal_with_inputs(["y", "y", "y", "y"])
        configure_active_project(self.paths, io)
        rendered = "\n".join(output)
        self.assertNotIn("Exploration data directory", rendered)
        self.assertNotIn("Topography file (", rendered)

    def test_core_context_contains_no_pilot_topography_filename(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "planminpy"
            / "core"
            / "context.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Topopl.csv", source)


if __name__ == "__main__":
    unittest.main()
