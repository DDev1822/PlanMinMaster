from __future__ import annotations

import unittest
from datetime import datetime, timezone

from planminpy.core.contracts import ModuleResult, ModuleStatus
from planminpy.modules.m01.models import Finding, ReadinessVerdict, Severity, readiness_verdict
from planminpy.reporting.contracts import ReportState
from planminpy.reporting.renderers.markdown_renderer import render_markdown


class M01ReportingReadinessTests(unittest.TestCase):
    def test_readiness_mapping_all_four_verdicts(self) -> None:
        warning = Finding.create("W", Severity.WARNING, "warning")
        review = Finding.create("R", Severity.WARNING, "review", requires_review=True)
        blocker = Finding.create("E", Severity.ERROR, "error", blocking=True)
        self.assertIs(readiness_verdict([]), ReadinessVerdict.PASS)
        self.assertIs(readiness_verdict([warning]), ReadinessVerdict.PASS_WITH_WARNINGS)
        self.assertIs(readiness_verdict([review]), ReadinessVerdict.REQUIRES_REVIEW)
        self.assertIs(readiness_verdict([blocker]), ReadinessVerdict.FAILED)

    def test_markdown_renders_structured_report_payload(self) -> None:
        now = datetime.now(timezone.utc)
        result = ModuleResult(
            module_id="m01",
            module_version="0.9.0",
            status=ModuleStatus.COMPLETED,
            project_id="project",
            dataset_id="DS00",
            release_id="EXP03",
            started_at=now,
            completed_at=now,
            summary="done",
            report_payload={
                "schema_version": "m01.report.v1",
                "overview": {"hole_count": 2},
                "readiness": {"verdict": "PASS_WITH_WARNINGS"},
            },
        )
        state = ReportState.from_result(result, now)
        markdown = render_markdown(state)
        self.assertIn("### Structured Report Payload", markdown)
        self.assertIn("#### Overview", markdown)
        self.assertIn("PASS_WITH_WARNINGS", markdown)


if __name__ == "__main__":
    unittest.main()
