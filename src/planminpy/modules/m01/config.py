"""Load and validate the project-visible M01 engineering assumptions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from planminpy.core.contracts import PlanMinPyError


class M01ConfigError(PlanMinPyError):
    """Raised when configs/m01.json is missing or malformed."""


@dataclass(frozen=True)
class M01Config:
    path: Path
    values: Mapping[str, Any]

    @property
    def campaign_aliases(self) -> dict[str, str]:
        return dict(self.values["campaign_aliases"])

    @property
    def interval_tolerance_m(self) -> float:
        return float(self.values["numeric"]["interval_length_abs_tolerance_m"])

    @property
    def dogleg_epsilon_rad(self) -> float:
        return float(self.values["numeric"]["zero_dogleg_epsilon_rad"])

    @property
    def primary_element(self) -> str:
        return str(self.values["analysis"]["primary_element"])

    @property
    def reference_grade_enabled_by_default(self) -> bool:
        return bool(self.values["reference_grade_analysis"]["enabled_by_default"])

    @property
    def default_reference_grade(self) -> float:
        return float(self.values["reference_grade_analysis"]["default_reference_grade"])

    @property
    def grade_bin_boundaries(self) -> tuple[float, ...]:
        return tuple(float(value) for value in self.values["grade_distribution"]["boundaries"])

    @property
    def topography_ok_tolerance_m(self) -> float:
        return float(self.values["topography"]["warning_tolerance_m"])

    @property
    def topography_review_tolerance_m(self) -> float:
        return float(self.values["topography"]["review_tolerance_m"])


def load_config(project_root: Path) -> M01Config:
    path = (project_root / "configs" / "m01.json").resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M01ConfigError(f"cannot load M01 configuration: {path}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != "m01.config.v1.1":
        raise M01ConfigError("M01 configuration schema must be m01.config.v1.1")
    required = {
        "coordinate_system",
        "campaign_aliases",
        "numeric",
        "survey",
        "density",
        "topography",
        "analysis",
        "grade_distribution",
        "reference_grade_analysis",
        "visualization",
    }
    if not required.issubset(raw):
        raise M01ConfigError("M01 configuration is missing required sections")
    aliases = raw["campaign_aliases"]
    if not isinstance(aliases, dict) or not aliases:
        raise M01ConfigError("campaign_aliases must be a non-empty object")
    if len(set(aliases.values())) != len(aliases):
        raise M01ConfigError("campaign aliases must map one-to-one")
    if float(raw["numeric"]["interval_length_abs_tolerance_m"]) <= 0:
        raise M01ConfigError("interval tolerance must be positive")
    if float(raw["numeric"]["zero_dogleg_epsilon_rad"]) <= 0:
        raise M01ConfigError("dogleg epsilon must be positive")
    warning_tolerance = float(raw["topography"]["warning_tolerance_m"])
    review_tolerance = float(raw["topography"]["review_tolerance_m"])
    if warning_tolerance <= 0 or review_tolerance <= warning_tolerance:
        raise M01ConfigError("topography tolerances must satisfy 0 < warning < review")
    analysis = raw["analysis"]
    if analysis.get("primary_element") != "cu_pct":
        raise M01ConfigError("M01 v1.1 primary analytical element must be cu_pct")
    if analysis.get("unit") != "%":
        raise M01ConfigError("M01 v1.1 primary analytical unit must be %")
    boundaries = raw["grade_distribution"].get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) < 2:
        raise M01ConfigError("grade distribution boundaries must be a list")
    parsed_boundaries = [float(value) for value in boundaries]
    if any(
        current <= previous
        for previous, current in zip(parsed_boundaries, parsed_boundaries[1:])
    ):
        raise M01ConfigError("grade distribution boundaries must increase")
    reference = raw["reference_grade_analysis"]
    if not isinstance(reference.get("enabled_by_default"), bool):
        raise M01ConfigError("reference-grade default enablement must be boolean")
    reference_grade = float(reference["default_reference_grade"])
    if not 0.0 <= reference_grade <= 100.0:
        raise M01ConfigError("default reference grade must be a valid percent")
    if reference.get("purpose") != "drillhole_intercept_reference_only":
        raise M01ConfigError("reference-grade purpose must remain explicit")
    if int(raw["visualization"]["maximum_topography_vertices"]) < 3:
        raise M01ConfigError("visualization requires at least three topography vertices")
    return M01Config(path=path, values=MappingProxyType(raw))
