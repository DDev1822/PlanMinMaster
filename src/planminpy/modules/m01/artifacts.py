"""Deterministic persistence of the approved M01 v1.1 artifacts."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from planminpy.core.artifacts import ArtifactWorkspace
from planminpy.core.context import ModuleContext
from planminpy.core.contracts import ArtifactRecord
from planminpy.modules.m01.models import Finding


TRAJECTORY_FIELDS = (
    "project_id",
    "dataset_id",
    "release_id",
    "campaign_id",
    "hole_id",
    "station_index",
    "station_type",
    "md_m",
    "x",
    "y",
    "z",
    "azimuth_deg",
    "dip_deg",
    "interval_md_m",
    "dogleg_deg",
    "ratio_factor",
    "delta_easting_m",
    "delta_northing_m",
    "delta_z_m",
    "cumulative_tvd_m",
    "position_provenance",
    "orientation_provenance",
)

COLLAR_TOPOGRAPHY_FIELDS = (
    "project_id",
    "dataset_id",
    "release_id",
    "campaign_id",
    "hole_id",
    "collar_x",
    "collar_y",
    "collar_z",
    "topography_z",
    "delta_z_m",
    "surface_method",
    "support_status",
    "nearest_support_distance_m",
    "tolerance_warning_m",
    "tolerance_review_m",
    "consistency_class",
    "collar_z_provenance",
    "topography_z_provenance",
    "delta_z_provenance",
    "classification_provenance",
)

ASSAY_STATISTICS_FIELDS = (
    "project_id",
    "dataset_id",
    "release_id",
    "scope_type",
    "scope_id",
    "element",
    "unit",
    "classification",
    "total_count",
    "valid_count",
    "missing_count",
    "zero_count",
    "negative_count",
    "minimum",
    "maximum",
    "mean",
    "median",
    "population_stddev",
    "cv",
    "p05",
    "p10",
    "p25",
    "p50",
    "p75",
    "p90",
    "p95",
    "p99",
    "assay_metres",
    "q3_plus_3iqr",
    "q3_plus_3iqr_count",
    "statistics_provenance",
)

ASSAY_XYZ_FIELDS = (
    "sample_id", "project_id", "dataset_id", "release_id", "campaign_id", "hole_id",
    "from_m", "to_m", "length_m", "mid_m",
    "x_from", "y_from", "z_from", "x_mid", "y_mid", "z_mid", "x_to", "y_to", "z_to",
    "cu_pct", "mo_pct", "au_gt",
)

GRADE_DISTRIBUTION_FIELDS = (
    "project_id", "dataset_id", "release_id", "variable", "unit",
    "grade_from", "grade_to", "upper_bound_inclusive", "assay_count",
    "assayed_metres", "percentage_of_assayed_metres", "length_weighted_grade",
)

REFERENCE_GRADE_INTERCEPT_FIELDS = (
    "project_id", "dataset_id", "release_id", "campaign_id", "hole_id",
    "from_m", "to_m", "intercept_length_m", "x_mid", "y_mid", "z_mid",
    "length_weighted_grade", "reference_grade", "variable", "unit", "sample_count",
    "interpretation", "thickness_semantic",
)

TOPOGRAPHY_TIN_VERTEX_FIELDS = (
    "vertex_index", "source_pid", "x", "y", "z",
)

TOPOGRAPHY_TIN_TRIANGLE_FIELDS = (
    "triangle_index", "vertex_index_1", "vertex_index_2", "vertex_index_3",
)


def write_m01_run_config(
    context: ModuleContext,
    *,
    module_version: str,
    primary_element: str,
    reference_grade_analysis_enabled: bool,
    reference_grade: float | None,
    ok_tolerance_m: float,
    review_tolerance_m: float,
) -> ArtifactRecord:
    """Persist the explicit interactive selections through the safe workspace."""

    workspace = ArtifactWorkspace(context, "m01")
    payload = {
        "module_id": "m01",
        "module_version": module_version,
        "project_id": context.project_id,
        "dataset_id": context.dataset_id,
        "release_id": context.release_id,
        "inputs": {
            "exploration_data_path": str(context.dataset_path),
            "topography_path": str(context.topography_path),
        },
        "analysis": {
            "primary_element": primary_element,
            "reference_grade_analysis_enabled": reference_grade_analysis_enabled,
            "reference_grade": reference_grade,
        },
        "topography_validation": {
            "ok_tolerance_m": ok_tolerance_m,
            "review_tolerance_m": review_tolerance_m,
        },
    }
    path = workspace.write_json("m01_run_config.json", payload)
    return workspace.record(
        path,
        artifact_id="m01-run-config",
        artifact_type="application/json",
        description="Auditable M01 interactive inputs and analytical selections.",
        schema_version="m01.run_config.v1.1",
        record_count=None,
    )


def _csv_rows(
    rows: Iterable[Mapping[str, Any]],
    fields: Sequence[str],
) -> Iterable[dict[str, Any]]:
    """Select the frozen schema and serialize nulls without mutating numbers."""

    return (
        {field: "" if row.get(field) is None else row.get(field) for field in fields}
        for row in rows
    )


def write_m01_artifacts(
    context: ModuleContext,
    *,
    dataset_summary: Mapping[str, Any],
    findings: list[Finding],
    readiness: Mapping[str, Any],
    source_hashes: Mapping[str, str],
    trajectory_rows: list[Mapping[str, Any]],
    collar_topography_rows: list[Mapping[str, Any]],
    assay_statistics_rows: list[Mapping[str, Any]],
    assay_xyz_rows: list[Mapping[str, Any]],
    grade_distribution_rows: list[Mapping[str, Any]],
    reference_grade_intercept_rows: list[Mapping[str, Any]] | None,
    exploration_3d_html: str,
    technical_summary_markdown: str | None = None,
    topography_tin_vertex_rows: Iterable[Mapping[str, Any]] | None = None,
    topography_tin_triangle_rows: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[ArtifactRecord, ...]:
    """Atomically replace the approved artifacts inside the M01 workspace."""

    workspace = ArtifactWorkspace(context, "m01")
    records: list[ArtifactRecord] = []

    summary_payload = {
        "schema_version": "m01.dataset_summary.v2",
        "project_id": context.project_id,
        "dataset_id": context.dataset_id,
        "release_id": context.release_id,
        "generated_at": None,
        **dict(dataset_summary),
        "source_sha256": dict(sorted(source_hashes.items())),
    }
    summary_path = workspace.write_json("dataset_summary.json", summary_payload)
    records.append(
        workspace.record(
            summary_path,
            artifact_id="m01-dataset-summary",
            artifact_type="application/json",
            description="Deterministic M01 dataset and calculated analytical summaries.",
            schema_version="m01.dataset_summary.v2",
            record_count=None,
        )
    )

    ordered_findings = sorted(
        (item.to_dict() for item in findings),
        key=lambda item: (
            item["rule_id"],
            item["table"] or "",
            item["hole_id"] or "",
            item["row_number"] or 0,
            item["finding_id"],
        ),
    )
    validation_payload = {
        "schema_version": "m01.validation_results.v1",
        "project_id": context.project_id,
        "dataset_id": context.dataset_id,
        "release_id": context.release_id,
        "readiness": dict(readiness),
        "findings": ordered_findings,
        "source_sha256": dict(sorted(source_hashes.items())),
    }
    validation_path = workspace.write_json(
        "validation_results.json", validation_payload
    )
    records.append(
        workspace.record(
            validation_path,
            artifact_id="m01-validation-results",
            artifact_type="application/json",
            description="Structured M01 findings and readiness verdict.",
            schema_version="m01.validation_results.v1",
            record_count=len(ordered_findings),
        )
    )

    trajectory_path, trajectory_count = workspace.write_csv(
        "drillhole_trajectory.csv",
        TRAJECTORY_FIELDS,
        _csv_rows(trajectory_rows, TRAJECTORY_FIELDS),
    )
    records.append(
        workspace.record(
            trajectory_path,
            artifact_id="m01-drillhole-trajectory",
            artifact_type="text/csv",
            description="Minimum Curvature drillhole stations with provenance.",
            schema_version="m01.drillhole_trajectory.v1",
            record_count=trajectory_count,
        )
    )

    topography_path, topography_count = workspace.write_csv(
        "collar_topography_check.csv",
        COLLAR_TOPOGRAPHY_FIELDS,
        _csv_rows(collar_topography_rows, COLLAR_TOPOGRAPHY_FIELDS),
    )
    records.append(
        workspace.record(
            topography_path,
            artifact_id="m01-collar-topography-check",
            artifact_type="text/csv",
            description="Collar/TIN consistency under explicit educational tolerances.",
            schema_version="m01.collar_topography_check.v1",
            record_count=topography_count,
        )
    )

    assay_path, assay_count = workspace.write_csv(
        "assay_statistics.csv",
        ASSAY_STATISTICS_FIELDS,
        _csv_rows(assay_statistics_rows, ASSAY_STATISTICS_FIELDS),
    )
    records.append(
        workspace.record(
            assay_path,
            artifact_id="m01-assay-statistics",
            artifact_type="text/csv",
            description="Uncomposited raw-interval assay statistics by scope.",
            schema_version="m01.assay_statistics.v1",
            record_count=assay_count,
        )
    )

    assay_xyz_path, assay_xyz_count = workspace.write_csv(
        "assay_xyz.csv",
        ASSAY_XYZ_FIELDS,
        _csv_rows(assay_xyz_rows, ASSAY_XYZ_FIELDS),
    )
    records.append(
        workspace.record(
            assay_xyz_path,
            artifact_id="m01-assay-xyz",
            artifact_type="text/csv",
            description="Original assays positioned at FROM, MID and TO on continuous trajectories.",
            schema_version="m01.assay_xyz.v1",
            record_count=assay_xyz_count,
        )
    )

    distribution_path, distribution_count = workspace.write_csv(
        "grade_distribution.csv",
        GRADE_DISTRIBUTION_FIELDS,
        _csv_rows(grade_distribution_rows, GRADE_DISTRIBUTION_FIELDS),
    )
    records.append(
        workspace.record(
            distribution_path,
            artifact_id="m01-grade-distribution",
            artifact_type="text/csv",
            description="Observed Cu grade distribution across all valid assay intervals.",
            schema_version="m01.grade_distribution.v1",
            record_count=distribution_count,
        )
    )

    if reference_grade_intercept_rows is not None:
        intercept_path, intercept_count = workspace.write_csv(
            "reference_grade_intercepts.csv",
            REFERENCE_GRADE_INTERCEPT_FIELDS,
            _csv_rows(
                reference_grade_intercept_rows,
                REFERENCE_GRADE_INTERCEPT_FIELDS,
            ),
        )
        records.append(
            workspace.record(
                intercept_path,
                artifact_id="m01-reference-grade-intercepts",
                artifact_type="text/csv",
                description=(
                    "Optional descriptive along-hole intervals meeting the selected "
                    "reference grade; not a cut-off, domain, or resource classification."
                ),
                schema_version="m01.reference_grade_intercepts.v1",
                record_count=intercept_count,
            )
        )

    visualization_path = workspace.write_text("exploration_3d.html", exploration_3d_html)
    records.append(
        workspace.record(
            visualization_path,
            artifact_id="m01-exploration-3d",
            artifact_type="text/html",
            description=(
                "Offline 3D view of decimated topography, drillholes, all assays, "
                "and optional reference-grade intervals."
            ),
            schema_version="m01.exploration_3d.v1.1",
            record_count=None,
        )
    )
    if technical_summary_markdown is not None:
        technical_summary_path = workspace.write_text(
            "m01_technical_summary.md", technical_summary_markdown
        )
        records.append(
            workspace.record(
                technical_summary_path,
                artifact_id="m01-technical-summary",
                artifact_type="text/markdown",
                description="Deterministic human-readable M01 technical summary.",
                schema_version="m01.technical_summary.v1",
                record_count=None,
            )
        )

    if topography_tin_vertex_rows is not None:
        vertices_path, vertices_count = workspace.write_csv(
            "topography_tin_vertices.csv",
            TOPOGRAPHY_TIN_VERTEX_FIELDS,
            _csv_rows(topography_tin_vertex_rows, TOPOGRAPHY_TIN_VERTEX_FIELDS),
        )
        records.append(
            workspace.record(
                vertices_path,
                artifact_id="m01-topography-tin-vertices",
                artifact_type="text/csv",
                description="Full-resolution vertices of the validated scientific M01 TIN.",
                schema_version="m01.topography_tin_vertices.v1",
                record_count=vertices_count,
            )
        )
    if topography_tin_triangle_rows is not None:
        triangles_path, triangles_count = workspace.write_csv(
            "topography_tin_triangles.csv",
            TOPOGRAPHY_TIN_TRIANGLE_FIELDS,
            _csv_rows(topography_tin_triangle_rows, TOPOGRAPHY_TIN_TRIANGLE_FIELDS),
        )
        records.append(
            workspace.record(
                triangles_path,
                artifact_id="m01-topography-tin-triangles",
                artifact_type="text/csv",
                description="Full-resolution connectivity of the validated scientific M01 TIN.",
                schema_version="m01.topography_tin_triangles.v1",
                record_count=triangles_count,
            )
        )
    # Migration cleanup is restricted to reproducible M01 outputs.  These files
    # belonged to the superseded v1.0 contract and must never remain authoritative.
    stale_names = ["preliminary_inventory.csv", "mineralized_intercepts.csv"]
    if reference_grade_intercept_rows is None:
        stale_names.append("reference_grade_intercepts.csv")
    for stale_name in stale_names:
        workspace.resolve(stale_name).unlink(missing_ok=True)

    return tuple(records)
