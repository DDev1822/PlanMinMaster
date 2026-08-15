"""M01 structural, identity, survey and interval validation rules."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

from planminpy.core.context import ModuleContext
from planminpy.modules.m01.config import M01Config
from planminpy.modules.m01.geometry import minimum_curvature_increment
from planminpy.modules.m01.loaders import ReleaseData, TableData, source_label
from planminpy.modules.m01.models import Finding, Severity


def _error(
    rule_id: str,
    message: str,
    **kwargs: Any,
) -> Finding:
    return Finding.create(
        rule_id,
        Severity.ERROR,
        message,
        blocking=True,
        **kwargs,
    )


def validate_source_hashes(
    context: ModuleContext,
    release: ReleaseData,
) -> list[Finding]:
    findings: list[Finding] = []
    manifest_hashes = context.manifest.get("file_sha256")
    if not isinstance(manifest_hashes, dict):
        return [
            _error(
                "SOURCE_MANIFEST_HASH_MAP_MISSING",
                "release manifest does not contain a valid file_sha256 map",
                table="release_manifest.json",
                expected_condition="file_sha256 object is required",
                source=context.manifest_path.relative_to(context.project_root).as_posix(),
            )
        ]
    for filename, expected in sorted(manifest_hashes.items()):
        relative = source_label(context, context.dataset_path / filename)
        actual = release.source_hashes.get(relative)
        if actual is None or actual.lower() != str(expected).lower():
            findings.append(
                _error(
                    "SOURCE_HASH_MISMATCH",
                    f"source hash does not match release manifest for {filename}",
                    table=filename,
                    field="sha256",
                    observed_value=actual,
                    expected_condition=str(expected).lower(),
                    source=relative,
                    provenance_kind="CALCULATED",
                )
            )
    return findings


def validate_collars(
    table: TableData,
    context: ModuleContext,
    config: M01Config,
) -> list[Finding]:
    findings: list[Finding] = []
    seen_holes: set[str] = set()
    seen_xy: dict[tuple[float, float], str] = {}
    aliases = config.campaign_aliases
    manifest_campaigns = context.manifest.get("campaigns", [])
    unknown_manifest = sorted(set(manifest_campaigns) - set(aliases))
    for alias in unknown_manifest:
        findings.append(
            _error(
                "CAMPAIGN_ALIAS_UNDECLARED",
                f"manifest campaign alias is not configured: {alias}",
                table="release_manifest.json",
                field="campaigns",
                observed_value=alias,
                expected_condition="campaign alias must be explicitly configured",
                provenance_kind="OBSERVED",
            )
        )

    for row_number, row in enumerate(table.rows, start=2):
        hole_id = row["hole_id"]
        if hole_id in seen_holes:
            findings.append(
                _error(
                    "COLLAR_DUPLICATE_HOLE_ID",
                    f"duplicate collar hole_id: {hole_id}",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    field="hole_id",
                    observed_value=hole_id,
                    expected_condition="hole_id must be unique",
                    source=table.path.name,
                )
            )
        seen_holes.add(hole_id)
        for field, expected in (
            ("project_id", context.project_id),
            ("dataset_id", context.dataset_id),
        ):
            if row[field] != expected:
                findings.append(
                    _error(
                        "COLLAR_IDENTITY_MISMATCH",
                        f"collar {field} does not match canonical identity",
                        table=table.name,
                        row_number=row_number,
                        hole_id=hole_id,
                        field=field,
                        observed_value=row[field],
                        expected_condition=expected,
                        source=table.path.name,
                    )
                )
        numeric: dict[str, float] = {}
        for field in ("x", "y", "z", "azimuth_deg", "dip_deg", "final_depth_m"):
            try:
                value = float(row[field])
            except ValueError:
                value = math.nan
            numeric[field] = value
            if not math.isfinite(value):
                findings.append(
                    _error(
                        "COLLAR_NONFINITE_VALUE",
                        f"collar {field} must be finite",
                        table=table.name,
                        row_number=row_number,
                        hole_id=hole_id,
                        field=field,
                        observed_value=row[field],
                        expected_condition="finite numeric value",
                        source=table.path.name,
                    )
                )
        if math.isfinite(numeric["final_depth_m"]) and numeric["final_depth_m"] <= 0:
            findings.append(
                _error(
                    "COLLAR_INVALID_FINAL_DEPTH",
                    "final depth must be greater than zero",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    field="final_depth_m",
                    observed_value=numeric["final_depth_m"],
                    expected_condition="> 0 m",
                    source=table.path.name,
                )
            )
        if math.isfinite(numeric["azimuth_deg"]) and not (
            0.0 <= numeric["azimuth_deg"] < 360.0
        ):
            findings.append(
                _error(
                    "COLLAR_INVALID_AZIMUTH",
                    "collar azimuth must be in [0,360)",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    field="azimuth_deg",
                    observed_value=numeric["azimuth_deg"],
                    expected_condition="0 <= azimuth < 360 degrees",
                    source=table.path.name,
                )
            )
        if math.isfinite(numeric["dip_deg"]) and not (-90.0 <= numeric["dip_deg"] <= 0.0):
            findings.append(
                _error(
                    "COLLAR_INVALID_DIP",
                    "collar dip must be in [-90,0] under negative-down convention",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    field="dip_deg",
                    observed_value=numeric["dip_deg"],
                    expected_condition="-90 <= dip <= 0 degrees",
                    source=table.path.name,
                )
            )
        if math.isfinite(numeric["x"]) and math.isfinite(numeric["y"]):
            xy = (numeric["x"], numeric["y"])
            if xy in seen_xy:
                findings.append(
                    Finding.create(
                        "COLLAR_DUPLICATE_XY",
                        Severity.WARNING,
                        f"collar XY duplicates hole {seen_xy[xy]}",
                        requires_review=True,
                        table=table.name,
                        row_number=row_number,
                        hole_id=hole_id,
                        field="x,y",
                        observed_value=list(xy),
                        expected_condition="unique XY unless approved twin/wedge collar",
                        source=table.path.name,
                    )
                )
            seen_xy[xy] = hole_id
        parts = hole_id.split("-")
        alias = parts[1] if len(parts) >= 3 else None
        expected_campaign = aliases.get(alias) if alias is not None else None
        if expected_campaign is None or row["campaign_id"] != expected_campaign:
            findings.append(
                _error(
                    "COLLAR_CAMPAIGN_ALIAS_MISMATCH",
                    "collar campaign does not match its approved hole-ID alias",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    field="campaign_id",
                    observed_value={"alias": alias, "campaign_id": row["campaign_id"]},
                    expected_condition=str(expected_campaign),
                    source=table.path.name,
                    provenance_kind="INFERRED",
                )
            )
    return findings


def validate_surveys(
    table: TableData,
    collars: Mapping[str, Mapping[str, str]],
    context: ModuleContext,
    config: M01Config,
) -> list[Finding]:
    findings: list[Finding] = []
    grouped: defaultdict[str, list[tuple[int, Mapping[str, str]]]] = defaultdict(list)
    seen_stations: set[tuple[str, float]] = set()
    for row_number, row in enumerate(table.rows, start=2):
        hole_id = row["hole_id"]
        collar = collars.get(hole_id)
        if collar is None:
            findings.append(
                _error(
                    "SURVEY_ORPHAN_HOLE",
                    "survey references an unknown collar hole",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    expected_condition="hole_id exists in collar.csv",
                    source=table.path.name,
                )
            )
            continue
        try:
            md = float(row["depth_m"])
            azimuth = float(row["azimuth_deg"])
            dip = float(row["dip_deg"])
        except ValueError:
            findings.append(
                _error(
                    "SURVEY_NONNUMERIC",
                    "survey MD, azimuth and dip must be numeric",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    expected_condition="finite numeric survey values",
                    source=table.path.name,
                )
            )
            continue
        grouped[hole_id].append((row_number, row))
        key = (hole_id, md)
        if key in seen_stations:
            findings.append(
                _error(
                    "SURVEY_DUPLICATE_MD",
                    "duplicate survey station for hole and MD",
                    table=table.name,
                    row_number=row_number,
                    hole_id=hole_id,
                    field="depth_m",
                    observed_value=md,
                    expected_condition="unique (hole_id, depth_m)",
                    source=table.path.name,
                )
            )
        seen_stations.add(key)
        if not math.isfinite(md) or md < 0:
            findings.append(_error("SURVEY_INVALID_MD", "survey MD must be finite and non-negative", table=table.name, row_number=row_number, hole_id=hole_id, field="depth_m", observed_value=md, expected_condition=">= 0 m", source=table.path.name))
        if math.isfinite(md) and md > float(collar["final_depth_m"]) + config.interval_tolerance_m:
            findings.append(_error("SURVEY_BEYOND_FINAL_DEPTH", "survey station exceeds collar final depth", table=table.name, row_number=row_number, hole_id=hole_id, field="depth_m", observed_value=md, expected_condition=f"<= {collar['final_depth_m']} m", source=table.path.name))
        if not math.isfinite(azimuth) or not (0.0 <= azimuth < 360.0):
            findings.append(_error("SURVEY_INVALID_AZIMUTH", "survey azimuth must be in [0,360)", table=table.name, row_number=row_number, hole_id=hole_id, field="azimuth_deg", observed_value=azimuth, expected_condition="0 <= azimuth < 360 degrees", source=table.path.name))
        if not math.isfinite(dip) or not (-90.0 <= dip <= 0.0):
            findings.append(_error("SURVEY_INVALID_DIP", "survey dip must be in [-90,0]", table=table.name, row_number=row_number, hole_id=hole_id, field="dip_deg", observed_value=dip, expected_condition="-90 <= dip <= 0 degrees", source=table.path.name))
        for field, expected in (("project_id", context.project_id), ("dataset_id", context.dataset_id), ("campaign_id", collar["campaign_id"])):
            if row[field] != expected:
                findings.append(_error("SURVEY_IDENTITY_MISMATCH", f"survey {field} does not match collar/context", table=table.name, row_number=row_number, hole_id=hole_id, field=field, observed_value=row[field], expected_condition=expected, source=table.path.name))

    survey_config = config.values["survey"]
    for hole_id, collar in sorted(collars.items()):
        items = grouped.get(hole_id, [])
        if not items:
            findings.append(_error("SURVEY_MISSING_HOLE", "hole has no survey observations", table=table.name, hole_id=hole_id, expected_condition="at least one survey station", source=table.path.name))
            continue
        ordered = sorted(items, key=lambda item: float(item[1]["depth_m"]))
        first = ordered[0][1]
        first_md = float(first["depth_m"])
        if first_md > config.interval_tolerance_m:
            findings.append(Finding.create("SURVEY_MISSING_MD0", Severity.WARNING, "MD0 station will be seeded from collar orientation", requires_review=True, table=table.name, hole_id=hole_id, field="depth_m", observed_value=first_md, expected_condition="first station at 0 m", source=table.path.name, provenance_kind="ASSUMED"))
        else:
            if abs(float(first["azimuth_deg"]) - float(collar["azimuth_deg"])) > config.interval_tolerance_m or abs(float(first["dip_deg"]) - float(collar["dip_deg"])) > config.interval_tolerance_m:
                findings.append(Finding.create("SURVEY_COLLAR_MD0_DISAGREEMENT", Severity.WARNING, "survey orientation at MD0 differs from collar orientation", requires_review=True, table=table.name, hole_id=hole_id, observed_value={"collar_azimuth": collar["azimuth_deg"], "collar_dip": collar["dip_deg"], "survey_azimuth": first["azimuth_deg"], "survey_dip": first["dip_deg"]}, expected_condition="collar and survey MD0 orientations agree", source=table.path.name))
        for (_, previous), (_, current) in zip(ordered, ordered[1:]):
            spacing = float(current["depth_m"]) - float(previous["depth_m"])
            if spacing > float(survey_config["station_spacing_review_m"]):
                findings.append(Finding.create("SURVEY_STATION_SPACING_REVIEW", Severity.WARNING, "survey station spacing exceeds review threshold", requires_review=True, table=table.name, hole_id=hole_id, field="depth_m", observed_value=spacing, expected_condition=f"<= {survey_config['station_spacing_review_m']} m", source=table.path.name, provenance_kind="CALCULATED"))
            elif spacing > float(survey_config["station_spacing_warning_m"]):
                findings.append(Finding.create("SURVEY_STATION_SPACING_WARNING", Severity.WARNING, "survey station spacing exceeds warning threshold", table=table.name, hole_id=hole_id, field="depth_m", observed_value=spacing, expected_condition=f"<= {survey_config['station_spacing_warning_m']} m", source=table.path.name, provenance_kind="CALCULATED"))
            if spacing > 0:
                increment = minimum_curvature_increment(spacing, float(previous["azimuth_deg"]), float(previous["dip_deg"]), float(current["azimuth_deg"]), float(current["dip_deg"]), zero_dogleg_epsilon_rad=config.dogleg_epsilon_rad)
                severity = math.degrees(increment.dogleg_rad) * float(survey_config["dogleg_normalization_m"]) / spacing
                if severity > float(survey_config["dogleg_review_deg_per_normalization"]):
                    findings.append(Finding.create("SURVEY_DOGLEG_REVIEW", Severity.WARNING, "dogleg severity exceeds review threshold", requires_review=True, table=table.name, hole_id=hole_id, observed_value=severity, expected_condition=f"<= {survey_config['dogleg_review_deg_per_normalization']} deg/{survey_config['dogleg_normalization_m']}m", source=table.path.name, provenance_kind="CALCULATED"))
                elif severity > float(survey_config["dogleg_warning_deg_per_normalization"]):
                    findings.append(Finding.create("SURVEY_DOGLEG_WARNING", Severity.WARNING, "dogleg severity exceeds warning threshold", table=table.name, hole_id=hole_id, observed_value=severity, expected_condition=f"<= {survey_config['dogleg_warning_deg_per_normalization']} deg/{survey_config['dogleg_normalization_m']}m", source=table.path.name, provenance_kind="CALCULATED"))
        last_md = float(ordered[-1][1]["depth_m"])
        terminal_gap = float(collar["final_depth_m"]) - last_md
        if terminal_gap > float(survey_config["terminal_gap_review_m"]):
            findings.append(Finding.create("SURVEY_TERMINAL_GAP_REVIEW", Severity.WARNING, "terminal survey gap exceeds review threshold", requires_review=True, table=table.name, hole_id=hole_id, observed_value=terminal_gap, expected_condition=f"<= {survey_config['terminal_gap_review_m']} m", source=table.path.name, provenance_kind="CALCULATED"))
        elif terminal_gap > float(survey_config["terminal_gap_warning_m"]):
            findings.append(Finding.create("SURVEY_TERMINAL_GAP_WARNING", Severity.WARNING, "terminal survey gap exceeds warning threshold", table=table.name, hole_id=hole_id, observed_value=terminal_gap, expected_condition=f"<= {survey_config['terminal_gap_warning_m']} m", source=table.path.name, provenance_kind="CALCULATED"))
    return findings


def validate_intervals(
    table: TableData,
    collars: Mapping[str, Mapping[str, str]],
    context: ModuleContext,
    config: M01Config,
    *,
    primary_id: str | None,
    gap_kind: str,
) -> list[Finding]:
    findings: list[Finding] = []
    tolerance = config.interval_tolerance_m
    if not table.rows and table.name == "alteration.csv":
        if int(context.manifest.get("n_alteration_intervals", -1)) == 0:
            return [Finding.create("ALTERATION_NO_OBSERVATIONS", Severity.INFO, "alteration is a valid empty optional input", table=table.name, observed_value=0, expected_condition="manifest declares zero alteration intervals", source=table.path.name, provenance_kind="OBSERVED")]
    seen_ids: set[str] = set()
    seen_intervals: set[tuple[str, float, float]] = set()
    grouped: defaultdict[str, list[tuple[float, float]]] = defaultdict(list)
    for row_number, row in enumerate(table.rows, start=2):
        hole_id = row["hole_id"]
        collar = collars.get(hole_id)
        if collar is None:
            findings.append(_error("INTERVAL_ORPHAN_HOLE", "interval references unknown collar", table=table.name, row_number=row_number, hole_id=hole_id, expected_condition="hole_id exists in collar.csv", source=table.path.name))
            continue
        if primary_id is not None:
            record_id = row[primary_id]
            if record_id in seen_ids:
                findings.append(_error("INTERVAL_DUPLICATE_PRIMARY_ID", "duplicate interval primary identifier", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, field=primary_id, observed_value=record_id, expected_condition="unique primary identifier", source=table.path.name))
            seen_ids.add(record_id)
        else:
            record_id = None
        try:
            from_m = float(row["from_m"])
            to_m = float(row["to_m"])
            length_m = float(row["length_m"])
        except ValueError:
            findings.append(_error("INTERVAL_NONNUMERIC", "interval boundaries and length must be numeric", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, expected_condition="finite numeric FROM, TO and length", source=table.path.name))
            continue
        if not all(math.isfinite(value) for value in (from_m, to_m, length_m)):
            findings.append(_error("INTERVAL_NONFINITE", "interval boundaries and length must be finite", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, observed_value=[from_m, to_m, length_m], expected_condition="finite values", source=table.path.name))
            continue
        if from_m < 0 or to_m < 0:
            findings.append(_error("INTERVAL_NEGATIVE_DEPTH", "interval contains a negative depth", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, observed_value=[from_m, to_m], expected_condition="FROM and TO >= 0", source=table.path.name))
        if from_m >= to_m:
            findings.append(_error("INTERVAL_INVALID_ORDER", "interval must satisfy FROM < TO", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, observed_value=[from_m, to_m], expected_condition="FROM < TO", source=table.path.name))
        if length_m <= 0:
            findings.append(_error("INTERVAL_ZERO_LENGTH", "interval length must be greater than zero", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, field="length_m", observed_value=length_m, expected_condition="> 0 m", source=table.path.name))
        if abs((to_m - from_m) - length_m) > tolerance:
            findings.append(_error("INTERVAL_LENGTH_MISMATCH", "interval length differs from TO-FROM", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, observed_value={"from_m": from_m, "to_m": to_m, "length_m": length_m}, expected_condition=f"absolute difference <= {tolerance} m", source=table.path.name, provenance_kind="CALCULATED"))
        if to_m > float(collar["final_depth_m"]) + tolerance:
            findings.append(_error("INTERVAL_BEYOND_FINAL_DEPTH", "interval extends beyond collar final depth", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, observed_value=to_m, expected_condition=f"<= {collar['final_depth_m']} m", source=table.path.name))
        for field, expected in (("project_id", context.project_id), ("dataset_id", context.dataset_id), ("campaign_id", collar["campaign_id"])):
            if row[field] != expected:
                findings.append(_error("INTERVAL_IDENTITY_MISMATCH", f"interval {field} does not match collar/context", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, field=field, observed_value=row[field], expected_condition=expected, source=table.path.name))
        key = (hole_id, from_m, to_m)
        if key in seen_intervals:
            findings.append(_error("INTERVAL_DUPLICATE_EXACT", "duplicate exact interval", table=table.name, row_number=row_number, hole_id=hole_id, record_id=record_id, observed_value=[from_m, to_m], expected_condition="unique (hole_id,FROM,TO)", source=table.path.name))
        seen_intervals.add(key)
        grouped[hole_id].append((from_m, to_m))

    for hole_id, intervals in sorted(grouped.items()):
        ordered = sorted(intervals)
        gaps: list[float] = []
        if ordered and ordered[0][0] > tolerance:
            gaps.append(ordered[0][0])
        previous_to = ordered[0][1] if ordered else 0.0
        for from_m, to_m in ordered[1:]:
            if from_m < previous_to - tolerance:
                findings.append(_error("INTERVAL_OVERLAP", "intervals overlap within the same table and hole", table=table.name, hole_id=hole_id, observed_value=previous_to - from_m, expected_condition="non-overlapping intervals", source=table.path.name, provenance_kind="CALCULATED"))
            elif from_m > previous_to + tolerance:
                gaps.append(from_m - previous_to)
            previous_to = max(previous_to, to_m)
        final_depth = float(collars[hole_id]["final_depth_m"])
        if previous_to < final_depth - tolerance:
            gaps.append(final_depth - previous_to)
        if gaps:
            severity = Severity.WARNING if gap_kind == "GEOLOGICAL_GAP" else Severity.INFO
            findings.append(Finding.create(f"INTERVAL_{gap_kind}", severity, f"{table.name} contains {gap_kind.lower().replace('_', ' ')}", requires_review=gap_kind == "GEOLOGICAL_GAP", table=table.name, hole_id=hole_id, observed_value={"gap_count": len(gaps), "gap_metres": sum(gaps)}, expected_condition="gap semantics are table-specific", source=table.path.name, provenance_kind="CALCULATED"))
    return findings


def validate_assay_values(
    table: TableData,
    classifications: Mapping[str, str],
) -> list[Finding]:
    findings: list[Finding] = []
    for field, classification in classifications.items():
        if classification == "CONSTANT_ZERO":
            findings.append(Finding.create("ASSAY_CONSTANT_ZERO", Severity.WARNING, f"analytical field {field} is constant zero; no detection-limit meaning is inferred", table=table.name, field=field, observed_value=classification, expected_condition="analytical classification is reported literally", source=table.path.name, provenance_kind="CALCULATED"))
        elif classification in {"EMPTY", "CONSTANT_NONZERO"}:
            findings.append(Finding.create("ASSAY_NONVARIABLE_FIELD_REVIEW", Severity.WARNING, f"analytical field {field} is {classification}", requires_review=True, table=table.name, field=field, observed_value=classification, expected_condition="analytical usability requires review", source=table.path.name, provenance_kind="CALCULATED"))
    for row_number, row in enumerate(table.rows, start=2):
        for field in classifications:
            raw = row[field].strip()
            try:
                value = float(raw)
            except ValueError:
                value = math.nan
            if not math.isfinite(value):
                findings.append(_error("ASSAY_INVALID_VALUE", "assay value must be finite", table=table.name, row_number=row_number, hole_id=row["hole_id"], record_id=row["sample_id"], field=field, observed_value=raw, expected_condition="finite numeric assay", source=table.path.name))
            elif value < 0:
                findings.append(_error("ASSAY_NEGATIVE_VALUE", "negative assay value is structurally invalid", table=table.name, row_number=row_number, hole_id=row["hole_id"], record_id=row["sample_id"], field=field, observed_value=value, expected_condition=">= 0", source=table.path.name))
    return findings


def validate_density_values(
    table: TableData,
    config: M01Config,
) -> list[Finding]:
    findings: list[Finding] = []
    minimum = float(config.values["density"]["review_min_t_m3"])
    maximum = float(config.values["density"]["review_max_t_m3"])
    for row_number, row in enumerate(table.rows, start=2):
        try:
            value = float(row["density_t_m3"])
        except ValueError:
            value = math.nan
        if not math.isfinite(value) or value <= 0:
            findings.append(_error("DENSITY_INVALID_VALUE", "density must be finite and greater than zero", table=table.name, row_number=row_number, hole_id=row["hole_id"], record_id=row["density_sample_id"], field="density_t_m3", observed_value=row["density_t_m3"], expected_condition="> 0 t/m3", source=table.path.name))
        elif value < minimum or value > maximum:
            findings.append(Finding.create("DENSITY_PHYSICAL_REVIEW", Severity.WARNING, "density lies outside the configured diagnostic review range", requires_review=True, table=table.name, row_number=row_number, hole_id=row["hole_id"], record_id=row["density_sample_id"], field="density_t_m3", observed_value=value, expected_condition=f"{minimum} <= density <= {maximum} t/m3", source=table.path.name, provenance_kind="INFERRED"))
    return findings
