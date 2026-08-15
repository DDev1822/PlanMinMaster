from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from interactive_test_support import (
    make_interactive_project,
    result_for,
    terminal_with_inputs,
)
from planminpy.interactive.contracts import WizardAction, WizardRequest
from planminpy.modules.m01.artifacts import write_m01_run_config
from planminpy.modules.m01.config import M01ConfigError, load_config
from planminpy.modules.m01.settings import M01RunSettings
from planminpy.modules.m01.wizard import (
    M01Wizard,
    prompt_nonnegative_float,
    prompt_topography_tolerances,
)


class M01InteractiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths, self.active = make_interactive_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _request(self, values, *, result=None, settings=None):
        io_adapter, output = terminal_with_inputs(values)
        request = WizardRequest(
            paths=self.paths,
            project=self.active,
            settings={} if settings is None else settings,
            last_result=result,
            io=io_adapter,
            open_path=lambda _path: True,
        )
        return request, output

    def test_blank_numeric_parameter_accepts_default(self) -> None:
        io_adapter, _ = terminal_with_inputs([""])
        self.assertEqual(prompt_nonnegative_float(io_adapter, "Value", 0.2), 0.2)

    def test_invalid_and_negative_reference_grades_are_rejected_by_prompt(self) -> None:
        io_adapter, output = terminal_with_inputs(["abc", "-1", "0.35"])
        value = prompt_nonnegative_float(io_adapter, "Reference grade", 0.2)
        self.assertEqual(value, 0.35)
        rendered = "\n".join(output)
        self.assertIn("numeric", rendered)
        self.assertIn("cannot be negative", rendered)

    def test_topography_tolerance_ordering_is_validated(self) -> None:
        io_adapter, output = terminal_with_inputs(["5", "2", "2", "5"])
        self.assertEqual(prompt_topography_tolerances(io_adapter, 2.0, 5.0), (2.0, 5.0))
        self.assertIn("0 <= OK", "\n".join(output))

    def test_interactive_settings_override_config_defaults(self) -> None:
        context = self.active.create_context(
            self.paths,
            {
                "execution_mode": "INTERACTIVE",
                "primary_element": "cu_pct",
                "reference_grade_analysis_enabled": True,
                "reference_grade": 0.55,
                "topography_ok_tolerance_m": 1.5,
                "topography_review_tolerance_m": 4.5,
            },
        )
        settings = M01RunSettings.resolve(context, load_config(self.root))
        self.assertTrue(settings.reference_grade_analysis_enabled)
        self.assertEqual(settings.reference_grade, 0.55)
        self.assertEqual((settings.ok_tolerance_m, settings.review_tolerance_m), (1.5, 4.5))

    def test_direct_context_defaults_reference_analysis_to_disabled(self) -> None:
        context = self.active.create_context(self.paths, {})
        settings = M01RunSettings.resolve(context, load_config(self.root))
        self.assertFalse(settings.reference_grade_analysis_enabled)
        self.assertIsNone(settings.reference_grade)
        self.assertFalse(settings.interactive)

    def test_negative_reference_grade_is_rejected_by_settings_contract(self) -> None:
        context = self.active.create_context(
            self.paths,
            {"reference_grade_analysis_enabled": True, "reference_grade": -0.01},
        )
        with self.assertRaises(M01ConfigError):
            M01RunSettings.resolve(context, load_config(self.root))

    def test_disabled_reference_ignores_stale_reference_value(self) -> None:
        context = self.active.create_context(
            self.paths,
            {"reference_grade_analysis_enabled": False, "reference_grade": 0.8},
        )
        settings = M01RunSettings.resolve(context, load_config(self.root))
        self.assertIsNone(settings.reference_grade)

    def test_m01_run_config_uses_only_v11_analysis_fields(self) -> None:
        context = self.active.create_context(self.paths, {"execution_mode": "INTERACTIVE"})
        record = write_m01_run_config(
            context,
            module_version="1.1.0",
            primary_element="cu_pct",
            reference_grade_analysis_enabled=True,
            reference_grade=0.35,
            ok_tolerance_m=2.0,
            review_tolerance_m=5.0,
        )
        path = context.output_root / record.relative_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["analysis"],
            {
                "primary_element": "cu_pct",
                "reference_grade_analysis_enabled": True,
                "reference_grade": 0.35,
            },
        )
        self.assertNotIn("density_method", json.dumps(payload))
        self.assertNotIn("preliminary_analysis_method", json.dumps(payload))

    def test_m01_run_config_stays_inside_output_workspace(self) -> None:
        context = self.active.create_context(self.paths, {})
        record = write_m01_run_config(
            context,
            module_version="1.1.0",
            primary_element="cu_pct",
            reference_grade_analysis_enabled=False,
            reference_grade=None,
            ok_tolerance_m=2.0,
            review_tolerance_m=5.0,
        )
        path = context.output_root / record.relative_path
        self.assertTrue(path.is_relative_to(context.output_root))
        self.assertFalse(path.is_relative_to(context.data_root))
        self.assertEqual(len(record.sha256 or ""), 64)

    def test_m01_wizard_can_return_without_execution(self) -> None:
        request, _ = self._request(["0"])
        self.assertIs(M01Wizard().interact(request).action, WizardAction.BACK)

    def test_blank_optional_answer_means_not_requested(self) -> None:
        request, _ = self._request(["2", "", "", "", "", "0"])
        outcome = M01Wizard().interact(request)
        self.assertFalse(outcome.settings["reference_grade_analysis_enabled"])
        self.assertIsNone(outcome.settings["reference_grade"])

    def test_wizard_returns_enabled_reference_configuration(self) -> None:
        request, output = self._request(["2", "1", "", "", "y", "0.35", "0"])
        outcome = M01Wizard().interact(request)
        self.assertTrue(outcome.settings["reference_grade_analysis_enabled"])
        self.assertEqual(outcome.settings["reference_grade"], 0.35)
        rendered = "\n".join(output)
        self.assertIn("It is NOT:", rendered)
        self.assertIn("- an economic cut-off grade", rendered)
        self.assertIn("NOT SUITABLE", rendered)

    def test_obsolete_incoming_settings_are_not_propagated(self) -> None:
        request, _ = self._request(
            ["0"],
            settings={
                "preliminary_analysis_method": "DELAUNAY_NODAL",
                "density_method": "GLOBAL_OBSERVED_MEAN",
                "mineralization_threshold": 0.2,
            },
        )
        outcome = M01Wizard().interact(request)
        self.assertNotIn("preliminary_analysis_method", outcome.settings)
        self.assertNotIn("density_method", outcome.settings)
        self.assertNotIn("mineralization_threshold", outcome.settings)

    def test_detected_constant_zero_elements_are_explained_honestly(self) -> None:
        request, output = self._request(["2", "2", "1", "", "", "", "0"])
        M01Wizard().interact(request)
        rendered = "\n".join(output)
        self.assertIn("Mo (%)", rendered)
        self.assertIn("CONSTANT_ZERO", rendered)
        self.assertIn("not suitable", rendered.lower())

    def test_no_reference_result_screen_has_no_tonnage(self) -> None:
        result = result_for(
            metrics={
                "validation_status": "PASS_WITH_WARNINGS",
                "hole_count": 3,
                "total_drilled_m": 100.0,
                "assays_positioned_count": 4,
                "observed_grade_minimum": 0.0,
                "observed_grade_maximum": 0.8,
                "observed_grade_mean": 0.2,
                "observed_grade_median": 0.1,
                "reference_grade_analysis_enabled": False,
                "visualization_relative_path": "project/DS00/EXP03/m01/exploration_3d.html",
            }
        )
        request, output = self._request(["0"], result=result)
        M01Wizard().show_result(result, request)
        rendered = "\n".join(output)
        self.assertIn("NOT REQUESTED", rendered)
        self.assertIn("does NOT calculate Mineral Resources", rendered)
        self.assertNotIn("tonnes", rendered.lower())
        self.assertNotIn("contained Cu", rendered)

    def test_reference_result_screen_uses_along_hole_language(self) -> None:
        result = result_for(
            metrics={
                "validation_status": "PASS_WITH_WARNINGS",
                "hole_count": 3,
                "total_drilled_m": 100.0,
                "assays_positioned_count": 4,
                "observed_grade_minimum": 0.0,
                "observed_grade_maximum": 0.8,
                "observed_grade_mean": 0.2,
                "observed_grade_median": 0.1,
                "reference_grade_analysis_enabled": True,
                "reference_grade": 0.2,
                "reference_grade_intercept_count": 2,
                "reference_grade_intercept_metres": 20.0,
                "reference_grade_drillhole_count": 2,
                "visualization_relative_path": "project/DS00/EXP03/m01/exploration_3d.html",
            }
        )
        request, output = self._request(["0"], result=result)
        M01Wizard().show_result(result, request)
        rendered = "\n".join(output)
        self.assertIn("REFERENCE-GRADE INTERCEPT ANALYSIS", rendered)
        self.assertIn("NOT TRUE GEOLOGICAL THICKNESS", rendered)
        self.assertIn("NOT an economic cut-off grade", rendered)

    def test_result_menu_reprompts_blank_and_rejects_invalid_option(self) -> None:
        result = result_for(metrics={"validation_status": "PASS"})
        request, output = self._request(["", "x", "0"], result=result)
        M01Wizard().show_result(result, request)
        rendered = "\n".join(output)
        self.assertIn("[4] Generate Datamine topographic wireframe", rendered)
        self.assertIn("Invalid option. Select 0, 1, 2, 3 or 4.", rendered)

    def test_root_entrypoint_contains_no_module_specific_branch(self) -> None:
        root_main = Path(__file__).resolve().parents[1] / "main.py"
        text = root_main.read_text(encoding="utf-8").lower()
        self.assertNotIn("m01", text)
        self.assertNotIn("selection", text)


if __name__ == "__main__":
    unittest.main()
