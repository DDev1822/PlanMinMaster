from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from interactive_test_support import (
    make_interactive_project,
    result_for,
    terminal_with_inputs,
)
from planminpy import cli
from planminpy.core.registry import (
    ModuleAvailability,
    ModuleDescriptor,
    ModuleRegistry,
    ModuleUnavailableError,
)
from planminpy.core.runner import ModuleRunner
from planminpy.interactive.contracts import WizardAction, WizardOutcome
from planminpy.interactive.dashboard import (
    InteractiveDashboard,
    last_run_label,
    safe_open_path,
    safe_open_web_path,
)
from planminpy.reporting.reporter import Reporter


class _FakeWizard:
    def __init__(self, action: WizardAction = WizardAction.RUN) -> None:
        self.action = action
        self.result_shown = False

    def interact(self, _request):
        return WizardOutcome(
            self.action,
            {
                "execution_mode": "INTERACTIVE",
                "preliminary_analysis_method": "INTERCEPTS_ONLY",
            },
        )

    def show_result(self, _result, _request) -> None:
        self.result_shown = True


class _SpyRunner:
    def __init__(self, module_id: str, version: str) -> None:
        self.calls: list[tuple[str, object]] = []
        self.module_id = module_id
        self.version = version

    def run(self, module_id, context):
        self.calls.append((module_id, context))
        return result_for(module_id=self.module_id, version=self.version)


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths, self.active = make_interactive_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_cli_no_arguments_selects_interactive_mode(self) -> None:
        with patch("planminpy.cli.InteractiveDashboard.run", return_value=17) as run:
            self.assertEqual(cli.main([], project_root=self.root), 17)
        run.assert_called_once_with()

    def test_cli_list_remains_noninteractive(self) -> None:
        output = io.StringIO()
        with patch(
            "planminpy.cli.InteractiveDashboard.run",
            side_effect=AssertionError("interactive dashboard must not run"),
        ), redirect_stdout(output):
            code = cli.main(["list"], project_root=self.root)
        self.assertEqual(code, 0)
        self.assertIn("m01", output.getvalue())

    def test_cli_run_remains_noninteractive(self) -> None:
        error = io.StringIO()
        with patch(
            "planminpy.cli.InteractiveDashboard.run",
            side_effect=AssertionError("interactive dashboard must not run"),
        ), redirect_stderr(error):
            code = cli.main(
                ["run", "m01", "--dataset", "DS99", "--release", "EXP03"],
                project_root=self.root,
            )
        self.assertEqual(code, 2)
        self.assertIn("error:", error.getvalue())

    def test_module_menu_is_generated_from_registry(self) -> None:
        descriptors = (
            ModuleDescriptor(
                "m02",
                "M02 — Synthetic Future Module",
                "0.0.0",
                "fake.m02",
                "run",
                availability=ModuleAvailability.NOT_IMPLEMENTED,
            ),
            ModuleDescriptor(
                "m77",
                "M77 — Registry Proof",
                "0.0.0",
                "fake.m77",
                "run",
                availability=ModuleAvailability.NOT_IMPLEMENTED,
            ),
        )
        io_adapter, output = terminal_with_inputs(["0"])
        dashboard = InteractiveDashboard(
            self.paths,
            ModuleRegistry(descriptors),
            io=io_adapter,
        )
        self.assertEqual(dashboard.run(), 0)
        rendered = "\n".join(output)
        self.assertIn("M02 — Synthetic Future Module", rendered)
        self.assertIn("M77 — Registry Proof", rendered)

    def test_unavailable_module_cannot_execute(self) -> None:
        registry = ModuleRegistry(
            (
                ModuleDescriptor(
                    "m02",
                    "M02",
                    "0.0.0",
                    "fake.m02",
                    "run",
                    availability=ModuleAvailability.NOT_IMPLEMENTED,
                ),
            )
        )
        with self.assertRaises(ModuleUnavailableError):
            ModuleRunner(registry).run("m02", None)  # type: ignore[arg-type]

    def test_dashboard_refuses_unavailable_module_without_crashing(self) -> None:
        registry = ModuleRegistry(
            (
                ModuleDescriptor(
                    "m02",
                    "M02 — Compositing & EDA",
                    "0.0.0",
                    "fake.m02",
                    "run",
                    availability=ModuleAvailability.NOT_IMPLEMENTED,
                ),
            )
        )
        io_adapter, output = terminal_with_inputs(["1", "0"])
        dashboard = InteractiveDashboard(self.paths, registry, io=io_adapter)
        self.assertEqual(dashboard.run(), 0)
        self.assertIn("not implemented yet", "\n".join(output))

    def _registry_for_wizard(self, wizard: _FakeWizard) -> ModuleRegistry:
        def importer(name: str) -> ModuleType:
            module = ModuleType(name)
            module.create_wizard = lambda: wizard
            return module

        return ModuleRegistry(
            (
                ModuleDescriptor(
                    "mx1",
                    "MX1 — Future Wizard Contract",
                    "0.1.0",
                    "fake.module",
                    "run",
                    wizard_import_path="fake.wizard",
                    wizard_callable_name="create_wizard",
                ),
            ),
            importer=importer,
        )

    def test_dashboard_execution_goes_through_module_runner_contract(self) -> None:
        wizard = _FakeWizard()
        runner = _SpyRunner("mx1", "0.1.0")
        io_adapter, _ = terminal_with_inputs(["d", "1", "0"])
        dashboard = InteractiveDashboard(
            self.paths,
            self._registry_for_wizard(wizard),
            runner=runner,  # type: ignore[arg-type]
            io=io_adapter,
            project_configurator=lambda _paths, _io: self.active,
        )
        self.assertEqual(dashboard.run(), 0)
        self.assertEqual([call[0] for call in runner.calls], ["mx1"])
        self.assertTrue(wizard.result_shown)

    def test_future_module_wizard_can_return_without_execution(self) -> None:
        wizard = _FakeWizard(WizardAction.BACK)
        runner = _SpyRunner("mx1", "0.1.0")
        io_adapter, _ = terminal_with_inputs(["d", "1", "0"])
        dashboard = InteractiveDashboard(
            self.paths,
            self._registry_for_wizard(wizard),
            runner=runner,  # type: ignore[arg-type]
            io=io_adapter,
            project_configurator=lambda _paths, _io: self.active,
        )
        dashboard.run()
        self.assertEqual(runner.calls, [])

    def test_last_run_state_is_resolved_from_cumulative_report(self) -> None:
        result = result_for(
            warnings=("review warning",),
            metrics={"validation_status": "PASS_WITH_WARNINGS"},
        )
        Reporter(self.paths).update(result)
        io_adapter, _ = terminal_with_inputs(["0"])
        dashboard = InteractiveDashboard(
            self.paths,
            ModuleRegistry(
                (
                    ModuleDescriptor(
                        "m01", "M01", "1.0.0", "fake.m01", "run"
                    ),
                )
            ),
            io=io_adapter,
        )
        dashboard.project = self.active
        loaded = dashboard._last_result("m01")
        self.assertIsNotNone(loaded)
        self.assertEqual(last_run_label(loaded), "COMPLETED_WITH_WARNINGS")
        self.assertEqual(last_run_label(None), "NEVER_RUN")

    def test_output_opening_failure_does_not_raise(self) -> None:
        io_adapter, output = terminal_with_inputs([])

        def fail(_path: Path) -> None:
            raise OSError("desktop unavailable")

        self.assertFalse(
            safe_open_path(self.root / "missing.html", io_adapter, opener=fail)
        )
        self.assertIn("desktop unavailable", "\n".join(output))

    def test_html_opening_uses_explicit_file_uri(self) -> None:
        io_adapter, _ = terminal_with_inputs([])
        opened: list[str] = []
        self.assertTrue(
            safe_open_web_path(
                self.root / "view with spaces.html",
                io_adapter,
                opener=lambda uri: opened.append(uri) or True,
            )
        )
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].startswith("file:///"))
        self.assertIn("view%20with%20spaces.html", opened[0])


if __name__ == "__main__":
    unittest.main()
