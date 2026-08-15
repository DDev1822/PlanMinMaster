"""Deterministic Datamine staging and optional official DmFile COM export."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import uuid
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from planminpy.core.artifacts import ArtifactWorkspace
from planminpy.core.context import ModuleContext
from planminpy.core.contracts import PlanMinPyError
from planminpy.modules.m01.artifacts import (
    TOPOGRAPHY_TIN_TRIANGLE_FIELDS,
    TOPOGRAPHY_TIN_VERTEX_FIELDS,
)
from planminpy.modules.m01.config import load_config
from planminpy.modules.m01.geometry import evaluate_trajectory_at_md
from planminpy.modules.m01.module import MODULE_ID, MODULE_VERSION
from planminpy.modules.m01.topography import TopographySurface


DRILLHOLE_FIELDS = (
    "BHID", "FROM", "TO", "LENGTH", "X", "Y", "Z", "A0", "B0", "CU", "MO", "AU",
)
PT_FIELDS = ("PID", "XP", "YP", "ZP")
TR_FIELDS = ("TRIANGLE", "PID1", "PID2", "PID3")


class DatamineExportError(PlanMinPyError):
    """Raised when staging cannot be generated from validated M01 artifacts."""


@dataclass(frozen=True)
class DatamineBackendInfo:
    available: bool
    status: str
    name: str | None
    version: str | None


class DatamineBackend(Protocol):
    info: DatamineBackendInfo

    def write_static_drillholes(self, staging_csv: Path, target: Path) -> bool: ...

    def write_wireframe(
        self,
        pt_staging_csv: Path,
        tr_staging_csv: Path,
        pt_target: Path,
        tr_target: Path,
    ) -> bool: ...


@dataclass(frozen=True)
class DatamineExportResult:
    export_type: str
    backend_status: str
    backend_name: str | None
    backend_version: str | None
    staging_paths: tuple[Path, ...]
    manifest_path: Path
    native_paths: tuple[Path, ...]
    native_created: bool
    record_count: int | None = None
    point_count: int | None = None
    triangle_count: int | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, expected_fields: tuple[str, ...]) -> Iterable[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            actual = tuple(reader.fieldnames or ())
            if actual != expected_fields:
                raise DatamineExportError(
                    f"Unexpected M01 artifact schema for {path.name}: {actual}"
                )
            for row in reader:
                yield dict(row)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DatamineExportError(f"Cannot read M01 artifact: {path}") from exc


class _UnavailableBackend:
    def __init__(self, info: DatamineBackendInfo) -> None:
        self.info = info

    def write_static_drillholes(self, staging_csv: Path, target: Path) -> bool:
        return False

    def write_wireframe(
        self,
        pt_staging_csv: Path,
        tr_staging_csv: Path,
        pt_target: Path,
        tr_target: Path,
    ) -> bool:
        return False


class PowerShellDmFileBackend:
    """Use registered official DmFile COM classes through installed PowerShell."""

    def __init__(self, executable: str, info: DatamineBackendInfo) -> None:
        self.executable = executable
        self.info = info

    @staticmethod
    def _quote(value: Path) -> str:
        return "'" + str(value.resolve()).replace("'", "''") + "'"

    def _run_script(self, script: str) -> bool:
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        try:
            completed = subprocess.run(
                [self.executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False
        return completed.returncode == 0

    def _write_table(self, staging_csv: Path, target: Path, kind: str) -> bool:
        source = self._quote(staging_csv)
        destination = self._quote(target)
        if kind == "STATIC_DRILLHOLES":
            schema_script = """
$schema.AddStringColumn('BHID', 64, '', 0)
foreach ($field in @('FROM','TO','LENGTH','X','Y','Z','A0','B0','CU','MO','AU')) {
    $schema.AddNumericColumn($field, 0.0, 0)
}
"""
            assignment_script = """
$table.SetColumnString(1, [string]$row.BHID)
$names = @('FROM','TO','LENGTH','X','Y','Z','A0','B0','CU','MO','AU')
for ($index = 0; $index -lt $names.Count; $index++) {
    $value = [double]::Parse([string]$row.($names[$index]), $culture)
    $table.SetColumnDouble($index + 2, $value)
}
"""
        elif kind == "WIREFRAME_POINTS":
            schema_script = "$schema.CreateWfPointFile()"
            assignment_script = """
$table.SetColumnDouble(1, [double]::Parse([string]$row.XP, $culture))
$table.SetColumnDouble(2, [double]::Parse([string]$row.YP, $culture))
$table.SetColumnDouble(3, [double]::Parse([string]$row.ZP, $culture))
$table.SetColumnDouble(4, [double]::Parse([string]$row.PID, $culture))
"""
        elif kind == "WIREFRAME_TRIANGLES":
            schema_script = "$schema.CreateWfTriangleFile()"
            assignment_script = """
$table.SetColumnDouble(1, [double]::Parse([string]$row.PID1, $culture))
$table.SetColumnDouble(2, [double]::Parse([string]$row.PID2, $culture))
$table.SetColumnDouble(3, [double]::Parse([string]$row.PID3, $culture))
$table.SetColumnDouble(4, [double]::Parse([string]$row.TRIANGLE, $culture))
"""
        else:
            return False
        script = f"""
$ErrorActionPreference = 'Stop'
$culture = [Globalization.CultureInfo]::InvariantCulture
$schema = New-Object -ComObject DmFile.DmSchema
$table = New-Object -ComObject DmFile.DmTable
$opened = $false
try {{
{schema_script}
    $schema.DoublePrecision = $true
    $table.Create({destination}, $schema)
    $opened = $true
    Import-Csv -LiteralPath {source} | ForEach-Object {{
        $row = $_
        $table.AddRow()
{assignment_script}
    }}
    $table.FlushChanges()
    $table.Close()
    $opened = $false
}} finally {{
    if ($opened) {{ try {{ $table.Close() }} catch {{}} }}
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($table) | Out-Null
    [Runtime.InteropServices.Marshal]::FinalReleaseComObject($schema) | Out-Null
}}
"""
        return self._run_script(script) and target.is_file() and target.stat().st_size > 0

    @staticmethod
    def _temporary_target(target: Path) -> Path:
        return target.with_name(f".{target.stem}.{uuid.uuid4().hex}.dm")

    def write_static_drillholes(self, staging_csv: Path, target: Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._temporary_target(target)
        try:
            if not self._write_table(staging_csv, temporary, "STATIC_DRILLHOLES"):
                return False
            os.replace(temporary, target)
            return target.is_file() and target.stat().st_size > 0
        finally:
            temporary.unlink(missing_ok=True)

    def write_wireframe(
        self,
        pt_staging_csv: Path,
        tr_staging_csv: Path,
        pt_target: Path,
        tr_target: Path,
    ) -> bool:
        pt_target.parent.mkdir(parents=True, exist_ok=True)
        temporary_pt = self._temporary_target(pt_target)
        temporary_tr = self._temporary_target(tr_target)
        try:
            if not self._write_table(pt_staging_csv, temporary_pt, "WIREFRAME_POINTS"):
                return False
            if not self._write_table(tr_staging_csv, temporary_tr, "WIREFRAME_TRIANGLES"):
                return False
            os.replace(temporary_pt, pt_target)
            os.replace(temporary_tr, tr_target)
            return all(path.is_file() and path.stat().st_size > 0 for path in (pt_target, tr_target))
        finally:
            temporary_pt.unlink(missing_ok=True)
            temporary_tr.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def detect_datamine_backend() -> DatamineBackend:
    """Detect registered DmFile components and installed Datamine products."""

    executable = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if executable is None:
        return _UnavailableBackend(
            DatamineBackendInfo(False, "NOT_AVAILABLE", None, None)
        )
    script = """
$ErrorActionPreference = 'Stop'
$table = [type]::GetTypeFromProgID('DmFile.DmTable')
$schema = [type]::GetTypeFromProgID('DmFile.DmSchema')
$products = @(
    'Registry::HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',
    'Registry::HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*'
) | ForEach-Object { Get-ItemProperty -Path $_ -ErrorAction SilentlyContinue } |
    Where-Object { $_.Publisher -like 'Datamine*' -and $_.DisplayName } |
    Sort-Object DisplayName, DisplayVersion -Unique
[pscustomobject]@{
    available = ($null -ne $table -and $null -ne $schema)
    name = (($products | ForEach-Object DisplayName) -join '; ')
    version = (($products | ForEach-Object DisplayVersion) -join '; ')
} | ConvertTo-Json -Compress
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        completed = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        payload = json.loads(completed.stdout.strip()) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        payload = {}
    if not bool(payload.get("available")):
        return _UnavailableBackend(
            DatamineBackendInfo(False, "NOT_AVAILABLE", None, None)
        )
    info = DatamineBackendInfo(
        True,
        "AVAILABLE",
        str(payload.get("name") or "Datamine DmFile COM"),
        str(payload.get("version") or "REGISTERED_VERSION_NOT_REPORTED"),
    )
    return PowerShellDmFileBackend(executable, info)


def _native_status(backend: DatamineBackend, created: bool) -> str:
    if not backend.info.available:
        return "NOT_AVAILABLE"
    return "SUCCESS" if created else "ERROR"


def _relative_output(context: ModuleContext, path: Path) -> str:
    return path.resolve().relative_to(context.output_root.resolve()).as_posix()


def export_static_drillholes(
    context: ModuleContext,
    *,
    backend: DatamineBackend | None = None,
) -> DatamineExportResult:
    """Build Datamine-ready static drillholes from frozen M01 geometry artifacts."""

    workspace = ArtifactWorkspace(context, MODULE_ID)
    trajectory_path = workspace.resolve("drillhole_trajectory.csv")
    assay_xyz_path = workspace.resolve("assay_xyz.csv")
    if not trajectory_path.is_file() or not assay_xyz_path.is_file():
        raise DatamineExportError("Run M01 before generating the Datamine export.")
    trajectories: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    with trajectory_path.open(encoding="utf-8", newline="") as handle:
        trajectory_fields = tuple(next(csv.reader(handle)))
    for row in _read_csv(trajectory_path, trajectory_fields):
        trajectories[row["hole_id"]].append(row)
    with assay_xyz_path.open(encoding="utf-8", newline="") as handle:
        assay_fields = tuple(next(csv.reader(handle)))
    config = load_config(context.project_root)
    rows: list[dict[str, Any]] = []
    for assay in _read_csv(assay_xyz_path, assay_fields):
        hole_id = assay["hole_id"]
        if hole_id not in trajectories:
            raise DatamineExportError(f"Missing M01 trajectory for drillhole {hole_id}")
        midpoint = evaluate_trajectory_at_md(
            trajectories[hole_id],
            float(assay["mid_m"]),
            zero_dogleg_epsilon_rad=config.dogleg_epsilon_rad,
            md_tolerance_m=config.interval_tolerance_m,
        )
        values = {
            "BHID": hole_id,
            "FROM": float(assay["from_m"]),
            "TO": float(assay["to_m"]),
            "LENGTH": float(assay["length_m"]),
            "X": float(assay["x_mid"]),
            "Y": float(assay["y_mid"]),
            "Z": float(assay["z_mid"]),
            "A0": midpoint.azimuth_deg,
            "B0": -midpoint.dip_deg,
            "CU": float(assay["cu_pct"]),
            "MO": float(assay["mo_pct"]),
            "AU": float(assay["au_gt"]),
        }
        if not all(
            isinstance(value, str) or math.isfinite(float(value))
            for value in values.values()
        ):
            raise DatamineExportError("Static drillhole staging contains non-finite values")
        rows.append(values)
    rows.sort(key=lambda row: (str(row["BHID"]), float(row["FROM"]), float(row["TO"])))
    staging_path, record_count = workspace.write_csv(
        "datamine/drillholes_m01_datamine_input.csv", DRILLHOLE_FIELDS, rows
    )
    selected_backend = backend or detect_datamine_backend()
    native_path = workspace.resolve("datamine/drillholes_m01.dm")
    native_existed = native_path.is_file()
    native_created = False
    if selected_backend.info.available:
        native_created = selected_backend.write_static_drillholes(staging_path, native_path)
        native_created = bool(
            native_created and native_path.is_file() and native_path.stat().st_size > 0
        )
        if not native_created and not native_existed:
            native_path.unlink(missing_ok=True)
    status = _native_status(selected_backend, native_created)
    source_hashes = {
        "assay_xyz.csv": _sha256(assay_xyz_path),
        "drillhole_trajectory.csv": _sha256(trajectory_path),
    }
    manifest = {
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "project_id": context.project_id,
        "dataset_id": context.dataset_id,
        "release_id": context.release_id,
        "export_type": "STATIC_DRILLHOLES",
        "record_count": record_count,
        "drillhole_count": len({str(row["BHID"]) for row in rows}),
        "field_mapping": {
            "BHID": "hole_id", "FROM": "from_m", "TO": "to_m", "LENGTH": "length_m",
            "X": "x_mid", "Y": "y_mid", "Z": "z_mid",
            "A0": "local_trajectory_azimuth_at_interval_centre",
            "B0": "datamine_dip_at_interval_centre",
            "CU": "cu_pct", "MO": "mo_pct", "AU": "au_gt",
        },
        "coordinate_convention": "LOCAL_CARTESIAN; Z_POSITIVE_UP; A0_CLOCKWISE_FROM_NORTH",
        "dip_conversion": "M01 NEGATIVE_DOWN dip_deg -> Datamine B0 POSITIVE_DOWN using B0 = -dip_deg",
        "source_artifact_hashes": source_hashes,
        "staging_csv_hash": _sha256(staging_path),
        "datamine_backend_status": status,
        "datamine_backend_name": selected_backend.info.name,
        "datamine_backend_version": selected_backend.info.version,
        "native_output_path": _relative_output(context, native_path),
        "native_output_created": native_created,
    }
    manifest_path = workspace.write_json(
        "datamine/drillholes_m01_export_manifest.json", manifest
    )
    return DatamineExportResult(
        "STATIC_DRILLHOLES",
        status,
        selected_backend.info.name,
        selected_backend.info.version,
        (staging_path,),
        manifest_path,
        (native_path,),
        native_created,
        record_count=record_count,
    )


def _validate_vertices(path: Path) -> tuple[set[int], tuple[float, ...], int]:
    indices: set[int] = set()
    x_min = y_min = z_min = math.inf
    x_max = y_max = z_max = -math.inf
    count = 0
    for row in _read_csv(path, TOPOGRAPHY_TIN_VERTEX_FIELDS):
        try:
            index = int(row["vertex_index"])
            x, y, z = float(row["x"]), float(row["y"]), float(row["z"])
        except ValueError as exc:
            raise DatamineExportError("Invalid scientific TIN vertex value") from exc
        if index < 0 or index in indices:
            raise DatamineExportError("Scientific TIN vertex indices must be unique and nonnegative")
        if not all(math.isfinite(value) for value in (x, y, z)):
            raise DatamineExportError("Scientific TIN coordinates must be finite")
        indices.add(index)
        count += 1
        x_min, x_max = min(x_min, x), max(x_max, x)
        y_min, y_max = min(y_min, y), max(y_max, y)
        z_min, z_max = min(z_min, z), max(z_max, z)
    if count == 0:
        raise DatamineExportError("PT point_count must be greater than zero")
    if indices != set(range(count)):
        raise DatamineExportError("Scientific TIN vertex indices must be contiguous from zero")
    return indices, (x_min, x_max, y_min, y_max, z_min, z_max), count


def _validate_triangles(path: Path, vertices: set[int]) -> int:
    triangle_ids: set[int] = set()
    count = 0
    for row in _read_csv(path, TOPOGRAPHY_TIN_TRIANGLE_FIELDS):
        try:
            triangle_id = int(row["triangle_index"])
            vertex_ids = tuple(int(row[f"vertex_index_{index}"]) for index in (1, 2, 3))
        except ValueError as exc:
            raise DatamineExportError("Invalid scientific TIN triangle value") from exc
        if triangle_id < 0 or triangle_id in triangle_ids:
            raise DatamineExportError("Scientific TIN triangle IDs must be unique and nonnegative")
        if len(set(vertex_ids)) != 3:
            raise DatamineExportError("Scientific TIN contains a degenerate triangle reference")
        if any(vertex_id not in vertices for vertex_id in vertex_ids):
            raise DatamineExportError("Scientific TIN contains an orphan vertex reference")
        triangle_ids.add(triangle_id)
        count += 1
    if count == 0:
        raise DatamineExportError("TR triangle_count must be greater than zero")
    if triangle_ids != set(range(count)):
        raise DatamineExportError("Scientific TIN triangle IDs must be contiguous from zero")
    return count


def _source_extents(path: Path) -> tuple[float, ...]:
    x_min = y_min = z_min = math.inf
    x_max = y_max = z_max = -math.inf
    count = 0
    for row in _read_csv(path, ("PID", "X", "Y", "Z")):
        try:
            x, y, z = float(row["X"]), float(row["Y"]), float(row["Z"])
        except ValueError as exc:
            raise DatamineExportError("Invalid source topography coordinate") from exc
        if not all(math.isfinite(value) for value in (x, y, z)):
            raise DatamineExportError("Source topography coordinates must be finite")
        count += 1
        x_min, x_max = min(x_min, x), max(x_max, x)
        y_min, y_max = min(y_min, y), max(y_max, y)
        z_min, z_max = min(z_min, z), max(z_max, z)
    if count == 0:
        raise DatamineExportError("Source topography is empty")
    return x_min, x_max, y_min, y_max, z_min, z_max


def _pt_rows(path: Path) -> Iterable[dict[str, Any]]:
    for row in _read_csv(path, TOPOGRAPHY_TIN_VERTEX_FIELDS):
        yield {
            "PID": int(row["vertex_index"]) + 1,
            "XP": float(row["x"]),
            "YP": float(row["y"]),
            "ZP": float(row["z"]),
        }


def _tr_rows(path: Path) -> Iterable[dict[str, int]]:
    for row in _read_csv(path, TOPOGRAPHY_TIN_TRIANGLE_FIELDS):
        yield {
            "TRIANGLE": int(row["triangle_index"]) + 1,
            "PID1": int(row["vertex_index_1"]) + 1,
            "PID2": int(row["vertex_index_2"]) + 1,
            "PID3": int(row["vertex_index_3"]) + 1,
        }


def export_topographic_wireframe(
    context: ModuleContext,
    *,
    backend: DatamineBackend | None = None,
) -> DatamineExportResult:
    """Export the persisted validated full-resolution M01 TIN as a PT/TR pair."""

    workspace = ArtifactWorkspace(context, MODULE_ID)
    vertices_path = workspace.resolve("topography_tin_vertices.csv")
    triangles_path = workspace.resolve("topography_tin_triangles.csv")
    if not vertices_path.is_file() or not triangles_path.is_file():
        raise DatamineExportError(
            "Full-resolution scientific TIN artifacts are unavailable; rerun M01."
        )
    vertex_indices, extents, point_count = _validate_vertices(vertices_path)
    triangle_count = _validate_triangles(triangles_path, vertex_indices)
    source_extents = _source_extents(context.topography_path)
    if any(
        not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9)
        for left, right in zip(extents, source_extents)
    ):
        raise DatamineExportError("Scientific TIN extents do not reconcile with source topography")

    pt_path, written_points = workspace.write_csv(
        "datamine/topography_m01_pt_input.csv", PT_FIELDS, _pt_rows(vertices_path)
    )
    tr_path, written_triangles = workspace.write_csv(
        "datamine/topography_m01_tr_input.csv", TR_FIELDS, _tr_rows(triangles_path)
    )
    if written_points != point_count or written_triangles != triangle_count:
        raise DatamineExportError("PT/TR staging record counts are inconsistent")

    selected_backend = backend or detect_datamine_backend()
    native_pt = workspace.resolve("datamine/topography_m01pt.dm")
    native_tr = workspace.resolve("datamine/topography_m01tr.dm")
    native_existed = (native_pt.is_file(), native_tr.is_file())
    native_created = False
    if selected_backend.info.available:
        native_created = selected_backend.write_wireframe(
            pt_path, tr_path, native_pt, native_tr
        )
        native_created = bool(
            native_created
            and all(path.is_file() and path.stat().st_size > 0 for path in (native_pt, native_tr))
        )
        if not native_created:
            for path, existed in zip((native_pt, native_tr), native_existed):
                if not existed:
                    path.unlink(missing_ok=True)
    status = _native_status(selected_backend, native_created)
    source_path = context.topography_path.resolve()
    manifest = {
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "project_id": context.project_id,
        "dataset_id": context.dataset_id,
        "release_id": context.release_id,
        "export_type": "TOPOGRAPHIC_WIREFRAME",
        "wireframe_base_name": "topography_m01",
        "points_file": "topography_m01pt.dm",
        "triangles_file": "topography_m01tr.dm",
        "point_count": point_count,
        "triangle_count": triangle_count,
        "points_schema": list(PT_FIELDS),
        "triangles_schema": list(TR_FIELDS),
        "coordinate_convention": "LOCAL_CARTESIAN; X_EASTING; Y_NORTHING; Z_POSITIVE_UP; PID_ONE_BASED",
        "source_topography_path": str(source_path.relative_to(context.project_root)),
        "source_topography_sha256": _sha256(source_path),
        "scientific_tin_method": TopographySurface.method_identifier,
        "pt_staging_sha256": _sha256(pt_path),
        "tr_staging_sha256": _sha256(tr_path),
        "coordinate_extents": {
            "x_min": extents[0], "x_max": extents[1],
            "y_min": extents[2], "y_max": extents[3],
            "z_min": extents[4], "z_max": extents[5],
        },
        "datamine_backend_status": status,
        "datamine_backend_name": selected_backend.info.name,
        "datamine_backend_version": selected_backend.info.version,
        "native_pt_created": native_created and native_pt.is_file(),
        "native_tr_created": native_created and native_tr.is_file(),
    }
    manifest_path = workspace.write_json(
        "datamine/topography_m01_wireframe_manifest.json", manifest
    )
    return DatamineExportResult(
        "TOPOGRAPHIC_WIREFRAME",
        status,
        selected_backend.info.name,
        selected_backend.info.version,
        (pt_path, tr_path),
        manifest_path,
        (native_pt, native_tr),
        native_created,
        point_count=point_count,
        triangle_count=triangle_count,
    )
