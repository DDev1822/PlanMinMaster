"""Deterministic human rendering of values already calculated by M01."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


SummaryRow = Mapping[str, Any]


def _row(
    category: str,
    indicator: str,
    value: Any,
    unit: str = "",
    decimals: int | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "indicator": indicator,
        "value": value,
        "unit": unit,
        "decimals": decimals,
    }


def build_technical_summary(
    *,
    project_name: str,
    dataset_id: str,
    release_id: str,
    drilling: Mapping[str, Any],
    validation: Mapping[str, Any],
    drillhole_geometry: Mapping[str, Any],
    observed_grade: Mapping[str, Any],
    topography: Mapping[str, Any],
    density: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble a presentation model without performing scientific analysis."""

    finding_counts = validation.get("finding_counts", {})
    if not isinstance(finding_counts, Mapping):
        finding_counts = {}
    consistency = topography.get("consistency_class_counts", {})
    if not isinstance(consistency, Mapping):
        consistency = {}
    density_statistics = density.get("statistics", {})
    if not isinstance(density_statistics, Mapping):
        density_statistics = {}
    residual_statistics = topography.get("residual_statistics_m", {})
    if not isinstance(residual_statistics, Mapping):
        residual_statistics = {}

    rows: list[dict[str, Any]] = [
        _row("PROJECT", "Project", project_name),
        _row("PROJECT", "Dataset", dataset_id),
        _row("PROJECT", "Release", release_id),
        _row("DRILLING", "Drillholes", drilling.get("hole_count"), "DH"),
        _row("DRILLING", "Total drilled", drilling.get("total_drilled_metres"), "m", 2),
        _row("DRILLING", "Survey stations", drillhole_geometry.get("survey_record_count")),
        _row("DRILLING", "Assays", observed_grade.get("source_record_count")),
        _row("DRILLING", "Assayed metres", observed_grade.get("assayed_metres"), "m", 2),
        _row("VALIDATION", "Errors", finding_counts.get("blocking_error_count", 0)),
        _row("VALIDATION", "Warnings", finding_counts.get("warning_count", 0)),
        _row("VALIDATION", "Status", validation.get("verdict")),
        _row("DESURVEY", "Drillholes desurveyed", drillhole_geometry.get("drillholes_desurveyed")),
        _row("DESURVEY", "Trajectory stations", drillhole_geometry.get("trajectory_station_count")),
        _row("DESURVEY", "Assays positioned XYZ", drillhole_geometry.get("assays_positioned_xyz")),
        _row("DESURVEY", "Terminal extensions", drillhole_geometry.get("terminal_extension_count")),
        _row("DESURVEY", "Maximum dogleg", drillhole_geometry.get("maximum_dogleg_deg_per_30m"), "°/30 m", 5),
        _row("OBSERVED Cu", "Minimum", observed_grade.get("minimum"), "%", 5),
        _row("OBSERVED Cu", "Maximum", observed_grade.get("maximum"), "%", 5),
        _row("OBSERVED Cu", "Mean", observed_grade.get("mean"), "%", 5),
        _row("OBSERVED Cu", "Median", observed_grade.get("median"), "%", 5),
        _row("OBSERVED Cu", "Stddev", observed_grade.get("population_stddev"), "%", 5),
        _row("OBSERVED Cu", "CV", observed_grade.get("coefficient_of_variation"), "", 5),
        _row("OBSERVED Cu", "P10", observed_grade.get("p10"), "%", 5),
        _row("OBSERVED Cu", "P50", observed_grade.get("p50"), "%", 5),
        _row("OBSERVED Cu", "P90", observed_grade.get("p90"), "%", 5),
        _row("TOPOGRAPHY", "Source points", topography.get("source_point_count")),
        _row("TOPOGRAPHY", "Collars OK", consistency.get("OK", 0)),
        _row("TOPOGRAPHY", "Warnings", consistency.get("WARNING", 0)),
        _row("TOPOGRAPHY", "Requires review", consistency.get("REQUIRES_REVIEW", 0)),
        _row("TOPOGRAPHY", "Errors", consistency.get("ERROR", 0)),
        _row("TOPOGRAPHY", "Maximum |delta Z|", residual_statistics.get("maximum_absolute"), "m", 5),
        _row("DENSITY", "Samples", density.get("record_count")),
        _row("DENSITY", "Holes represented", density.get("holes_represented")),
        _row("DENSITY", "Mean", density_statistics.get("mean"), "t/m3", 5),
        _row("DENSITY", "Minimum", density_statistics.get("minimum"), "t/m3", 5),
        _row("DENSITY", "Maximum", density_statistics.get("maximum"), "t/m3", 5),
    ]
    if not bool(reference.get("reference_grade_analysis_enabled", False)):
        rows.append(_row("REFERENCE", "Analysis", "NOT REQUESTED"))
    else:
        rows.extend(
            (
                _row("REFERENCE", "Reference grade", reference.get("reference_grade"), "% Cu", 2),
                _row("REFERENCE", "Intercepts", reference.get("intercept_count", 0)),
                _row("REFERENCE", "Along-hole metres", reference.get("intercept_metres", 0.0), "m", 2),
                _row("REFERENCE", "Drillholes represented", reference.get("drillholes_represented", 0)),
                _row("REFERENCE", "Interpretation", "ALONG-HOLE"),
            )
        )
    return {
        "schema_version": "m01.technical_summary.v1",
        "rows": rows,
        "disclaimer": "M01 does not calculate Mineral Resources or Mineral Reserves.",
    }


def _format_value(row: SummaryRow) -> str:
    value = row.get("value")
    if value is None:
        return "N/A"
    decimals = row.get("decimals")
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if isinstance(decimals, int):
            return f"{value:,.{decimals}f}"
        return f"{value:,}"
    return str(value)


def _rows(summary: Mapping[str, Any]) -> Sequence[SummaryRow]:
    rows = summary.get("rows", ())
    if not isinstance(rows, (list, tuple)) or not all(
        isinstance(row, Mapping) for row in rows
    ):
        raise ValueError("technical summary rows are invalid")
    return rows


def render_technical_summary_text(summary: Mapping[str, Any]) -> str:
    """Render only supplied presentation values; no mining functions are called."""

    lines = [
        "=" * 80,
        "M01 — TECHNICAL SUMMARY".center(80),
        "=" * 80,
        "",
        f"{'CATEGORY':<16}{'INDICATOR':<36}{'VALUE':>18}  UNIT",
        "-" * 80,
    ]
    for row in _rows(summary):
        lines.append(
            f"{str(row.get('category', '')):<16.16}"
            f"{str(row.get('indicator', '')):<36.36}"
            f"{_format_value(row):>18}  {row.get('unit', '')}"
        )
    lines.extend(("", str(summary.get("disclaimer", ""))))
    return "\n".join(lines).rstrip() + "\n"


def render_technical_summary_markdown(summary: Mapping[str, Any]) -> str:
    """Render deterministic Markdown from the normalized presentation model."""

    lines = [
        "# M01 — Technical Summary",
        "",
        "| Category | Indicator | Value | Unit |",
        "|---|---|---:|---|",
    ]
    for row in _rows(summary):
        values = (
            str(row.get("category", "")),
            str(row.get("indicator", "")),
            _format_value(row),
            str(row.get("unit", "")),
        )
        escaped = tuple(value.replace("|", "\\|") for value in values)
        lines.append(f"| {escaped[0]} | {escaped[1]} | {escaped[2]} | {escaped[3]} |")
    lines.extend(("", str(summary.get("disclaimer", "")), ""))
    return "\n".join(lines)
