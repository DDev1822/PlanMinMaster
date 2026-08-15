"""Human-readable Markdown rendering of the cumulative report state."""

from __future__ import annotations

import json
from typing import Any, Iterable

from planminpy.reporting.contracts import ReportState


def _text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return str(value)


def _cell(value: Any) -> str:
    return _text(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _bullet_block(values: Iterable[str]) -> list[str]:
    items = list(values)
    return [f"- {item}" for item in items] if items else ["_None._"]


def _title(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _render_payload_value(name: str, value: Any, level: int) -> list[str]:
    """Render arbitrary normalized payload data without domain calculations."""

    heading = "#" * min(level, 6)
    lines = [f"{heading} {_title(name)}", ""]
    if isinstance(value, dict):
        scalar_items = [(key, item) for key, item in value.items() if _is_scalar(item)]
        nested_items = [(key, item) for key, item in value.items() if not _is_scalar(item)]
        if scalar_items:
            lines.extend(["| Field | Value |", "|---|---|"])
            for key, item in scalar_items:
                lines.append(f"| {_cell(_title(key))} | {_cell(item)} |")
            lines.append("")
        if not value:
            lines.extend(["_None._", ""])
        for key, item in nested_items:
            lines.extend(_render_payload_value(key, item, level + 1))
        return lines
    if isinstance(value, (list, tuple)):
        if not value:
            lines.extend(["_None._", ""])
        elif all(_is_scalar(item) for item in value):
            lines.extend(f"- {_text(item)}" for item in value)
            lines.append("")
        elif all(isinstance(item, dict) for item in value):
            columns = sorted({key for item in value for key in item})
            if columns and all(_is_scalar(item.get(key)) for item in value for key in columns):
                lines.append("| " + " | ".join(_cell(_title(key)) for key in columns) + " |")
                lines.append("|" + "---|" * len(columns))
                for item in value:
                    lines.append(
                        "| " + " | ".join(_cell(item.get(key)) for key in columns) + " |"
                    )
                lines.append("")
            else:
                for index, item in enumerate(value, start=1):
                    lines.extend(_render_payload_value(f"item {index}", item, level + 1))
        else:
            lines.extend(f"- {_text(item)}" for item in value)
            lines.append("")
        return lines
    lines.extend([_text(value), ""])
    return lines


def render_markdown(state: ReportState) -> str:
    lines = [
        "# PlanMinPy Cumulative Report",
        "",
        f"- Project: `{state.project_id}`",
        f"- Dataset: `{state.dataset_id}`",
        f"- Release: `{state.release_id}`",
        f"- Created: `{state.created_at.isoformat()}`",
        f"- Updated: `{state.updated_at.isoformat()}`",
        "",
    ]

    for section in state.sections:
        result = section.result
        lines.extend(
            [
                f"## Module `{result.module_id}`",
                "",
                f"- Version: `{result.module_version}`",
                f"- Status: `{result.status.value}`",
                f"- Started: `{result.started_at.isoformat()}`",
                f"- Completed: `{result.completed_at.isoformat()}`",
                f"- Section updated: `{section.updated_at.isoformat()}`",
                "",
                "### Summary",
                "",
                result.summary or "_None._",
                "",
                "### Metrics",
                "",
            ]
        )
        if result.metrics:
            lines.extend(["| Name | Value |", "|---|---|"])
            for name in sorted(result.metrics):
                lines.append(f"| {_cell(name)} | {_cell(result.metrics[name])} |")
        else:
            lines.append("_None._")

        lines.extend(["", "### Structured Report Payload", ""])
        if result.report_payload:
            for name, value in result.report_payload.items():
                lines.extend(_render_payload_value(name, value, 4))
        else:
            lines.append("_None._")

        lines.extend(["", "### Provenance", ""])
        if result.provenance:
            lines.extend(
                [
                    "| Kind | Name | Value | Unit | Source | Method | Rationale |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            for record in result.provenance:
                lines.append(
                    "| "
                    + " | ".join(
                        _cell(value)
                        for value in (
                            record.kind.value,
                            record.name,
                            record.value,
                            record.unit,
                            record.source,
                            record.method,
                            record.rationale,
                        )
                    )
                    + " |"
                )
        else:
            lines.append("_None._")

        lines.extend(["", "### Warnings", ""])
        lines.extend(_bullet_block(result.warnings))
        lines.extend(["", "### Errors", ""])
        lines.extend(_bullet_block(result.errors))
        lines.extend(["", "### Artifacts", ""])
        if result.artifacts:
            lines.extend(
                [
                    "| ID | Type | Schema | Path | SHA-256 | Bytes | Records | Description |",
                    "|---|---|---|---|---|---|---|---|",
                ]
            )
            for artifact in result.artifacts:
                lines.append(
                    "| "
                    + " | ".join(
                        _cell(value)
                        for value in (
                            artifact.artifact_id,
                            artifact.artifact_type,
                            artifact.schema_version,
                            artifact.relative_path,
                            artifact.sha256,
                            artifact.byte_size,
                            artifact.record_count,
                            artifact.description,
                        )
                    )
                    + " |"
                )
        else:
            lines.append("_None._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
