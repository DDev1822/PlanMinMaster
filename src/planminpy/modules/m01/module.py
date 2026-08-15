"""M01 v1.1 validation, desurvey, and observed drillhole analysis."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping

from planminpy.core.context import ModuleContext
from planminpy.core.contracts import (
    ModuleResult,
    ModuleStatus,
    ProvenanceKind,
    ProvenanceRecord,
)
from planminpy.modules.m01.artifacts import write_m01_artifacts, write_m01_run_config
from planminpy.modules.m01.config import load_config
from planminpy.modules.m01.geometry import desurvey_hole
from planminpy.modules.m01.inventory import (
    build_reference_grade_intercepts,
    position_assays_xyz,
)
from planminpy.modules.m01.loaders import load_release
from planminpy.modules.m01.models import (
    Finding,
    ReadinessVerdict,
    Severity,
    finding_counts,
    readiness_verdict,
)
from planminpy.modules.m01.statistics import (
    assay_statistics_rows,
    grade_distribution_rows,
    numeric_statistics,
    observed_grade_distribution,
    values_for,
)
from planminpy.modules.m01.technical_summary import (
    build_technical_summary,
    render_technical_summary_markdown,
)
from planminpy.modules.m01.settings import M01RunSettings
from planminpy.modules.m01.topography import (
    TopographySurface,
    classify_topography_consistency,
)
from planminpy.modules.m01.validation import (
    validate_assay_values,
    validate_collars,
    validate_density_values,
    validate_intervals,
    validate_source_hashes,
    validate_surveys,
)
from planminpy.modules.m01.visualization import build_exploration_3d_html

MODULE_ID = "m01"
MODULE_VERSION = "1.1.0"


def _stats(values: list[float]) -> dict[str, float | int | None]:
    return numeric_statistics([value for value in values if math.isfinite(value)])


def _status(verdict: ReadinessVerdict) -> ModuleStatus:
    return {
        ReadinessVerdict.PASS: ModuleStatus.COMPLETED,
        ReadinessVerdict.PASS_WITH_WARNINGS: ModuleStatus.COMPLETED,
        ReadinessVerdict.REQUIRES_REVIEW: ModuleStatus.REQUIRES_REVIEW,
        ReadinessVerdict.FAILED: ModuleStatus.FAILED,
    }[verdict]


def _identity(context: ModuleContext) -> dict[str, str]:
    return {
        "project_id": context.project_id,
        "dataset_id": context.dataset_id,
        "release_id": context.release_id,
    }


def _survey_summary(
    survey_rows: tuple[dict[str, str], ...],
    collars: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    grouped: defaultdict[str, list[float]] = defaultdict(list)
    for row in survey_rows:
        try:
            grouped[row["hole_id"]].append(float(row["depth_m"]))
        except ValueError:
            continue
    spacings: list[float] = []
    terminal_gaps: list[float] = []
    for hole_id, depths in grouped.items():
        ordered = sorted(depths)
        spacings.extend(
            current - previous for previous, current in zip(ordered, ordered[1:])
        )
        collar = collars.get(hole_id)
        if collar is not None and ordered:
            terminal_gaps.append(float(collar["final_depth_m"]) - ordered[-1])
    return {
        "survey_record_count": len(survey_rows),
        "holes_with_surveys": len(grouped),
        "holes_without_surveys": len(set(collars) - set(grouped)),
        "station_spacing_m": _stats(spacings),
        "terminal_gap_m": _stats(terminal_gaps),
    }


def _interval_coverage(
    rows: tuple[dict[str, str], ...],
    *,
    code_field: str | None = None,
) -> dict[str, Any]:
    metres = sum(values_for(rows, "length_m"))
    result: dict[str, Any] = {
        "record_count": len(rows),
        "holes_represented": len({row["hole_id"] for row in rows}),
        "sampled_metres": metres,
    }
    if code_field is not None:
        counts = Counter(row[code_field] for row in rows)
        code_metres: defaultdict[str, float] = defaultdict(float)
        for row in rows:
            try:
                code_metres[row[code_field]] += float(row["length_m"])
            except ValueError:
                continue
        result["literal_codes"] = {
            code: {"record_count": counts[code], "metres": code_metres[code]}
            for code in sorted(counts)
        }
    return result


def run(context: ModuleContext) -> ModuleResult:
    """Execute M01 independently without calculating a resource inventory."""

    started_at = datetime.now(timezone.utc)
    config = load_config(context.project_root)
    run_settings = M01RunSettings.resolve(context, config)
    release = load_release(context)
    tables = release.tables
    identity = _identity(context)
    collars = {row["hole_id"]: row for row in tables["collar.csv"].rows}

    findings: list[Finding] = []
    findings.extend(validate_source_hashes(context, release))
    findings.extend(validate_collars(tables["collar.csv"], context, config))
    findings.extend(validate_surveys(tables["survey.csv"], collars, context, config))
    for name, primary_id, gap_kind in (
        ("assay.csv", "sample_id", "UNSAMPLED_GAP"),
        ("lithology.csv", None, "GEOLOGICAL_GAP"),
        ("alteration.csv", None, "ALTERATION_GAP"),
        ("density.csv", "density_sample_id", "DENSITY_GAP"),
    ):
        findings.extend(
            validate_intervals(
                tables[name],
                collars,
                context,
                config,
                primary_id=primary_id,
                gap_kind=gap_kind,
            )
        )

    assay_rows = assay_statistics_rows(tables["assay.csv"].rows, **identity)
    overall_classifications = {
        row["element"]: row["classification"]
        for row in assay_rows
        if row["scope_type"] == "ALL"
    }
    findings.extend(validate_assay_values(tables["assay.csv"], overall_classifications))
    findings.extend(validate_density_values(tables["density.csv"], config))

    survey_groups: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in tables["survey.csv"].rows:
        survey_groups[row["hole_id"]].append(row)
    trajectories: dict[str, list[dict[str, object]]] = {}
    trajectory_rows: list[dict[str, Any]] = []
    for hole_id in sorted(collars):
        collar = collars[hole_id]
        if not survey_groups.get(hole_id):
            continue
        try:
            stations = desurvey_hole(
                collar,
                survey_groups[hole_id],
                zero_dogleg_epsilon_rad=config.dogleg_epsilon_rad,
            )
        except (KeyError, ValueError):
            continue
        trajectories[hole_id] = stations
        for station in stations:
            trajectory_rows.append(
                {
                    **identity,
                    "campaign_id": collar["campaign_id"],
                    "hole_id": hole_id,
                    **station,
                }
            )

    assay_xyz_rows = position_assays_xyz(
        tables["assay.csv"].rows,
        trajectories,
        **identity,
        zero_dogleg_epsilon_rad=config.dogleg_epsilon_rad,
        md_tolerance_m=config.interval_tolerance_m,
    )
    observed_distribution = observed_grade_distribution(
        tables["assay.csv"].rows,
        variable=run_settings.primary_element,
        unit="%",
    )
    grade_bins = grade_distribution_rows(
        tables["assay.csv"].rows,
        variable=run_settings.primary_element,
        unit="%",
        boundaries=config.grade_bin_boundaries,
        **identity,
    )
    reference_grade_intercepts: list[dict[str, Any]] | None = None
    if run_settings.reference_grade_analysis_enabled:
        assert run_settings.reference_grade is not None
        reference_grade_intercepts = build_reference_grade_intercepts(
            tables["assay.csv"].rows,
            trajectories,
            **identity,
            reference_grade=run_settings.reference_grade,
            interval_tolerance_m=config.interval_tolerance_m,
            zero_dogleg_epsilon_rad=config.dogleg_epsilon_rad,
        )

    surface = TopographySurface.from_csv(release.topography_path)
    tin_triangles = surface.triangle_vertex_indices
    warning_tolerance = run_settings.ok_tolerance_m
    review_tolerance = run_settings.review_tolerance_m
    collar_topography_rows: list[dict[str, Any]] = []
    for hole_id in sorted(collars):
        collar = collars[hole_id]
        try:
            x, y, collar_z = float(collar["x"]), float(collar["y"]), float(collar["z"])
        except ValueError:
            continue
        if not all(math.isfinite(value) for value in (x, y, collar_z)):
            continue
        evaluation = surface.evaluate(x, y)
        topography_z = evaluation.topography_z
        delta_z = None if topography_z is None else collar_z - topography_z
        classification = classify_topography_consistency(
            delta_z,
            evaluation.support_status,
            warning_tolerance_m=warning_tolerance,
            review_tolerance_m=review_tolerance,
        )
        if classification == "ERROR":
            findings.append(
                Finding.create(
                    "COLLAR_OUTSIDE_TOPOGRAPHY_HULL",
                    Severity.ERROR,
                    "collar lies outside the topographic convex hull; no extrapolation was used",
                    blocking=True,
                    table="collar.csv",
                    hole_id=hole_id,
                    field="x,y",
                    observed_value=[x, y],
                    expected_condition="collar XY inside the Delaunay convex hull",
                    source=release.topography_source,
                    provenance_kind="CALCULATED",
                )
            )
        elif classification == "WARNING":
            findings.append(
                Finding.create(
                    "COLLAR_TOPOGRAPHY_WARNING",
                    Severity.WARNING,
                    "collar/topography residual exceeds the educational warning tolerance",
                    table="collar.csv",
                    hole_id=hole_id,
                    field="delta_z_m",
                    observed_value=delta_z,
                    expected_condition=f"absolute residual <= {warning_tolerance} m",
                    source=release.topography_source,
                    provenance_kind="INFERRED",
                )
            )
        elif classification == "REQUIRES_REVIEW":
            findings.append(
                Finding.create(
                    "COLLAR_TOPOGRAPHY_REQUIRES_REVIEW",
                    Severity.WARNING,
                    "collar/topography residual exceeds the educational review tolerance",
                    requires_review=True,
                    table="collar.csv",
                    hole_id=hole_id,
                    field="delta_z_m",
                    observed_value=delta_z,
                    expected_condition=f"absolute residual <= {review_tolerance} m",
                    source=release.topography_source,
                    provenance_kind="INFERRED",
                )
            )
        collar_topography_rows.append(
            {
                **identity,
                "campaign_id": collar["campaign_id"],
                "hole_id": hole_id,
                "collar_x": x,
                "collar_y": y,
                "collar_z": collar_z,
                "topography_z": topography_z,
                "delta_z_m": delta_z,
                "surface_method": surface.method_identifier,
                "support_status": evaluation.support_status,
                "nearest_support_distance_m": evaluation.nearest_support_distance_m,
                "tolerance_warning_m": warning_tolerance,
                "tolerance_review_m": review_tolerance,
                "consistency_class": classification,
                "collar_z_provenance": "OBSERVED",
                "topography_z_provenance": "OBSERVED"
                if evaluation.support_status == "EXACT_XY"
                else "CALCULATED",
                "delta_z_provenance": "CALCULATED",
                "classification_provenance": "INFERRED",
            }
        )

    verdict = readiness_verdict(findings)
    counts = finding_counts(findings)
    readiness = {
        "verdict": verdict.value,
        "module_status": _status(verdict).value,
        "finding_counts": counts,
    }

    total_drilled = sum(values_for(tables["collar.csv"].rows, "final_depth_m"))
    depths = values_for(tables["collar.csv"].rows, "final_depth_m")
    residuals = [
        float(row["delta_z_m"])
        for row in collar_topography_rows
        if row["delta_z_m"] is not None
    ]
    residual_statistics = _stats(residuals)
    residual_statistics["maximum_absolute"] = max(
        (abs(value) for value in residuals), default=None
    )
    residual_table = sorted(
        collar_topography_rows,
        key=lambda row: (
            row["delta_z_m"] is None,
            -(abs(float(row["delta_z_m"])) if row["delta_z_m"] is not None else 0.0),
            row["hole_id"],
        ),
    )
    density_values = values_for(tables["density.csv"].rows, "density_t_m3")
    density_summary = {
        **_interval_coverage(tables["density.csv"].rows),
        "coverage_percent_of_drilled_metres": (
            100.0 * sum(values_for(tables["density.csv"].rows, "length_m")) / total_drilled
            if total_drilled
            else None
        ),
        "statistics": _stats(density_values),
        "interpolation_performed": False,
    }
    drilling_summary = {
        "hole_count": len(collars),
        "campaign_count": len({row["campaign_id"] for row in collars.values()}),
        "campaigns": sorted({row["campaign_id"] for row in collars.values()}),
        "total_drilled_metres": total_drilled,
        "final_depth_m": _stats(depths),
        "collar_extent": {
            axis: {"minimum": min(values), "maximum": max(values)}
            for axis in ("x", "y", "z")
            if (values := values_for(tables["collar.csv"].rows, axis))
        },
    }
    survey_summary = _survey_summary(tables["survey.csv"].rows, collars)
    dogleg_normalization_m = float(config.values["survey"]["dogleg_normalization_m"])
    dogleg_severities = [
        float(row["dogleg_deg"]) * dogleg_normalization_m / float(row["interval_md_m"])
        for row in trajectory_rows
        if float(row["interval_md_m"]) > 0.0
    ]
    drillhole_geometry_summary = {
        **survey_summary,
        "algorithm": "MINIMUM_CURVATURE",
        "coordinate_conventions": dict(config.values["coordinate_system"]),
        "drillholes_desurveyed": len(trajectories),
        "trajectory_station_count": len(trajectory_rows),
        "assays_positioned_xyz": len(assay_xyz_rows),
        "terminal_extension_count": sum(
            row["station_type"] == "TERMINAL_EXTENSION" for row in trajectory_rows
        ),
        "maximum_dogleg_deg_per_30m": max(dogleg_severities, default=0.0),
    }
    assay_summary = {
        "raw_interval_count": len(tables["assay.csv"].rows),
        "classifications": overall_classifications,
        "statistics": [row for row in assay_rows if row["scope_type"] == "ALL"],
        "compositing_performed": False,
        "length_weighting_performed": False,
        "capping_performed": False,
    }
    lithology_summary = _interval_coverage(
        tables["lithology.csv"].rows, code_field="lith_code"
    )
    alteration_summary = _interval_coverage(
        tables["alteration.csv"].rows, code_field="alteration_code"
    )
    topography_summary = {
        "source_sha256": release.source_hashes[release.topography_source],
        "source_point_count": int(len(surface.xy)),
        "scientific_triangle_count": int(len(tin_triangles)),
        "numpy_version": surface.numpy_version,
        "scipy_version": surface.scipy_version,
        "qhull_backed_method_identifier": surface.method_identifier,
        "interpolation_method": "BARYCENTRIC_LINEAR_WITHIN_DELAUNAY_TRIANGLE",
        "extrapolation_performed": False,
        "support_status_counts": dict(
            sorted(Counter(row["support_status"] for row in collar_topography_rows).items())
        ),
        "consistency_class_counts": dict(
            sorted(Counter(row["consistency_class"] for row in collar_topography_rows).items())
        ),
        "nearest_support_distance_m": _stats(
            [float(row["nearest_support_distance_m"]) for row in collar_topography_rows]
        ),
        "residual_statistics_m": residual_statistics,
        "warning_tolerance_m": warning_tolerance,
        "review_tolerance_m": review_tolerance,
        "tolerance_provenance": "ASSUMED_EDUCATIONAL_PROJECT_THRESHOLD",
        "residuals_descending_absolute_delta_z": residual_table,
    }
    if reference_grade_intercepts is None:
        reference_summary: dict[str, Any] = {
            "status": "NOT_REQUESTED",
            "reference_grade_analysis_enabled": False,
            "reference_grade": None,
            "variable": run_settings.primary_element,
            "unit": "%",
            "interpretation": "ALONG_HOLE_REFERENCE_GRADE_INTERCEPT",
            "thickness_semantic": "NOT_TRUE_GEOLOGICAL_THICKNESS",
        }
    else:
        reference_summary = {
            "status": "COMPLETED",
            "reference_grade_analysis_enabled": True,
            "reference_grade": run_settings.reference_grade,
            "variable": run_settings.primary_element,
            "unit": "%",
            "intercept_count": len(reference_grade_intercepts),
            "intercept_metres": sum(
                float(row["intercept_length_m"])
                for row in reference_grade_intercepts
            ),
            "drillholes_represented": len(
                {str(row["hole_id"]) for row in reference_grade_intercepts}
            ),
            "interpretation": "ALONG_HOLE_REFERENCE_GRADE_INTERCEPT",
            "thickness_semantic": "NOT_TRUE_GEOLOGICAL_THICKNESS",
            "economic_cut_off_grade": False,
            "domain_boundary": False,
        }
    assay_positioning_summary = {
        "source_assay_count": len(tables["assay.csv"].rows),
        "positioned_assay_count": len(assay_xyz_rows),
        "positions_per_assay": ["FROM", "MID", "TO"],
        "trajectory_evaluation": "CONTINUOUS_MINIMUM_CURVATURE",
        "station_snapping": False,
    }

    exploration_html, visualization_summary = build_exploration_3d_html(
        surface,
        trajectory_rows,
        assay_xyz_rows,
        reference_grade=run_settings.reference_grade,
        maximum_topography_vertices=int(
            config.values["visualization"]["maximum_topography_vertices"]
        ),
        **identity,
    )
    visualization_summary["html_byte_size"] = len(exploration_html.encode("utf-8"))
    visualization_summary["relative_path"] = (
        f"{context.project_id}/{context.dataset_id}/{context.release_id}/m01/exploration_3d.html"
    )

    dataset_summary = {
        "coordinate_system": dict(config.values["coordinate_system"]),
        "campaign_aliases": dict(config.campaign_aliases),
        "drilling": drilling_summary,
        "survey": survey_summary,
        "assay": assay_summary,
        "assay_positioning": assay_positioning_summary,
        "observed_grade_distribution": observed_distribution,
        "grade_bins": grade_bins,
        "reference_grade_intercepts": reference_summary,
        "density": density_summary,
        "lithology": lithology_summary,
        "alteration": alteration_summary,
        "collar_topography": topography_summary,
        "visualization": visualization_summary,
        "readiness": readiness,
    }
    technical_summary = build_technical_summary(
        project_name=str(context.manifest.get("project_name") or context.project_id),
        dataset_id=context.dataset_id,
        release_id=context.release_id,
        drilling=drilling_summary,
        validation=readiness,
        drillhole_geometry=drillhole_geometry_summary,
        observed_grade=observed_distribution,
        topography=topography_summary,
        density=density_summary,
        reference=reference_summary,
    )
    dataset_summary["technical_summary"] = technical_summary
    if run_settings.interactive:
        dataset_summary["execution_settings"] = {
            "analysis": run_settings.analysis_payload(),
            "topography_validation": {
                "ok_tolerance_m": warning_tolerance,
                "review_tolerance_m": review_tolerance,
            },
        }
    artifacts = write_m01_artifacts(
        context,
        dataset_summary=dataset_summary,
        findings=findings,
        readiness=readiness,
        source_hashes=release.source_hashes,
        trajectory_rows=trajectory_rows,
        collar_topography_rows=collar_topography_rows,
        assay_statistics_rows=assay_rows,
        assay_xyz_rows=assay_xyz_rows,
        grade_distribution_rows=grade_bins,
        reference_grade_intercept_rows=reference_grade_intercepts,
        exploration_3d_html=exploration_html,
        technical_summary_markdown=render_technical_summary_markdown(
            technical_summary
        ),
        topography_tin_vertex_rows=(
            {
                "vertex_index": index,
                "source_pid": float(surface.pid[index]),
                "x": float(surface.xy[index, 0]),
                "y": float(surface.xy[index, 1]),
                "z": float(surface.z[index]),
            }
            for index in range(len(surface.pid))
        ),
        topography_tin_triangle_rows=(
            {
                "triangle_index": index,
                "vertex_index_1": int(vertices[0]),
                "vertex_index_2": int(vertices[1]),
                "vertex_index_3": int(vertices[2]),
            }
            for index, vertices in enumerate(tin_triangles)
        ),
    )
    run_config_artifact = write_m01_run_config(
        context,
        module_version=MODULE_VERSION,
        primary_element=run_settings.primary_element,
        reference_grade_analysis_enabled=(
            run_settings.reference_grade_analysis_enabled
        ),
        reference_grade=run_settings.reference_grade,
        ok_tolerance_m=warning_tolerance,
        review_tolerance_m=review_tolerance,
    )
    artifacts = artifacts + (run_config_artifact,)

    report_payload = {
        "schema_version": "m01.report.v1.1",
        **identity,
        "overview": drilling_summary,
        "validation_status": readiness,
        "drillhole_geometry": drillhole_geometry_summary,
        "collar_topography": topography_summary,
        "observed_grade_distribution": observed_distribution,
        "grade_bins": grade_bins,
        "density_observations": density_summary,
        "lithology_alteration_coverage": {
            "lithology": lithology_summary,
            "alteration": alteration_summary,
        },
        "reference_grade_intercepts": reference_summary,
        "visualization": visualization_summary,
        "technical_findings": [
            item.to_dict() for item in sorted(findings, key=lambda item: item.finding_id)
        ],
        "readiness": readiness,
        "technical_summary": technical_summary,
    }
    if run_settings.interactive:
        report_payload["execution_settings"] = {
            "analysis": run_settings.analysis_payload(),
            "topography_validation": {
                "ok_tolerance_m": warning_tolerance,
                "review_tolerance_m": review_tolerance,
            },
        }
    config_source = config.path.relative_to(context.project_root).as_posix()
    provenance_items = [
        ProvenanceRecord(
            kind=ProvenanceKind.OBSERVED,
            name="source_sha256",
            value=dict(sorted(release.source_hashes.items())),
            source=f"{context.dataset_path} and {release.topography_path}",
            method="SHA-256",
            rationale="Source bytes are inventoried without modification.",
        ),
        ProvenanceRecord(
            kind=ProvenanceKind.ASSUMED,
            name="m01_configuration",
            value=dict(config.values),
            source=config_source,
            rationale="Approved educational/project conventions and validation tolerances.",
        ),
        ProvenanceRecord(
            kind=ProvenanceKind.CALCULATED,
            name="drillhole_and_assay_geometry",
            value={
                "algorithm": "MINIMUM_CURVATURE",
                "station_count": len(trajectory_rows),
                "positioned_assay_count": len(assay_xyz_rows),
            },
            method="Continuous Minimum Curvature",
            rationale="Coordinates calculated from preserved collar, survey and assay observations.",
        ),
        ProvenanceRecord(
            kind=ProvenanceKind.CALCULATED,
            name="observed_grade_distribution",
            value=observed_distribution,
            method="DESCRIPTIVE_STATISTICS_ALL_VALID_ASSAYS",
            rationale="All valid observed Cu assays, including zero and low grades, are represented.",
        ),
        ProvenanceRecord(
            kind=ProvenanceKind.INFERRED,
            name="readiness_verdict",
            value=verdict.value,
            method="m01.readiness.v1",
            rationale="Mapped from explicit blocking and review flags.",
        ),
    ]
    if run_settings.interactive:
        provenance_items.insert(
            2,
            ProvenanceRecord(
                kind=ProvenanceKind.ASSUMED,
                name="interactive_run_settings",
                value={
                    "analysis": run_settings.analysis_payload(),
                    "topography_validation": {
                        "ok_tolerance_m": warning_tolerance,
                        "review_tolerance_m": review_tolerance,
                    },
                },
                source="student terminal confirmation",
                rationale=(
                    "Explicit interactive selections override the module configuration defaults."
                ),
            ),
        )
    if reference_grade_intercepts is not None:
        provenance_items.insert(
            -1,
            ProvenanceRecord(
                kind=ProvenanceKind.CALCULATED,
                name="reference_grade_intercepts",
                value=reference_summary,
                method="CONTIGUOUS_ASSAYS_AT_OR_ABOVE_REFERENCE_GRADE",
                rationale=(
                    "Optional descriptive along-hole analysis only; it is not a cut-off, "
                    "domain, ore/waste definition, or true geological thickness."
                ),
            ),
        )
    provenance = tuple(provenance_items)

    completed_at = datetime.now(timezone.utc)
    summary = (
        f"{len(collars)} drillholes validated and desurveyed; "
        f"{len(assay_xyz_rows)} assays positioned in 3D; complete observed Cu "
        "grade distribution calculated."
    )
    metrics = {
        "hole_count": len(collars),
        "total_drilled_m": total_drilled,
        "total_drilled_metres": total_drilled,
        "survey_station_count": len(tables["survey.csv"].rows),
        "assay_count": len(tables["assay.csv"].rows),
        "assays_positioned_count": len(assay_xyz_rows),
        "validation_error_count": counts["blocking_error_count"],
        "validation_warning_count": counts["warning_count"],
        "validation_status": verdict.value,
        "finding_counts": counts,
        "readiness_verdict": verdict.value,
        "trajectory_station_count": len(trajectory_rows),
        "drillholes_desurveyed_count": len(trajectories),
        "terminal_extension_count": drillhole_geometry_summary[
            "terminal_extension_count"
        ],
        "maximum_dogleg_deg_per_30m": drillhole_geometry_summary[
            "maximum_dogleg_deg_per_30m"
        ],
        "observed_grade_record_count": observed_distribution["record_count"],
        "observed_grade_assayed_metres": observed_distribution["assayed_metres"],
        "observed_grade_minimum": observed_distribution["minimum"],
        "observed_grade_maximum": observed_distribution["maximum"],
        "observed_grade_mean": observed_distribution["mean"],
        "observed_grade_median": observed_distribution["median"],
        "observed_grade_population_stddev": observed_distribution["population_stddev"],
        "observed_grade_coefficient_of_variation": observed_distribution[
            "coefficient_of_variation"
        ],
        "grade_bin_count": len(grade_bins),
        "reference_grade_analysis_enabled": (
            run_settings.reference_grade_analysis_enabled
        ),
        "reference_grade": run_settings.reference_grade,
        "reference_grade_intercept_count": (
            0 if reference_grade_intercepts is None else len(reference_grade_intercepts)
        ),
        "reference_grade_intercept_metres": reference_summary.get(
            "intercept_metres", 0.0
        ),
        "reference_grade_drillhole_count": reference_summary.get(
            "drillholes_represented", 0
        ),
        "visualization_relative_path": visualization_summary["relative_path"],
        "technical_summary_relative_path": (
            f"{context.project_id}/{context.dataset_id}/{context.release_id}/"
            "m01/m01_technical_summary.md"
        ),
    }
    return ModuleResult(
        module_id=MODULE_ID,
        module_version=MODULE_VERSION,
        status=_status(verdict),
        project_id=context.project_id,
        dataset_id=context.dataset_id,
        release_id=context.release_id,
        started_at=started_at,
        completed_at=completed_at,
        summary=summary,
        metrics=metrics,
        provenance=provenance,
        artifacts=artifacts,
        warnings=tuple(
            item.message for item in findings if item.severity is Severity.WARNING
        ),
        errors=tuple(
            item.message for item in findings if item.severity is Severity.ERROR
        ),
        report_payload=report_payload,
    )
