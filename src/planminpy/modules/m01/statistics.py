"""Deterministic raw-interval descriptive statistics for M01."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


PERCENTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)


def linear_percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def numeric_statistics(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "valid_count": 0,
            "minimum": None,
            "maximum": None,
            "mean": None,
            "median": None,
            "population_stddev": None,
            "cv": None,
            "p05": None,
            "p10": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "p99": None,
        }
    mean = statistics.fmean(values)
    standard_deviation = statistics.pstdev(values)
    result: dict[str, float | int | None] = {
        "valid_count": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": mean,
        "median": linear_percentile(values, 0.50),
        "population_stddev": standard_deviation,
        "cv": None if mean == 0.0 else standard_deviation / mean,
    }
    for probability in PERCENTILES:
        percentile_name = f"p{int(probability * 100):02d}"
        result[percentile_name] = linear_percentile(values, probability)
    return result


def analytical_classification(values: Sequence[float]) -> str:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return "EMPTY"
    if all(value == 0.0 for value in finite):
        return "CONSTANT_ZERO"
    if min(finite) == max(finite):
        return "CONSTANT_NONZERO"
    return "VARIABLE"


def assay_statistics_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    project_id: str,
    dataset_id: str,
    release_id: str,
) -> list[dict[str, Any]]:
    elements = (
        ("cu_pct", "percent"),
        ("mo_pct", "percent"),
        ("au_gt", "g/t"),
    )
    scopes: list[tuple[str, str, Sequence[Mapping[str, str]]]] = [
        ("ALL", "ALL", rows)
    ]
    campaigns: defaultdict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        campaigns[row["campaign_id"]].append(row)
    scopes.extend(
        ("CAMPAIGN", campaign, campaigns[campaign])
        for campaign in sorted(campaigns)
    )

    output: list[dict[str, Any]] = []
    for scope_type, scope_id, subset in scopes:
        for element, unit in elements:
            parsed: list[tuple[Mapping[str, str], float]] = []
            missing_count = 0
            for row in subset:
                raw = row[element].strip()
                if not raw:
                    missing_count += 1
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    missing_count += 1
                    continue
                if not math.isfinite(value):
                    missing_count += 1
                    continue
                parsed.append((row, value))
            values = [item[1] for item in parsed]
            summary = numeric_statistics(values)
            if values:
                q1 = linear_percentile(values, 0.25)
                q3 = linear_percentile(values, 0.75)
                high_threshold = q3 + 3.0 * (q3 - q1)
                high_count = sum(value > high_threshold for value in values)
            else:
                high_threshold = None
                high_count = 0
            output.append(
                {
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "release_id": release_id,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "element": element,
                    "unit": unit,
                    "classification": analytical_classification(values),
                    "total_count": len(subset),
                    **summary,
                    "missing_count": missing_count,
                    "zero_count": sum(value == 0.0 for value in values),
                    "negative_count": sum(value < 0.0 for value in values),
                    "assay_metres": sum(float(row["length_m"]) for row, _ in parsed),
                    "q3_plus_3iqr": high_threshold,
                    "q3_plus_3iqr_count": high_count,
                    "statistics_provenance": "CALCULATED",
                }
            )
    return output


def observed_grade_distribution(
    rows: Sequence[Mapping[str, str]],
    *,
    variable: str,
    unit: str,
) -> dict[str, Any]:
    """Summarize every finite observed assay value without grade filtering."""

    parsed: list[tuple[float, float]] = []
    missing_count = 0
    for row in rows:
        raw_grade = (row.get(variable) or "").strip()
        try:
            grade = float(raw_grade)
            length = float(row["length_m"])
        except (KeyError, TypeError, ValueError):
            missing_count += 1
            continue
        if not math.isfinite(grade) or not math.isfinite(length) or length < 0.0:
            missing_count += 1
            continue
        parsed.append((grade, length))

    values = [grade for grade, _ in parsed]
    statistics_payload = numeric_statistics(values)
    return {
        "semantic": "OBSERVED_DRILLHOLE_GRADE_DISTRIBUTION",
        "variable": variable,
        "unit": unit,
        "source_record_count": len(rows),
        "record_count": len(parsed),
        "assayed_metres": sum(length for _, length in parsed),
        "minimum": statistics_payload["minimum"],
        "maximum": statistics_payload["maximum"],
        "mean": statistics_payload["mean"],
        "median": statistics_payload["median"],
        "population_stddev": statistics_payload["population_stddev"],
        "coefficient_of_variation": statistics_payload["cv"],
        "p05": statistics_payload["p05"],
        "p10": statistics_payload["p10"],
        "p25": statistics_payload["p25"],
        "p50": statistics_payload["p50"],
        "p75": statistics_payload["p75"],
        "p90": statistics_payload["p90"],
        "p95": statistics_payload["p95"],
        "p99": statistics_payload["p99"],
        "zero_count": sum(grade == 0.0 for grade, _ in parsed),
        "negative_count": sum(grade < 0.0 for grade, _ in parsed),
        "missing_count": missing_count,
        "weighting": "RECORD_STATISTICS_UNWEIGHTED; ASSAYED_METRES_LENGTH_SUM",
        "provenance": "OBSERVED_AND_CALCULATED",
    }


def grade_distribution_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    variable: str,
    unit: str,
    boundaries: Sequence[float],
    project_id: str,
    dataset_id: str,
    release_id: str,
) -> list[dict[str, Any]]:
    """Bin all finite observed grades using lower-inclusive deterministic intervals."""

    ordered_boundaries = tuple(float(value) for value in boundaries)
    if len(ordered_boundaries) < 2 or any(
        not math.isfinite(value) for value in ordered_boundaries
    ):
        raise ValueError("grade distribution requires finite ordered boundaries")
    if any(
        current <= previous
        for previous, current in zip(ordered_boundaries, ordered_boundaries[1:])
    ):
        raise ValueError("grade distribution boundaries must be strictly increasing")

    observations: list[tuple[float, float]] = []
    for row in rows:
        try:
            grade = float(row[variable])
            length = float(row["length_m"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(grade) and math.isfinite(length) and length >= 0.0:
            observations.append((grade, length))

    bins: list[tuple[float | None, float | None]] = []
    if observations and min(grade for grade, _ in observations) < ordered_boundaries[0]:
        bins.append((None, ordered_boundaries[0]))
    bins.extend(zip(ordered_boundaries, ordered_boundaries[1:]))
    bins.append((ordered_boundaries[-1], None))
    total_metres = sum(length for _, length in observations)

    output: list[dict[str, Any]] = []
    for grade_from, grade_to in bins:
        selected = [
            (grade, length)
            for grade, length in observations
            if (grade_from is None or grade >= grade_from)
            and (grade_to is None or grade < grade_to)
        ]
        assayed_metres = sum(length for _, length in selected)
        output.append(
            {
                "project_id": project_id,
                "dataset_id": dataset_id,
                "release_id": release_id,
                "variable": variable,
                "unit": unit,
                "grade_from": grade_from,
                "grade_to": grade_to,
                "upper_bound_inclusive": False,
                "assay_count": len(selected),
                "assayed_metres": assayed_metres,
                "percentage_of_assayed_metres": (
                    100.0 * assayed_metres / total_metres if total_metres > 0.0 else 0.0
                ),
                "length_weighted_grade": (
                    sum(grade * length for grade, length in selected) / assayed_metres
                    if assayed_metres > 0.0
                    else None
                ),
            }
        )
    return output


def values_for(rows: Iterable[Mapping[str, str]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            value = float(row[field])
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values
