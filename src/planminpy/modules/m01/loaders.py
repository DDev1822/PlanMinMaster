"""Read-only loaders and source-integrity inventory for M01."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from planminpy.core.context import ModuleContext
from planminpy.core.contracts import PlanMinPyError


class M01DataError(PlanMinPyError):
    """Raised when an input file cannot satisfy its exact source schema."""


SCHEMAS: dict[str, tuple[str, ...]] = {
    "collar.csv": (
        "hole_id", "dataset_id", "project_id", "campaign_id", "x", "y", "z",
        "azimuth_deg", "dip_deg", "final_depth_m",
    ),
    "survey.csv": (
        "hole_id", "dataset_id", "project_id", "campaign_id", "depth_m",
        "azimuth_deg", "dip_deg",
    ),
    "assay.csv": (
        "sample_id", "hole_id", "dataset_id", "project_id", "campaign_id",
        "from_m", "to_m", "length_m", "cu_pct", "mo_pct", "au_gt",
    ),
    "lithology.csv": (
        "hole_id", "dataset_id", "project_id", "campaign_id", "from_m", "to_m",
        "length_m", "lith_code",
    ),
    "alteration.csv": (
        "hole_id", "dataset_id", "project_id", "campaign_id", "from_m", "to_m",
        "length_m", "alteration_code", "alteration_intensity",
    ),
    "density.csv": (
        "density_sample_id", "hole_id", "dataset_id", "project_id", "campaign_id",
        "from_m", "to_m", "length_m", "density_t_m3",
    ),
}


@dataclass(frozen=True)
class TableData:
    name: str
    path: Path
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ReleaseData:
    tables: Mapping[str, TableData]
    topography_path: Path
    topography_source: str
    source_hashes: Mapping[str, str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_label(context: ModuleContext, path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(context.project_root):
        return resolved.relative_to(context.project_root).as_posix()
    if resolved.parent == context.dataset_path:
        return f"exploration_data/{resolved.name}"
    if resolved == context.topography_path:
        return f"topography/{resolved.name}"
    return f"external_source/{resolved.name}"


def load_table(path: Path, expected_columns: tuple[str, ...]) -> TableData:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            actual = tuple(reader.fieldnames or ())
            if actual != expected_columns:
                raise M01DataError(
                    f"schema mismatch for {path.name}: expected {expected_columns}, got {actual}"
                )
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise M01DataError(f"cannot read source table: {path}") from exc
    return TableData(path.name, path, expected_columns, rows)


def load_release(context: ModuleContext) -> ReleaseData:
    tables = {
        name: load_table(context.dataset_path / name, columns)
        for name, columns in SCHEMAS.items()
    }
    topography_path = context.topography_path
    if topography_path is None or not topography_path.is_file():
        raise M01DataError(f"selected topography source is missing: {topography_path}")
    source_paths = [topography_path] + sorted(
        item for item in context.dataset_path.iterdir() if item.is_file()
    )
    hashes = {
        source_label(context, path): sha256_file(path)
        for path in source_paths
    }
    return ReleaseData(
        tables=tables,
        topography_path=topography_path,
        topography_source=source_label(context, topography_path),
        source_hashes=hashes,
    )


def finite_float(value: str, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise M01DataError(f"{field_name} must be numeric: {value!r}") from exc
    return parsed
