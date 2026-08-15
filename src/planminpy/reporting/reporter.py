"""Cumulative report upsert and safe persistence under outputs/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from planminpy.core.contracts import ModuleResult, PlanMinPyError
from planminpy.core.paths import ProjectPaths
from planminpy.reporting.contracts import ReportContractError, ReportState
from planminpy.reporting.renderers.json_renderer import render_json
from planminpy.reporting.renderers.markdown_renderer import render_markdown


class ReportingError(PlanMinPyError):
    """Raised for controlled report loading or persistence failures."""


@dataclass(frozen=True)
class ReporterOutput:
    state_path: Path
    markdown_path: Path
    state: ReportState


class Reporter:
    def __init__(self, paths: ProjectPaths) -> None:
        self._paths = paths

    def update(self, result: ModuleResult) -> ReporterOutput:
        report_parts = (
            result.project_id,
            result.dataset_id,
            result.release_id,
            "report",
        )
        state_parts = report_parts + ("report_state.json",)
        markdown_parts = report_parts + ("report.md",)
        state_path = self._paths.output_path(*state_parts)
        markdown_path = self._paths.output_path(*markdown_parts)

        existing = self._load_state(state_path) if state_path.exists() else None
        timestamp = datetime.now(timezone.utc)
        try:
            state = (
                ReportState.from_result(result, timestamp)
                if existing is None
                else existing.upsert(result, timestamp)
            )
            json_content = render_json(state)
            markdown_content = render_markdown(state)
        except (ReportContractError, TypeError, ValueError) as exc:
            raise ReportingError("could not build normalized report state") from exc

        written_state_path = self._paths.atomic_write_text(state_parts, json_content)
        written_markdown_path = self._paths.atomic_write_text(
            markdown_parts, markdown_content
        )
        return ReporterOutput(
            state_path=written_state_path,
            markdown_path=written_markdown_path,
            state=state,
        )

    @staticmethod
    def _load_state(state_path: Path) -> ReportState:
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("report state must be a JSON object")
            return ReportState.from_dict(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, ReportContractError, TypeError) as exc:
            raise ReportingError(f"existing report state is invalid: {state_path}") from exc
