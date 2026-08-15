"""Validated M01 v1.1 analytical selections over project defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from planminpy.core.context import ModuleContext
from planminpy.modules.m01.config import M01Config, M01ConfigError


@dataclass(frozen=True)
class M01RunSettings:
    """Resolved, validated settings for one independent M01 execution."""

    primary_element: str
    reference_grade_analysis_enabled: bool
    reference_grade: float | None
    ok_tolerance_m: float
    review_tolerance_m: float
    interactive: bool

    @classmethod
    def resolve(
        cls,
        context: ModuleContext,
        config: M01Config,
    ) -> "M01RunSettings":
        overrides: Mapping[str, Any] = context.settings

        primary_element = str(
            overrides.get("primary_element", config.primary_element)
        ).strip()
        if primary_element != "cu_pct":
            raise M01ConfigError(
                "M01 v1.1 currently supports primary_element='cu_pct' only."
            )

        enabled = overrides.get(
            "reference_grade_analysis_enabled",
            config.reference_grade_enabled_by_default,
        )
        if not isinstance(enabled, bool):
            raise M01ConfigError(
                "reference_grade_analysis_enabled must be a boolean."
            )

        ok_tolerance_m = _as_float(
            overrides.get("topography_ok_tolerance_m", config.topography_ok_tolerance_m),
            "topography_ok_tolerance_m",
        )
        review_tolerance_m = _as_float(
            overrides.get(
                "topography_review_tolerance_m",
                config.topography_review_tolerance_m,
            ),
            "topography_review_tolerance_m",
        )
        if not 0.0 <= ok_tolerance_m < review_tolerance_m:
            raise M01ConfigError(
                "Topography tolerances must satisfy 0 <= ok_tolerance_m "
                "< review_tolerance_m."
            )

        reference_grade: float | None = None
        if enabled:
            reference_grade = _as_float(
                overrides.get("reference_grade", config.default_reference_grade),
                "reference_grade",
            )
            if not 0.0 <= reference_grade <= 100.0:
                raise M01ConfigError(
                    "reference_grade must be between 0 and 100 percent."
                )

        return cls(
            primary_element=primary_element,
            reference_grade_analysis_enabled=enabled,
            reference_grade=reference_grade,
            ok_tolerance_m=ok_tolerance_m,
            review_tolerance_m=review_tolerance_m,
            interactive=(
                str(overrides.get("execution_mode", "DIRECT")).strip().upper()
                == "INTERACTIVE"
            ),
        )

    def to_context_settings(self) -> dict[str, Any]:
        """Return the normalized settings persisted in the run contract."""

        return {
            "execution_mode": "INTERACTIVE" if self.interactive else "DIRECT",
            "primary_element": self.primary_element,
            "reference_grade_analysis_enabled": (
                self.reference_grade_analysis_enabled
            ),
            "reference_grade": self.reference_grade,
            "topography_ok_tolerance_m": self.ok_tolerance_m,
            "topography_review_tolerance_m": self.review_tolerance_m,
        }

    def analysis_payload(self) -> dict[str, Any]:
        """Return the user-facing analytical choices for reports and metrics."""

        return {
            "primary_element": self.primary_element,
            "reference_grade_analysis_enabled": (
                self.reference_grade_analysis_enabled
            ),
            "reference_grade": self.reference_grade,
        }


def _as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise M01ConfigError(f"{field_name} must be numeric.") from exc
