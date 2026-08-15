from __future__ import annotations

import ast
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from planminpy import cli
from planminpy.core.paths import PathSafetyError, ProjectPaths


class PathAndEntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary.name)
        (self.project_root / "Data").mkdir()
        self.paths = ProjectPaths.from_project_root(self.project_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_generated_paths_remain_below_outputs(self) -> None:
        generated = self.paths.output_path("project", "report.json")
        self.assertTrue(generated.is_relative_to(self.paths.output_root))
        self.assertFalse(generated.is_relative_to(self.paths.data_root))

    def test_traversal_and_absolute_paths_are_rejected(self) -> None:
        with self.assertRaises(PathSafetyError):
            self.paths.output_path("..", "escape.json")
        with self.assertRaises(PathSafetyError):
            self.paths.output_path(self.project_root / "external.json")

    def test_data_cannot_be_configured_as_output_root(self) -> None:
        with self.assertRaises(PathSafetyError):
            ProjectPaths(
                self.project_root,
                self.project_root / "Data",
                self.project_root / "Data",
            )

    def test_root_main_is_only_thin_delegation(self) -> None:
        root_main = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(root_main.read_text(encoding="utf-8"))
        self.assertEqual(len(tree.body), 2)
        self.assertIsInstance(tree.body[0], ast.ImportFrom)
        self.assertIsInstance(tree.body[1], ast.If)
        self.assertEqual(tree.body[0].module, "planminpy.cli")
        self.assertEqual([alias.name for alias in tree.body[0].names], ["main"])

    def test_cli_list_succeeds(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = cli.main(["list"], project_root=self.project_root)
        self.assertEqual(exit_code, 0)
        self.assertIn("m01", output.getvalue())
        self.assertIn("1.1.0", output.getvalue())

    def test_cli_controlled_failure_is_nonzero_without_traceback(self) -> None:
        error = io.StringIO()
        with redirect_stderr(error):
            exit_code = cli.main(
                ["run", "m01", "--dataset", "DS99", "--release", "EXP03"],
                project_root=self.project_root,
            )
        self.assertNotEqual(exit_code, 0)
        self.assertIn("error:", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
