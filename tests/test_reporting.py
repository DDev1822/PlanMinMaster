from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from planminpy.core.contracts import ModuleResult, ModuleStatus
from planminpy.core.paths import ProjectPaths
from planminpy.reporting.reporter import Reporter


def result_for(module_id: str, summary: str) -> ModuleResult:
    now = datetime.now(timezone.utc)
    return ModuleResult(
        module_id=module_id,
        module_version="0.1.0",
        status=ModuleStatus.COMPLETED,
        project_id="quebrada_verde",
        dataset_id="DS00",
        release_id="EXP03",
        started_at=now,
        completed_at=now,
        summary=summary,
        metrics={"value": 1},
    )


class ReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temporary.name)
        (self.project_root / "Data").mkdir()
        self.paths = ProjectPaths.from_project_root(self.project_root)
        self.reporter = Reporter(self.paths)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_first_result_creates_one_section_and_both_renderings(self) -> None:
        output = self.reporter.update(result_for("m01", "first"))
        self.assertTrue(output.state_path.is_file())
        self.assertTrue(output.markdown_path.is_file())
        self.assertEqual(len(output.state.sections), 1)
        self.assertTrue(output.state_path.is_relative_to(self.paths.output_root))
        markdown = output.markdown_path.read_text(encoding="utf-8")
        self.assertIn("Project: `quebrada_verde`", markdown)
        self.assertIn("Status: `COMPLETED`", markdown)

    def test_rerun_upserts_latest_section_without_duplication(self) -> None:
        self.reporter.update(result_for("m01", "first"))
        output = self.reporter.update(result_for("m01", "latest"))
        self.assertEqual(len(output.state.sections), 1)
        self.assertEqual(output.state.sections[0].result.summary, "latest")

        serialized = json.loads(output.state_path.read_text(encoding="utf-8"))
        self.assertEqual(len(serialized["sections"]), 1)
        self.assertEqual(serialized["sections"][0]["summary"], "latest")

    def test_second_module_preserves_first_with_deterministic_order(self) -> None:
        self.reporter.update(result_for("m02", "second"))
        output = self.reporter.update(result_for("m01", "first"))
        self.assertEqual(
            [section.module_id for section in output.state.sections],
            ["m01", "m02"],
        )
        serialized = json.loads(output.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [section["module_id"] for section in serialized["sections"]],
            ["m01", "m02"],
        )
        expected_parent = (
            self.paths.output_root
            / "quebrada_verde"
            / "DS00"
            / "EXP03"
            / "report"
        )
        self.assertEqual(output.state_path.parent, expected_parent)


if __name__ == "__main__":
    unittest.main()
