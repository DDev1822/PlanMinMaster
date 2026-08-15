"""Minimum Curvature desurvey using the approved M01 coordinate conventions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CurvatureIncrement:
    dogleg_rad: float
    ratio_factor: float
    delta_easting_m: float
    delta_northing_m: float
    delta_z_m: float


@dataclass(frozen=True)
class TrajectoryPoint:
    measured_depth_m: float
    x: float
    y: float
    z: float
    azimuth_deg: float
    dip_deg: float


def minimum_curvature_increment(
    delta_md_m: float,
    azimuth_1_deg: float,
    dip_1_deg: float,
    azimuth_2_deg: float,
    dip_2_deg: float,
    *,
    zero_dogleg_epsilon_rad: float,
) -> CurvatureIncrement:
    a1 = math.radians(azimuth_1_deg)
    a2 = math.radians(azimuth_2_deg)
    d1 = math.radians(dip_1_deg)
    d2 = math.radians(dip_2_deg)
    cosine = (
        math.sin(d1) * math.sin(d2)
        + math.cos(d1) * math.cos(d2) * math.cos(a2 - a1)
    )
    beta = math.acos(max(-1.0, min(1.0, cosine)))
    ratio_factor = (
        1.0
        if beta <= zero_dogleg_epsilon_rad
        else (2.0 / beta) * math.tan(beta / 2.0)
    )
    half = delta_md_m / 2.0
    delta_easting = half * (
        math.cos(d1) * math.sin(a1) + math.cos(d2) * math.sin(a2)
    ) * ratio_factor
    delta_northing = half * (
        math.cos(d1) * math.cos(a1) + math.cos(d2) * math.cos(a2)
    ) * ratio_factor
    delta_z = half * (math.sin(d1) + math.sin(d2)) * ratio_factor
    return CurvatureIncrement(
        dogleg_rad=0.0 if beta <= zero_dogleg_epsilon_rad else beta,
        ratio_factor=ratio_factor,
        delta_easting_m=delta_easting,
        delta_northing_m=delta_northing,
        delta_z_m=delta_z,
    )


def desurvey_hole(
    collar: Mapping[str, str],
    surveys: Sequence[Mapping[str, str]],
    *,
    zero_dogleg_epsilon_rad: float,
) -> list[dict[str, object]]:
    if not surveys:
        return []
    ordered = sorted(surveys, key=lambda row: float(row["depth_m"]))
    stations: list[dict[str, object]] = []
    first_md = float(ordered[0]["depth_m"])
    controls: list[dict[str, object]] = []
    if first_md > 0.0:
        controls.append(
            {
                "md_m": 0.0,
                "azimuth_deg": float(collar["azimuth_deg"]),
                "dip_deg": float(collar["dip_deg"]),
                "station_type": "COLLAR",
                "orientation_provenance": "COLLAR",
            }
        )
    for index, row in enumerate(ordered):
        md = float(row["depth_m"])
        controls.append(
            {
                "md_m": md,
                "azimuth_deg": float(row["azimuth_deg"]),
                "dip_deg": float(row["dip_deg"]),
                "station_type": "COLLAR_SURVEY" if md == 0.0 and index == 0 else "SURVEY",
                "orientation_provenance": "SURVEY",
            }
        )
    final_depth = float(collar["final_depth_m"])
    if float(controls[-1]["md_m"]) < final_depth:
        controls.append(
            {
                "md_m": final_depth,
                "azimuth_deg": controls[-1]["azimuth_deg"],
                "dip_deg": controls[-1]["dip_deg"],
                "station_type": "TERMINAL_EXTENSION",
                "orientation_provenance": "TERMINAL_EXTENSION",
            }
        )

    x = float(collar["x"])
    y = float(collar["y"])
    z = float(collar["z"])
    for index, control in enumerate(controls):
        if index == 0:
            increment = CurvatureIncrement(0.0, 1.0, 0.0, 0.0, 0.0)
            interval_md = 0.0
        else:
            previous = controls[index - 1]
            interval_md = float(control["md_m"]) - float(previous["md_m"])
            increment = minimum_curvature_increment(
                interval_md,
                float(previous["azimuth_deg"]),
                float(previous["dip_deg"]),
                float(control["azimuth_deg"]),
                float(control["dip_deg"]),
                zero_dogleg_epsilon_rad=zero_dogleg_epsilon_rad,
            )
            x += increment.delta_easting_m
            y += increment.delta_northing_m
            z += increment.delta_z_m
        stations.append(
            {
                "station_index": index,
                "station_type": control["station_type"],
                "md_m": float(control["md_m"]),
                "x": x,
                "y": y,
                "z": z,
                "azimuth_deg": float(control["azimuth_deg"]),
                "dip_deg": float(control["dip_deg"]),
                "interval_md_m": interval_md,
                "dogleg_deg": math.degrees(increment.dogleg_rad),
                "ratio_factor": increment.ratio_factor,
                "delta_easting_m": increment.delta_easting_m,
                "delta_northing_m": increment.delta_northing_m,
                "delta_z_m": increment.delta_z_m,
                "cumulative_tvd_m": float(collar["z"]) - z,
                "position_provenance": "OBSERVED" if index == 0 else "CALCULATED",
                "orientation_provenance": control["orientation_provenance"],
            }
        )
    return stations


def _orientation_vector(azimuth_deg: float, dip_deg: float) -> tuple[float, float, float]:
    azimuth = math.radians(azimuth_deg)
    dip = math.radians(dip_deg)
    return (
        math.cos(dip) * math.sin(azimuth),
        math.cos(dip) * math.cos(azimuth),
        math.sin(dip),
    )


def _vector_orientation(vector: tuple[float, float, float]) -> tuple[float, float]:
    easting, northing, vertical = vector
    length = math.sqrt(easting * easting + northing * northing + vertical * vertical)
    if length == 0.0:
        raise ValueError("orientation vector cannot have zero length")
    easting /= length
    northing /= length
    vertical = max(-1.0, min(1.0, vertical / length))
    azimuth = math.degrees(math.atan2(easting, northing)) % 360.0
    dip = math.degrees(math.asin(vertical))
    return azimuth, dip


def interpolate_orientation(
    azimuth_1_deg: float,
    dip_1_deg: float,
    azimuth_2_deg: float,
    dip_2_deg: float,
    fraction: float,
    *,
    zero_dogleg_epsilon_rad: float,
) -> tuple[float, float]:
    """Spherically interpolate an orientation within one survey segment."""

    if not 0.0 <= fraction <= 1.0:
        raise ValueError("orientation fraction must be within [0,1]")
    first = _orientation_vector(azimuth_1_deg, dip_1_deg)
    second = _orientation_vector(azimuth_2_deg, dip_2_deg)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(first, second))))
    dogleg = math.acos(dot)
    if dogleg <= zero_dogleg_epsilon_rad:
        return azimuth_1_deg, dip_1_deg
    sine = math.sin(dogleg)
    if abs(sine) <= zero_dogleg_epsilon_rad:
        vector = tuple(
            (1.0 - fraction) * a + fraction * b
            for a, b in zip(first, second)
        )
    else:
        first_weight = math.sin((1.0 - fraction) * dogleg) / sine
        second_weight = math.sin(fraction * dogleg) / sine
        vector = tuple(
            first_weight * a + second_weight * b
            for a, b in zip(first, second)
        )
    return _vector_orientation(vector)


def evaluate_trajectory_at_md(
    stations: Sequence[Mapping[str, object]],
    measured_depth_m: float,
    *,
    zero_dogleg_epsilon_rad: float,
    md_tolerance_m: float,
) -> TrajectoryPoint:
    """Evaluate continuous Minimum Curvature geometry without station snapping."""

    if not stations:
        raise ValueError("trajectory requires at least one station")
    ordered = sorted(stations, key=lambda row: float(row["md_m"]))
    minimum_md = float(ordered[0]["md_m"])
    maximum_md = float(ordered[-1]["md_m"])
    if measured_depth_m < minimum_md - md_tolerance_m or measured_depth_m > maximum_md + md_tolerance_m:
        raise ValueError("measured depth lies outside the computed trajectory")
    target_md = min(max(measured_depth_m, minimum_md), maximum_md)

    for station in ordered:
        station_md = float(station["md_m"])
        if abs(target_md - station_md) <= md_tolerance_m:
            return TrajectoryPoint(
                measured_depth_m=measured_depth_m,
                x=float(station["x"]),
                y=float(station["y"]),
                z=float(station["z"]),
                azimuth_deg=float(station["azimuth_deg"]),
                dip_deg=float(station["dip_deg"]),
            )

    for start, end in zip(ordered, ordered[1:]):
        start_md = float(start["md_m"])
        end_md = float(end["md_m"])
        if start_md < target_md < end_md:
            fraction = (target_md - start_md) / (end_md - start_md)
            target_azimuth, target_dip = interpolate_orientation(
                float(start["azimuth_deg"]),
                float(start["dip_deg"]),
                float(end["azimuth_deg"]),
                float(end["dip_deg"]),
                fraction,
                zero_dogleg_epsilon_rad=zero_dogleg_epsilon_rad,
            )
            increment = minimum_curvature_increment(
                target_md - start_md,
                float(start["azimuth_deg"]),
                float(start["dip_deg"]),
                target_azimuth,
                target_dip,
                zero_dogleg_epsilon_rad=zero_dogleg_epsilon_rad,
            )
            return TrajectoryPoint(
                measured_depth_m=measured_depth_m,
                x=float(start["x"]) + increment.delta_easting_m,
                y=float(start["y"]) + increment.delta_northing_m,
                z=float(start["z"]) + increment.delta_z_m,
                azimuth_deg=target_azimuth,
                dip_deg=target_dip,
            )
    raise ValueError("measured depth could not be located in the trajectory")
