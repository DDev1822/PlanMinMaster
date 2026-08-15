"""Registry-driven terminal dashboard for classroom module orchestration."""

from __future__ import annotations

import json
import os
import webbrowser
from pathlib import Path
from typing import Callable

from planminpy.core.contracts import ModuleResult, ModuleStatus, PlanMinPyError
from planminpy.core.paths import ProjectPaths
from planminpy.core.registry import ModuleAvailability, ModuleDescriptor, ModuleRegistry
from planminpy.core.runner import ModuleRunner
from planminpy.interactive.contracts import (
    ActiveProject,
    TerminalIO,
    WizardAction,
    WizardRequest,
)
from planminpy.interactive.project import configure_active_project
from planminpy.reporting.contracts import ReportState
from planminpy.reporting.reporter import Reporter, ReporterOutput


def safe_open_path(
    path: Path,
    io: TerminalIO,
    *,
    opener: Callable[[Path], object] | None = None,
) -> bool:
    resolved = path.resolve(strict=False)
    try:
        if opener is not None:
            opener(resolved)
        elif hasattr(os, "startfile"):
            os.startfile(str(resolved))  # type: ignore[attr-defined]
        else:
            if not webbrowser.open(resolved.as_uri()):
                raise OSError("no desktop opener accepted the path")
        return True
    except Exception as exc:
        io.write(f"Could not open automatically: {exc}")
        io.write(f"Location: {resolved}")
        return False


def safe_open_web_path(
    path: Path,
    io: TerminalIO,
    *,
    opener: Callable[[str], object] | None = None,
) -> bool:
    """Open an HTML artifact explicitly through the user's web browser."""

    resolved = path.resolve(strict=False)
    uri = resolved.as_uri()
    try:
        accepted = (opener or webbrowser.open)(uri)
        if accepted is False:
            raise OSError("no web browser accepted the document URI")
        return True
    except Exception as exc:
        io.write(f"Could not open the web browser automatically: {exc}")
        io.write(f"Location: {resolved}")
        return False


def last_run_label(result: ModuleResult | None) -> str:
    if result is None:
        return "NEVER_RUN"
    if result.status is ModuleStatus.FAILED:
        return "FAILED"
    if result.status is ModuleStatus.REQUIRES_REVIEW:
        return "REQUIRES_REVIEW"
    if result.status is ModuleStatus.NOT_IMPLEMENTED:
        return "NOT_IMPLEMENTED"
    validation = str(
        result.metrics.get("validation_status")
        or result.metrics.get("readiness_verdict")
        or ""
    )
    if validation == "PASS_WITH_WARNINGS" or result.warnings:
        return "COMPLETED_WITH_WARNINGS"
    return "COMPLETED"


class InteractiveDashboard:
    def __init__(
        self,
        paths: ProjectPaths,
        registry: ModuleRegistry,
        *,
        runner: ModuleRunner | None = None,
        reporter: Reporter | None = None,
        io: TerminalIO | None = None,
        opener: Callable[[Path], object] | None = None,
        browser_opener: Callable[[str], object] | None = None,
        project_configurator: Callable[[ProjectPaths, TerminalIO], ActiveProject | None]
        = configure_active_project,
    ) -> None:
        self.paths = paths
        self.registry = registry
        self.runner = runner or ModuleRunner(registry)
        self.reporter = reporter or Reporter(paths)
        self.io = io or TerminalIO()
        self._opener = opener
        self._browser_opener = browser_opener
        self._project_configurator = project_configurator
        self.project: ActiveProject | None = None
        self._settings: dict[str, dict[str, object]] = {}
        self._last_results: dict[str, ModuleResult] = {}

    def _open(self, path: Path) -> bool:
        return safe_open_path(path, self.io, opener=self._opener)

    def _open_web(self, path: Path) -> bool:
        return safe_open_web_path(path, self.io, opener=self._browser_opener)

    def _report_paths(self) -> tuple[Path | None, Path | None]:
        if self.project is None:
            return None, None
        parts = (
            self.project.project_id,
            self.project.dataset_id,
            self.project.release_id,
            "report",
        )
        return (
            self.paths.output_path(*parts, "report_state.json"),
            self.paths.output_path(*parts, "report.md"),
        )

    def _load_report_state(self) -> ReportState | None:
        state_path, _ = self._report_paths()
        if state_path is None or not state_path.is_file():
            return None
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("report state must be an object")
            return ReportState.from_dict(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, PlanMinPyError) as exc:
            self.io.write(f"Warning: cumulative report state could not be read: {exc}")
            return None

    def _last_result(self, module_id: str) -> ModuleResult | None:
        cached = self._last_results.get(module_id)
        if cached is not None:
            return cached
        state = self._load_report_state()
        if state is None:
            return None
        for section in state.sections:
            if section.module_id == module_id:
                self._last_results[module_id] = section.result
                return section.result
        return None

    def _print_dashboard(self, descriptors: tuple[ModuleDescriptor, ...]) -> None:
        self.io.write("=" * 60)
        self.io.write("PLANMINPY")
        self.io.write("MINE PLANNING SYSTEM")
        if self.project is None:
            self.io.write("Project: Not configured")
            self.io.write("Dataset: Not configured")
            self.io.write("Release: Not configured")
            self.io.write("Topography: Not configured")
        else:
            self.io.write(
                f"Project: {self.project.project_name} | "
                f"{self.project.dataset_id} | {self.project.release_id}"
            )
        self.io.write("=" * 60)
        self.io.write()
        self.io.write("MODULES")
        self.io.write("-" * 60)
        self.io.write()
        for index, descriptor in enumerate(descriptors, start=1):
            self.io.write(f"[{index}] {descriptor.title}")
            self.io.write(f"    {descriptor.availability.value}")
            result = self._last_result(descriptor.module_id) if self.project else None
            self.io.write(f"    Last run: {last_run_label(result)}")
            if result is not None:
                self.io.write(f"    Dataset: {result.dataset_id} / {result.release_id}")
            self.io.write()
        self.io.write("-" * 60)
        self.io.write("[D] Configure / change project data")
        self.io.write("[R] View cumulative report")
        self.io.write("[O] View output location")
        self.io.write("[0] Exit")
        self.io.write("-" * 60)

    def _wizard_request(
        self,
        descriptor: ModuleDescriptor,
        *,
        report_output: ReporterOutput | None = None,
    ) -> WizardRequest:
        state_path, markdown_path = self._report_paths()
        if report_output is not None:
            state_path = report_output.state_path
            markdown_path = report_output.markdown_path
        return WizardRequest(
            paths=self.paths,
            project=self.project,
            settings=self._settings.get(descriptor.module_id, {}),
            last_result=self._last_result(descriptor.module_id),
            io=self.io,
            open_path=self._open,
            report_state_path=state_path,
            report_markdown_path=markdown_path,
            open_web_path=self._open_web,
        )

    def _configure_project(self) -> bool:
        selected = self._project_configurator(self.paths, self.io)
        if selected is None:
            return False
        self.project = selected
        self._settings.clear()
        self._last_results.clear()
        return True

    def _run_selected_module(self, descriptor: ModuleDescriptor) -> None:
        wizard = self.registry.load_wizard(descriptor.module_id)
        while True:
            request = self._wizard_request(descriptor)
            outcome = wizard.interact(request)
            self._settings[descriptor.module_id] = dict(outcome.settings)
            if outcome.action is WizardAction.BACK:
                return
            if outcome.action is WizardAction.CONFIGURE_DATA:
                self._configure_project()
                continue
            if self.project is None:
                self.io.write("Configure and confirm project data before execution.")
                continue
            context = self.project.create_context(self.paths, outcome.settings)
            self.io.write()
            self.io.write(f"Executing {descriptor.module_id.upper()}...")
            try:
                result = self.runner.run(descriptor.module_id, context)
                report_output = self.reporter.update(result)
            except PlanMinPyError as exc:
                self.io.write(f"Execution failed: {exc}")
                continue
            self._last_results[descriptor.module_id] = result
            result_request = self._wizard_request(
                descriptor,
                report_output=report_output,
            )
            wizard.show_result(result, result_request)
            return

    def run(self) -> int:
        initial_descriptors = self.registry.list_modules()
        if (
            self.project is None
            and any(
                descriptor.availability is ModuleAvailability.AVAILABLE
                for descriptor in initial_descriptors
            )
            and not self._configure_project()
        ):
            self.io.write("PlanMinPy session closed.")
            return 0
        while True:
            descriptors = self.registry.list_modules()
            self._print_dashboard(descriptors)
            selection = self.io.prompt("Select the module you want to work with or an option:").lower()
            if selection == "0":
                self.io.write("PlanMinPy session closed.")
                return 0
            if selection == "d":
                self._configure_project()
                continue
            if selection == "r":
                _, markdown_path = self._report_paths()
                if markdown_path is None or not markdown_path.is_file():
                    self.io.write("No cumulative report is available for the active project.")
                else:
                    self._open(markdown_path)
                continue
            if selection == "o":
                self._open(self.paths.output_root)
                continue
            try:
                index = int(selection) - 1
            except ValueError:
                self.io.write("Select a listed module or dashboard option.")
                continue
            if index < 0 or index >= len(descriptors):
                self.io.write("Select a listed module or dashboard option.")
                continue
            descriptor = descriptors[index]
            if descriptor.availability is not ModuleAvailability.AVAILABLE:
                self.io.write(f"{descriptor.module_id.upper()} is not implemented yet.")
                continue
            try:
                self._run_selected_module(descriptor)
            except PlanMinPyError as exc:
                self.io.write(f"Cannot open module workflow: {exc}")
