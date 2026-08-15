"""Assay positioning, reference-grade intervals, and detached legacy utilities.

M01 v1.1 executes only :func:`position_assays_xyz` and
:func:`build_reference_grade_intercepts`.  The influence-area inventory helpers
below remain available solely as detached legacy experiments and are not part of
the module registry, runner, report, or artifact contract.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.spatial import Delaunay

from planminpy.core.contracts import PlanMinPyError
from planminpy.modules.m01.geometry import evaluate_trajectory_at_md


class M01InventoryError(PlanMinPyError):
    """Raised when preliminary inventory mathematics cannot be evaluated safely."""


def position_assays_xyz(
    assay_rows: Sequence[Mapping[str, str]],
    trajectories: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    project_id: str,
    dataset_id: str,
    release_id: str,
    zero_dogleg_epsilon_rad: float,
    md_tolerance_m: float,
) -> list[dict[str, Any]]:
    """Position original assay FROM/MID/TO depths on continuous trajectories."""

    positioned: list[dict[str, Any]] = []
    for row in sorted(
        assay_rows,
        key=lambda item: (item["hole_id"], float(item["from_m"]), item["sample_id"]),
    ):
        trajectory = trajectories.get(row["hole_id"])
        if not trajectory:
            continue
        from_m = float(row["from_m"])
        to_m = float(row["to_m"])
        mid_m = (from_m + to_m) / 2.0
        from_point = evaluate_trajectory_at_md(
            trajectory,
            from_m,
            zero_dogleg_epsilon_rad=zero_dogleg_epsilon_rad,
            md_tolerance_m=md_tolerance_m,
        )
        mid_point = evaluate_trajectory_at_md(
            trajectory,
            mid_m,
            zero_dogleg_epsilon_rad=zero_dogleg_epsilon_rad,
            md_tolerance_m=md_tolerance_m,
        )
        to_point = evaluate_trajectory_at_md(
            trajectory,
            to_m,
            zero_dogleg_epsilon_rad=zero_dogleg_epsilon_rad,
            md_tolerance_m=md_tolerance_m,
        )
        positioned.append(
            {
                "sample_id": row["sample_id"],
                "project_id": project_id,
                "dataset_id": dataset_id,
                "release_id": release_id,
                "campaign_id": row["campaign_id"],
                "hole_id": row["hole_id"],
                "from_m": row["from_m"],
                "to_m": row["to_m"],
                "length_m": row["length_m"],
                "mid_m": mid_m,
                "x_from": from_point.x,
                "y_from": from_point.y,
                "z_from": from_point.z,
                "x_mid": mid_point.x,
                "y_mid": mid_point.y,
                "z_mid": mid_point.z,
                "x_to": to_point.x,
                "y_to": to_point.y,
                "z_to": to_point.z,
                "cu_pct": row["cu_pct"],
                "mo_pct": row["mo_pct"],
                "au_gt": row["au_gt"],
            }
        )
    return positioned


def length_weighted_grade(
    grade_length_pairs: Sequence[tuple[float, float]],
) -> float:
    total_length = sum(length for _, length in grade_length_pairs)
    if total_length <= 0.0:
        return 0.0
    return sum(grade * length for grade, length in grade_length_pairs) / total_length


def build_reference_grade_intercepts(
    assay_rows: Sequence[Mapping[str, str]],
    trajectories: Mapping[str, Sequence[Mapping[str, object]]],
    *,
    project_id: str,
    dataset_id: str,
    release_id: str,
    reference_grade: float,
    interval_tolerance_m: float,
    zero_dogleg_epsilon_rad: float,
) -> list[dict[str, Any]]:
    """Merge contiguous assays meeting an optional descriptive reference grade.

    Returned lengths are along-hole intervals.  They are not geological true
    thicknesses, domains, cut-offs, resources, or economic classifications.
    """

    grouped: defaultdict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in assay_rows:
        grouped[row["hole_id"]].append(row)
    intercepts: list[dict[str, Any]] = []

    def append_intercept(hole_id: str, rows: list[Mapping[str, str]]) -> None:
        if not rows:
            return
        from_m = float(rows[0]["from_m"])
        to_m = float(rows[-1]["to_m"])
        pairs = [(float(row["cu_pct"]), float(row["length_m"])) for row in rows]
        intercept_length = sum(length for _, length in pairs)
        midpoint = evaluate_trajectory_at_md(
            trajectories[hole_id],
            (from_m + to_m) / 2.0,
            zero_dogleg_epsilon_rad=zero_dogleg_epsilon_rad,
            md_tolerance_m=interval_tolerance_m,
        )
        intercepts.append(
            {
                "project_id": project_id,
                "dataset_id": dataset_id,
                "release_id": release_id,
                "hole_id": hole_id,
                "campaign_id": rows[0]["campaign_id"],
                "from_m": from_m,
                "to_m": to_m,
                "intercept_length_m": intercept_length,
                "x_mid": midpoint.x,
                "y_mid": midpoint.y,
                "z_mid": midpoint.z,
                "length_weighted_grade": length_weighted_grade(pairs),
                "reference_grade": reference_grade,
                "variable": "cu_pct",
                "unit": "%",
                "sample_count": len(rows),
                "interpretation": "ALONG_HOLE_REFERENCE_GRADE_INTERCEPT",
                "thickness_semantic": "NOT_TRUE_GEOLOGICAL_THICKNESS",
            }
        )

    for hole_id in sorted(grouped):
        current: list[Mapping[str, str]] = []
        for row in sorted(
            grouped[hole_id],
            key=lambda item: (float(item["from_m"]), float(item["to_m"]), item["sample_id"]),
        ):
            grade = float(row["cu_pct"])
            if not math.isfinite(grade) or grade < reference_grade:
                append_intercept(hole_id, current)
                current = []
                continue
            if current and abs(float(current[-1]["to_m"]) - float(row["from_m"])) > interval_tolerance_m:
                append_intercept(hole_id, current)
                current = []
            current.append(row)
        append_intercept(hole_id, current)
    return intercepts


# Everything below this boundary is detached legacy experimental code.  M01
# v1.1 neither imports nor invokes these influence-area/inventory functions.


def delaunay_nodal_influence_areas(
    collar_rows: Sequence[Mapping[str, str]],
) -> tuple[dict[str, float], float]:
    """Allocate one third of every collar Delaunay triangle to each vertex."""

    ordered = sorted(collar_rows, key=lambda row: row["hole_id"])
    if len(ordered) < 3:
        raise M01InventoryError("at least three collars are required for influence areas")
    xy = np.array(
        [[float(row["x"]), float(row["y"])] for row in ordered], dtype=np.float64
    )
    if not np.isfinite(xy).all() or len(np.unique(xy, axis=0)) != len(xy):
        raise M01InventoryError("collar XY must be finite and unique")
    triangulation = Delaunay(xy)
    areas = {row["hole_id"]: 0.0 for row in ordered}
    convex_hull_area = 0.0
    for simplex in triangulation.simplices:
        first, second, third = xy[simplex]
        triangle_area = abs(
            (second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0])
        ) / 2.0
        if not math.isfinite(triangle_area) or triangle_area <= 0.0:
            raise M01InventoryError("collar triangulation contains an invalid triangle")
        convex_hull_area += triangle_area
        share = triangle_area / 3.0
        for index in simplex:
            areas[ordered[int(index)]["hole_id"]] += share
    return areas, convex_hull_area


def density_means_by_hole(
    density_rows: Sequence[Mapping[str, str]],
    hole_ids: Sequence[str],
    *,
    density_method: str = "HOLE_OBSERVED_MEAN",
) -> tuple[dict[str, tuple[float, str]], float]:
    grouped: defaultdict[str, list[float]] = defaultdict(list)
    all_values: list[float] = []
    for row in density_rows:
        try:
            value = float(row["density_t_m3"])
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0.0:
            grouped[row["hole_id"]].append(value)
            all_values.append(value)
    if not all_values:
        raise M01InventoryError("at least one valid observed density is required")
    global_mean = statistics.fmean(all_values)
    if density_method not in {"HOLE_OBSERVED_MEAN", "GLOBAL_OBSERVED_MEAN"}:
        raise M01InventoryError(f"unsupported density method: {density_method}")
    result: dict[str, tuple[float, str]] = {}
    for hole_id in sorted(hole_ids):
        if density_method == "GLOBAL_OBSERVED_MEAN":
            result[hole_id] = (global_mean, "GLOBAL_OBSERVED_MEAN")
        elif grouped.get(hole_id):
            result[hole_id] = (
                statistics.fmean(grouped[hole_id]),
                "HOLE_OBSERVED_MEAN",
            )
        else:
            result[hole_id] = (global_mean, "GLOBAL_MEAN_FALLBACK")
    return result, global_mean


def contained_copper_tonnes(indicative_tonnes: float, cu_pct: float) -> float:
    return indicative_tonnes * cu_pct / 100.0


def indicative_volume_and_tonnes(
    influence_area_m2: float,
    mineralized_intercept_m: float,
    density_t_m3: float,
) -> tuple[float, float]:
    volume = influence_area_m2 * mineralized_intercept_m
    return volume, volume * density_t_m3


def weighted_overall_grade(rows: Sequence[Mapping[str, Any]]) -> float:
    total_tonnes = sum(float(row["indicative_tonnes"]) for row in rows)
    if total_tonnes <= 0.0:
        return 0.0
    return sum(
        float(row["indicative_tonnes"]) * float(row["mineralized_cu_pct"])
        for row in rows
    ) / total_tonnes


def build_preliminary_inventory(
    collar_rows: Sequence[Mapping[str, str]],
    density_rows: Sequence[Mapping[str, str]],
    intercept_rows: Sequence[Mapping[str, Any]],
    *,
    project_id: str,
    dataset_id: str,
    release_id: str,
    threshold_cu_pct: float,
    density_method: str = "HOLE_OBSERVED_MEAN",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    influence_areas, convex_hull_area = delaunay_nodal_influence_areas(collar_rows)
    hole_ids = sorted(row["hole_id"] for row in collar_rows)
    density_by_hole, global_density = density_means_by_hole(
        density_rows,
        hole_ids,
        density_method=density_method,
    )
    intercepts_by_hole: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in intercept_rows:
        intercepts_by_hole[str(row["hole_id"])].append(row)

    rows: list[dict[str, Any]] = []
    for hole_id in hole_ids:
        intercepts = intercepts_by_hole.get(hole_id, [])
        mineralized_metres = sum(float(row["intercept_length_m"]) for row in intercepts)
        grade = length_weighted_grade(
            [
                (float(row["cu_length_weighted_pct"]), float(row["intercept_length_m"]))
                for row in intercepts
            ]
        )
        density, density_source = density_by_hole[hole_id]
        volume, tonnes = indicative_volume_and_tonnes(
            influence_areas[hole_id], mineralized_metres, density
        )
        rows.append(
            {
                "project_id": project_id,
                "dataset_id": dataset_id,
                "release_id": release_id,
                "hole_id": hole_id,
                "influence_area_m2": influence_areas[hole_id],
                "mineralized_intercept_m": mineralized_metres,
                "mineralized_cu_pct": grade,
                "density_t_m3": density,
                "density_source": density_source,
                "indicative_volume_m3": volume,
                "indicative_tonnes": tonnes,
                "contained_cu_tonnes": contained_copper_tonnes(tonnes, grade),
                "mineralization_threshold_cu_pct": threshold_cu_pct,
                "threshold_purpose": "educational_mineralization_threshold",
                "inventory_method": "DELAUNAY_NODAL_AREA_X_DRILLHOLE_INTERCEPT",
                "classification": "PRELIMINARY_NON_CLASSIFIED",
            }
        )

    total_volume = sum(float(row["indicative_volume_m3"]) for row in rows)
    total_tonnes = sum(float(row["indicative_tonnes"]) for row in rows)
    total_grade = weighted_overall_grade(rows)
    total_contained = sum(float(row["contained_cu_tonnes"]) for row in rows)
    total_row = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "release_id": release_id,
        "hole_id": "TOTAL",
        "influence_area_m2": sum(float(row["influence_area_m2"]) for row in rows),
        "mineralized_intercept_m": sum(float(row["mineralized_intercept_m"]) for row in rows),
        "mineralized_cu_pct": total_grade,
        "density_t_m3": total_tonnes / total_volume if total_volume > 0.0 else global_density,
        "density_source": "AGGREGATED_EFFECTIVE_DENSITY",
        "indicative_volume_m3": total_volume,
        "indicative_tonnes": total_tonnes,
        "contained_cu_tonnes": total_contained,
        "mineralization_threshold_cu_pct": threshold_cu_pct,
        "threshold_purpose": "educational_mineralization_threshold",
        "inventory_method": "DELAUNAY_NODAL_AREA_X_DRILLHOLE_INTERCEPT",
        "classification": "PRELIMINARY_NON_CLASSIFIED",
    }
    summary = {
        "inventory_method": "DELAUNAY_NODAL_AREA_X_DRILLHOLE_INTERCEPT",
        "influence_area_method": "DELAUNAY_NODAL_AREA_1_3",
        "classification": "PRELIMINARY_NON_CLASSIFIED",
        "mineralization_threshold_cu_pct": threshold_cu_pct,
        "threshold_purpose": "educational_mineralization_threshold",
        "intercept_length_semantic": "ALONG_HOLE_NOT_TRUE_GEOLOGICAL_THICKNESS",
        "recovery_factor_applied": False,
        "economic_factor_applied": False,
        "modifying_factor_applied": False,
        "collar_convex_hull_area_m2": convex_hull_area,
        "sum_influence_area_m2": total_row["influence_area_m2"],
        "area_reconciliation_error_m2": total_row["influence_area_m2"] - convex_hull_area,
        "global_observed_density_mean_t_m3": global_density,
        "fallback_hole_count": sum(
            row["density_source"] == "GLOBAL_MEAN_FALLBACK" for row in rows
        ),
        "total_indicative_volume_m3": total_volume,
        "total_indicative_tonnes": total_tonnes,
        "weighted_cu_pct": total_grade,
        "contained_cu_tonnes": total_contained,
    }
    if density_method != "HOLE_OBSERVED_MEAN":
        summary["density_method"] = density_method
    return rows + [total_row], summary


def build_inventory_for_method(
    collar_rows: Sequence[Mapping[str, str]],
    density_rows: Sequence[Mapping[str, str]],
    intercept_rows: Sequence[Mapping[str, Any]],
    *,
    project_id: str,
    dataset_id: str,
    release_id: str,
    threshold_cu_pct: float,
    preliminary_analysis_method: str,
    density_method: str = "HOLE_OBSERVED_MEAN",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Dispatch the selected analysis without inventing inventory values."""

    if preliminary_analysis_method == "INTERCEPTS_ONLY":
        return [], {
            "calculated": False,
            "method_selected": "INTERCEPTS_ONLY",
            "classification": "NOT_CALCULATED",
            "mineralization_threshold_cu_pct": threshold_cu_pct,
            "threshold_purpose": "educational_mineralization_threshold",
            "intercept_length_semantic": "ALONG_HOLE_NOT_TRUE_GEOLOGICAL_THICKNESS",
        }
    if preliminary_analysis_method != "DELAUNAY_NODAL":
        raise M01InventoryError(
            f"unsupported preliminary analysis method: {preliminary_analysis_method}"
        )
    return build_preliminary_inventory(
        collar_rows,
        density_rows,
        intercept_rows,
        project_id=project_id,
        dataset_id=dataset_id,
        release_id=release_id,
        threshold_cu_pct=threshold_cu_pct,
        density_method=density_method,
    )


def inventory_consistency_issues(
    inventory_rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    *,
    absolute_tolerance: float,
) -> list[str]:
    holes = [row for row in inventory_rows if row["hole_id"] != "TOTAL"]
    issues: list[str] = []
    if not math.isclose(
        float(summary["sum_influence_area_m2"]),
        float(summary["collar_convex_hull_area_m2"]),
        rel_tol=1e-12,
        abs_tol=absolute_tolerance,
    ):
        issues.append("sum of influence areas does not reconcile to collar convex hull")
    if any(float(row["influence_area_m2"]) <= 0.0 for row in holes):
        issues.append("every drillhole influence area must be greater than zero")
    if any(float(row["indicative_tonnes"]) < 0.0 for row in inventory_rows):
        issues.append("indicative tonnes cannot be negative")
    if any(float(row["contained_cu_tonnes"]) < 0.0 for row in inventory_rows):
        issues.append("contained copper cannot be negative")
    total = next(row for row in inventory_rows if row["hole_id"] == "TOTAL")
    if float(total["indicative_tonnes"]) > 0.0 and not math.isfinite(
        float(total["mineralized_cu_pct"])
    ):
        issues.append("weighted copper grade must be finite when indicative tonnes are positive")
    return issues
