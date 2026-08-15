"""M01-owned terminal wizard; scientific calculations remain in the module."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from planminpy.core.contracts import ModuleResult
from planminpy.interactive.contracts import (
    TerminalIO,
    WizardAction,
    WizardOutcome,
    WizardRequest,
)
from planminpy.modules.m01.config import load_config
from planminpy.modules.m01.datamine import (
    DatamineExportError,
    export_static_drillholes,
    export_topographic_wireframe,
)
from planminpy.modules.m01.technical_summary import render_technical_summary_text


ELEMENT_LABELS = {
    "cu_pct": "Cu (%)",
    "mo_pct": "Mo (%)",
    "au_gt": "Au (g/t)",
}


def _defaults(project_root: Path) -> dict[str, Any]:
    config = load_config(project_root)
    return {
        "execution_mode": "INTERACTIVE",
        "primary_element": config.primary_element,
        "reference_grade_analysis_enabled": config.reference_grade_enabled_by_default,
        "reference_grade": None,
        "topography_ok_tolerance_m": config.topography_ok_tolerance_m,
        "topography_review_tolerance_m": config.topography_review_tolerance_m,
    }


def prompt_nonnegative_float(io: TerminalIO, label: str, default: float) -> float:
    while True:
        raw = io.prompt(f"{label} [{default}]:")
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            io.write("Enter a numeric value.")
            continue
        if value < 0.0:
            io.write("The value cannot be negative.")
            continue
        return value


def prompt_topography_tolerances(
    io: TerminalIO,
    ok_default: float,
    review_default: float,
) -> tuple[float, float]:
    while True:
        io.write()
        io.write("COLLAR — TOPOGRAPHY VALIDATION")
        ok_tolerance = prompt_nonnegative_float(io, "OK tolerance (m)", ok_default)
        review_tolerance = prompt_nonnegative_float(
            io, "Review tolerance (m)", review_default
        )
        if ok_tolerance < review_tolerance:
            return ok_tolerance, review_tolerance
        io.write("Tolerances must satisfy 0 <= OK tolerance < review tolerance.")


def _yes(io: TerminalIO, label: str) -> bool:
    """Return False for blank and all responses other than an explicit yes."""

    return io.prompt(label).strip().lower() in {"y", "yes"}


class M01Wizard:
    def _configure_parameters(
        self,
        request: WizardRequest,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        io = request.io
        if request.project is None:
            io.write("Configure project data before selecting M01 analysis parameters.")
            return settings

        variables = request.project.analytical_variables
        io.write()
        io.write("PRIMARY ANALYTICAL VARIABLE")
        for index, field_name in enumerate(ELEMENT_LABELS, start=1):
            classification = variables.get(field_name, "EMPTY")
            support = (
                "SUPPORTED"
                if field_name == "cu_pct"
                else "DETECTED — NOT SUITABLE FOR DISTRIBUTION/INTERCEPT ANALYSIS"
            )
            io.write(
                f"[{index}] {ELEMENT_LABELS[field_name]:<12} "
                f"{classification} / {support}"
            )
        while True:
            selected = io.prompt("Select primary variable [1]:") or "1"
            if selected == "1":
                settings["primary_element"] = "cu_pct"
                break
            if selected in {"2", "3"}:
                field_name = tuple(ELEMENT_LABELS)[int(selected) - 1]
                io.write(
                    f"{ELEMENT_LABELS[field_name]} is "
                    f"{variables.get(field_name, 'EMPTY')} in this release and is not "
                    "suitable for the principal M01 analysis. Select Cu."
                )
                continue
            io.write("Select one of the listed analytical variables.")

        ok_tolerance, review_tolerance = prompt_topography_tolerances(
            io,
            float(settings["topography_ok_tolerance_m"]),
            float(settings["topography_review_tolerance_m"]),
        )
        settings["topography_ok_tolerance_m"] = ok_tolerance
        settings["topography_review_tolerance_m"] = review_tolerance

        io.write()
        io.write("OPTIONAL INTERCEPT ANALYSIS")
        io.write()
        enabled = _yes(
            io,
            "Would you like to analyze drillhole intercepts "
            "above a reference Cu grade? [Y/N]:",
        )
        settings["reference_grade_analysis_enabled"] = enabled
        if not enabled:
            settings["reference_grade"] = None
            return settings

        config = load_config(request.paths.project_root)
        default_grade = settings.get("reference_grade")
        if default_grade is None:
            default_grade = config.default_reference_grade
        while True:
            reference_grade = prompt_nonnegative_float(
                io,
                "Reference Cu grade (%)",
                float(default_grade),
            )
            if reference_grade > 100.0:
                io.write("The reference Cu grade cannot exceed 100 percent.")
                continue
            settings["reference_grade"] = reference_grade
            break
        io.write()
        io.write("This is a REFERENCE GRADE used only to examine drillhole intercepts.")
        io.write("It is NOT:")
        io.write("- an economic cut-off grade;")
        io.write("- a Mineral Resource boundary;")
        io.write("- an ore/waste definition.")
        return settings

    def _review(self, request: WizardRequest, settings: Mapping[str, Any]) -> None:
        io = request.io
        project = request.project
        io.write()
        io.write("=" * 60)
        io.write("M01 EXECUTION CONFIGURATION")
        io.write("=" * 60)
        io.write()
        io.write("INPUTS")
        io.write("-" * 60)
        if project is None:
            io.write("Exploration data: Not configured")
            io.write("Topography: Not configured")
        else:
            io.write("Exploration data:")
            io.write(project.exploration_data_path)
            io.write("Topography:")
            io.write(project.topography_path)
        io.write()
        io.write("PROJECT")
        io.write("-" * 60)
        if project is None:
            io.write("Project:       Not configured")
            io.write("Dataset:       Not configured")
            io.write("Release:       Not configured")
        else:
            io.write(f"Project:       {project.project_name}")
            io.write(f"Dataset:       {project.dataset_id}")
            io.write(f"Release:       {project.release_id}")
        io.write()
        io.write("ANALYSIS")
        io.write("-" * 60)
        io.write("Primary element:              Cu")
        enabled = bool(settings["reference_grade_analysis_enabled"])
        io.write(
            "Reference-grade analysis:    "
            + ("ENABLED" if enabled else "NOT REQUESTED")
        )
        if enabled:
            io.write(
                "Reference grade:             "
                f"{float(settings['reference_grade']):.2f} % Cu"
            )
        io.write()
        io.write("TOPOGRAPHY QA")
        io.write("-" * 60)
        io.write(
            "OK tolerance:                 "
            f"{float(settings['topography_ok_tolerance_m']):.1f} m"
        )
        io.write(
            "Review tolerance:             "
            f"{float(settings['topography_review_tolerance_m']):.1f} m"
        )
        io.write()
        io.write("OUTPUT")
        io.write("-" * 60)
        if project is None:
            io.write("Not configured")
        else:
            io.write(
                request.paths.output_path(
                    project.project_id,
                    project.dataset_id,
                    project.release_id,
                    "m01",
                )
            )
        io.write()

    def interact(self, request: WizardRequest) -> WizardOutcome:
        defaults = _defaults(request.paths.project_root)
        allowed = set(defaults)
        settings = {
            **defaults,
            **{key: value for key, value in request.settings.items() if key in allowed},
        }
        settings["execution_mode"] = "INTERACTIVE"
        io = request.io
        while True:
            io.write("=" * 60)
            io.write("M01 — VALIDATE, DESURVEY & DRILLHOLE ANALYSIS")
            io.write("=" * 60)
            io.write()
            io.write("[1] Review / change inputs")
            io.write("[2] Configure analysis")
            io.write("[3] Review configuration")
            io.write("[4] Run M01")
            io.write("[5] View last result")
            io.write("[0] Back")
            selection = io.prompt("Select an M01 option:")
            if selection == "0":
                return WizardOutcome(WizardAction.BACK, settings)
            if selection == "1":
                return WizardOutcome(WizardAction.CONFIGURE_DATA, settings)
            if selection == "2":
                settings = self._configure_parameters(request, settings)
                continue
            if selection == "3":
                self._review(request, settings)
                continue
            if selection == "4":
                if request.project is None:
                    io.write("Configure and confirm project data before running M01.")
                    continue
                self._review(request, settings)
                if _yes(io, "Run M01 with this configuration? [Y/N]:"):
                    return WizardOutcome(WizardAction.RUN, settings)
                continue
            if selection == "5":
                if request.last_result is None:
                    io.write("M01 has not been run for the active project.")
                else:
                    self.show_result(request.last_result, request)
                continue
            io.write("Select an M01 menu option.")

    def show_result(self, result: ModuleResult, request: WizardRequest) -> None:
        io = request.io
        metrics = result.metrics
        io.write()
        io.write("=" * 60)
        io.write("M01 — RESULTS")
        io.write("=" * 60)
        io.write()
        io.write(
            f"Validation: {metrics.get('validation_status', result.status.value)}"
        )
        io.write()
        if not bool(metrics.get("reference_grade_analysis_enabled", False)):
            io.write("Reference-grade analysis: NOT REQUESTED")
        else:
            io.write("REFERENCE-GRADE INTERCEPT ANALYSIS")
            io.write("Interpretation: ALONG-HOLE INTERCEPTS")
            io.write("NOT TRUE GEOLOGICAL THICKNESS")
            io.write("This reference grade is NOT an economic cut-off grade.")
        io.write("M01 does NOT calculate Mineral Resources or Mineral Reserves.")
        io.write()
        io.write("[1] Open 3D visualization")
        io.write("[2] View technical module summary")
        io.write("[3] Generate Datamine drillholes (.dm)")
        io.write("[4] Generate Datamine topographic wireframe (PT/TR)")
        io.write("[0] Back to module dashboard")
        while True:
            selection = io.prompt("Select a result option:")
            if not selection:
                continue
            if selection == "0":
                return
            if selection == "1":
                relative = metrics.get("visualization_relative_path")
                if isinstance(relative, str):
                    opener = request.open_web_path or request.open_path
                    opener(request.paths.output_root / relative)
                else:
                    io.write("No 3D visualization is registered for this result.")
                continue
            if selection == "2":
                summary = result.report_payload.get("technical_summary")
                if isinstance(summary, Mapping):
                    io.write()
                    for line in render_technical_summary_text(summary).splitlines():
                        io.write(line)
                    relative = metrics.get("technical_summary_relative_path")
                    if isinstance(relative, str):
                        io.write()
                        io.write("Technical summary artifact:")
                        io.write(request.paths.output_root / relative)
                else:
                    io.write("No technical summary is registered; rerun M01.")
                continue
            if selection == "3":
                project = request.project
                if project is None:
                    io.write("No active project is available for Datamine export.")
                else:
                    try:
                        exported = export_static_drillholes(
                            project.create_context(request.paths, request.settings)
                        )
                    except DatamineExportError as exc:
                        io.write(f"Datamine staging failed: {exc}")
                        continue
                    io.write()
                    io.write("=" * 60)
                    io.write("DATAMINE STATIC DRILLHOLES")
                    io.write("=" * 60)
                    io.write()
                    io.write(f"Native Datamine backend: {exported.backend_status}")
                    if exported.backend_name:
                        io.write(f"Backend: {exported.backend_name}")
                    io.write()
                    if exported.native_created:
                        io.write("Status: SUCCESS")
                        io.write(f"Records: {int(exported.record_count or 0):,}")
                        io.write("Native file:")
                        io.write(exported.native_paths[0])
                    else:
                        io.write("Datamine-ready staging package generated:")
                        io.write(exported.staging_paths[0])
                        io.write(exported.manifest_path)
                        io.write()
                        io.write("No fake .dm file was created.")
                continue
            if selection == "4":
                project = request.project
                if project is None:
                    io.write("No active project is available for Datamine export.")
                else:
                    try:
                        exported = export_topographic_wireframe(
                            project.create_context(request.paths, request.settings)
                        )
                    except DatamineExportError as exc:
                        io.write(f"Datamine staging failed: {exc}")
                        continue
                    io.write()
                    io.write("=" * 60)
                    io.write("DATAMINE TOPOGRAPHIC WIREFRAME")
                    io.write("=" * 60)
                    io.write()
                    io.write(f"Native Datamine backend: {exported.backend_status}")
                    if exported.backend_name:
                        io.write(f"Backend: {exported.backend_name}")
                    io.write()
                    if exported.native_created:
                        io.write("Status:            SUCCESS")
                        io.write("Type:              WIREFRAME / DTM")
                        io.write(f"Points:            {int(exported.point_count or 0):,}")
                        io.write(f"Triangles:         {int(exported.triangle_count or 0):,}")
                        io.write()
                        io.write("Points file:")
                        io.write(exported.native_paths[0])
                        io.write("Triangles file:")
                        io.write(exported.native_paths[1])
                        io.write()
                        io.write("Coordinate system:")
                        io.write("LOCAL_CARTESIAN")
                        io.write("Source:")
                        io.write(project.topography_path)
                    else:
                        io.write("Datamine-ready PT/TR staging package generated:")
                        io.write(exported.staging_paths[0])
                        io.write(exported.staging_paths[1])
                        io.write(exported.manifest_path)
                        io.write()
                        io.write("No fake pt.dm/tr.dm files were created.")
                continue
            io.write("Invalid option. Select 0, 1, 2, 3 or 4.")


def create_wizard() -> M01Wizard:
    return M01Wizard()
