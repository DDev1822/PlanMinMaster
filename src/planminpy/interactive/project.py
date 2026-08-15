"""Read-only discovery, inspection, and confirmation of project inputs in Data/."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from planminpy.core.contracts import PlanMinPyError, validate_identifier
from planminpy.core.paths import ProjectPaths
from planminpy.interactive.contracts import ActiveProject, TerminalIO
from planminpy.modules.m01.loaders import SCHEMAS
from planminpy.modules.m01.statistics import analytical_classification


class ProjectInspectionError(PlanMinPyError):
    """Raised when selected source data cannot satisfy the current input contract."""


CORE_SOURCE_FILES = (
    "release_manifest.json",
    "collar.csv",
    "survey.csv",
    "assay.csv",
)
REQUIRED_SOURCE_FILES = tuple(SCHEMAS) + ("release_manifest.json",)
OPTIONAL_SOURCE_FILES = ("data_dictionary.csv", "README.md")
TOPOGRAPHY_COLUMNS = ("PID", "X", "Y", "Z")


@dataclass(frozen=True)
class ExplorationInspection:
    path: Path
    manifest_path: Path
    manifest: Mapping[str, Any]
    counts: Mapping[str, int]
    analytical_variables: Mapping[str, str]


@dataclass(frozen=True)
class TopographyInspection:
    path: Path
    point_count: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


def resolve_user_path(project_root: Path, value: str) -> Path:
    """Resolve a path for legacy/programmatic callers, not the standard UX."""

    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def source_detection(path: Path) -> tuple[tuple[str, bool, bool], ...]:
    return tuple(
        (name, (path / name).is_file(), True) for name in REQUIRED_SOURCE_FILES
    ) + tuple((name, (path / name).is_file(), False) for name in OPTIONAL_SOURCE_FILES)


def _read_manifest(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectInspectionError(f"Invalid release manifest: {path}") from exc
    if not isinstance(raw, dict):
        raise ProjectInspectionError("release_manifest.json must contain a JSON object")
    for field_name in ("project_id", "dataset_id", "release_id"):
        try:
            validate_identifier(field_name, raw.get(field_name))
        except PlanMinPyError as exc:
            raise ProjectInspectionError(str(exc)) from exc
    project_name = raw.get("project_name")
    if project_name is not None and (
        not isinstance(project_name, str) or not project_name.strip()
    ):
        raise ProjectInspectionError("manifest project_name must be a non-empty string")
    return MappingProxyType(dict(raw))


def inspect_exploration_directory(path: Path) -> ExplorationInspection:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ProjectInspectionError(f"Exploration data directory does not exist: {resolved}")
    missing = [
        name
        for name, present, required in source_detection(resolved)
        if required and not present
    ]
    if missing:
        raise ProjectInspectionError(
            "Missing required exploration inputs: " + ", ".join(missing)
        )

    manifest_path = resolved / "release_manifest.json"
    manifest = _read_manifest(manifest_path)
    counts: dict[str, int] = {}
    analytical_values = {"cu_pct": [], "mo_pct": [], "au_gt": []}
    for name, expected_columns in SCHEMAS.items():
        path_for_table = resolved / name
        try:
            with path_for_table.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                actual_columns = tuple(reader.fieldnames or ())
                if actual_columns != expected_columns:
                    raise ProjectInspectionError(
                        f"Schema mismatch for {name}: expected {expected_columns}, got {actual_columns}"
                    )
                count = 0
                for row in reader:
                    count += 1
                    if name == "assay.csv":
                        for field_name in analytical_values:
                            raw = (row.get(field_name) or "").strip()
                            if not raw:
                                continue
                            try:
                                value = float(raw)
                            except ValueError:
                                continue
                            if math.isfinite(value):
                                analytical_values[field_name].append(value)
                counts[name] = count
        except (OSError, UnicodeError, csv.Error) as exc:
            raise ProjectInspectionError(
                f"Cannot inspect source table: {path_for_table}"
            ) from exc

    classifications = {
        field_name: analytical_classification(values)
        for field_name, values in analytical_values.items()
    }
    return ExplorationInspection(
        path=resolved,
        manifest_path=manifest_path.resolve(),
        manifest=manifest,
        counts=MappingProxyType(counts),
        analytical_variables=MappingProxyType(classifications),
    )


def inspect_topography(path: Path) -> TopographyInspection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ProjectInspectionError(f"Topography file does not exist: {resolved}")
    point_count = 0
    x_min = y_min = z_min = math.inf
    x_max = y_max = z_max = -math.inf
    try:
        with resolved.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = tuple(next(reader, ()))
            if header != TOPOGRAPHY_COLUMNS:
                raise ProjectInspectionError(
                    f"Invalid topography schema: expected {TOPOGRAPHY_COLUMNS}, got {header}"
                )
            for row_number, row in enumerate(reader, start=2):
                if len(row) != 4:
                    raise ProjectInspectionError(
                        f"Invalid topography row {row_number}: expected PID,X,Y,Z"
                    )
                try:
                    pid, x, y, z = (float(value) for value in row)
                except ValueError as exc:
                    raise ProjectInspectionError(
                        f"Invalid numeric topography value at row {row_number}"
                    ) from exc
                if not all(math.isfinite(value) for value in (pid, x, y, z)):
                    raise ProjectInspectionError(
                        f"Non-finite topography value at row {row_number}"
                    )
                point_count += 1
                x_min, x_max = min(x_min, x), max(x_max, x)
                y_min, y_max = min(y_min, y), max(y_max, y)
                z_min, z_max = min(z_min, z), max(z_max, z)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ProjectInspectionError(f"Cannot inspect topography: {resolved}") from exc
    if point_count < 3:
        raise ProjectInspectionError("Topography requires at least three XYZ points")
    return TopographyInspection(
        path=resolved,
        point_count=point_count,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        z_min=z_min,
        z_max=z_max,
    )


def discover_exploration_datasets(data_root: Path) -> tuple[ExplorationInspection, ...]:
    """Return valid M01 releases below Data/, independent of folder names."""

    root = data_root.resolve()
    if not root.is_dir():
        return ()
    candidates: list[ExplorationInspection] = []
    for manifest_path in sorted(root.rglob("release_manifest.json")):
        directory = manifest_path.parent.resolve()
        if not directory.is_relative_to(root):
            continue
        if not all((directory / name).is_file() for name in CORE_SOURCE_FILES):
            continue
        try:
            candidates.append(inspect_exploration_directory(directory))
        except ProjectInspectionError:
            continue
    return tuple(candidates)


def discover_topographies(data_root: Path) -> tuple[TopographyInspection, ...]:
    """Return schema-valid topography CSVs stored directly in Data/."""

    root = data_root.resolve()
    if not root.is_dir():
        return ()
    candidates: list[TopographyInspection] = []
    for path in sorted(root.glob("*.csv")):
        try:
            candidates.append(inspect_topography(path))
        except ProjectInspectionError:
            continue
    return tuple(candidates)


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _yes(io: TerminalIO, label: str) -> bool:
    return io.prompt(label).strip().lower() in {"y", "yes"}


def _rescan_or_exit(io: TerminalIO) -> bool:
    while True:
        io.write()
        io.write("[R] Rescan Data")
        io.write("[0] Back / Exit")
        selection = io.prompt("Select an option:").strip().lower()
        if selection == "r":
            return True
        if selection == "0":
            return False
        io.write("Invalid option. Select R or 0.")


def _select_exploration(
    candidates: tuple[ExplorationInspection, ...],
    paths: ProjectPaths,
    io: TerminalIO,
) -> ExplorationInspection | None:
    if len(candidates) == 1:
        selected = candidates[0]
        manifest = selected.manifest
        io.write()
        io.write("Exploration dataset detected:")
        io.write()
        io.write(f"[1] {_display_path(selected.path, paths.project_root)}")
        io.write()
        io.write("Manifest:")
        io.write(f"Project:   {manifest.get('project_name') or manifest['project_id']}")
        io.write(f"Dataset:   {manifest['dataset_id']}")
        io.write(f"Release:   {manifest['release_id']}")
        return selected if _yes(io, "Use this dataset? [Y/N]:") else None

    io.write()
    io.write("=" * 60)
    io.write("EXPLORATION DATASETS DETECTED")
    io.write("=" * 60)
    io.write()
    io.write(f"{'#':<4}{'Folder':<24}{'Project':<24}{'Dataset':<12}Release")
    io.write("-" * 76)
    for index, candidate in enumerate(candidates, start=1):
        manifest = candidate.manifest
        folder = _display_path(candidate.path, paths.project_root)
        project = str(manifest.get("project_name") or manifest["project_id"])
        io.write(
            f"{index:<4}{folder:<24.24}{project:<24.24}"
            f"{str(manifest['dataset_id']):<12.12}{manifest['release_id']}"
        )
    while True:
        raw = io.prompt("Select the exploration dataset:")
        try:
            index = int(raw) - 1
        except ValueError:
            index = -1
        if 0 <= index < len(candidates):
            selected = candidates[index]
            break
        io.write("Select one of the listed exploration datasets.")
    manifest = selected.manifest
    io.write()
    io.write("Selected:")
    io.write(_display_path(selected.path, paths.project_root))
    io.write(
        f"{manifest.get('project_name') or manifest['project_id']} | "
        f"{manifest['dataset_id']} | {manifest['release_id']}"
    )
    return selected if _yes(io, "Confirm? [Y/N]:") else None


def _print_topography_details(
    io: TerminalIO,
    topography: TopographyInspection,
    paths: ProjectPaths,
) -> None:
    io.write(_display_path(topography.path, paths.project_root))
    io.write()
    io.write(f"Points: {topography.point_count:,}")
    io.write(f"X: {topography.x_min:,.3f} to {topography.x_max:,.3f}")
    io.write(f"Y: {topography.y_min:,.3f} to {topography.y_max:,.3f}")
    io.write(f"Z: {topography.z_min:,.3f} to {topography.z_max:,.3f}")


def _select_topography(
    candidates: tuple[TopographyInspection, ...],
    paths: ProjectPaths,
    io: TerminalIO,
) -> TopographyInspection | None:
    if len(candidates) == 1:
        selected = candidates[0]
        io.write()
        io.write("Topography detected:")
        io.write()
        _print_topography_details(io, selected, paths)
        return selected if _yes(io, "Use this topography? [Y/N]:") else None

    io.write()
    io.write("=" * 60)
    io.write("TOPOGRAPHY FILES DETECTED")
    io.write("=" * 60)
    io.write()
    io.write(f"{'#':<4}{'File':<30}{'Points':>12}{'Z Min':>15}{'Z Max':>15}")
    io.write("-" * 76)
    for index, candidate in enumerate(candidates, start=1):
        file_name = _display_path(candidate.path, paths.project_root)
        io.write(
            f"{index:<4}{file_name:<30.30}{candidate.point_count:>12,}"
            f"{candidate.z_min:>15,.3f}{candidate.z_max:>15,.3f}"
        )
    while True:
        raw = io.prompt("Select the correct topography:")
        try:
            index = int(raw) - 1
        except ValueError:
            index = -1
        if 0 <= index < len(candidates):
            selected = candidates[index]
            break
        io.write("Select one of the listed topography files.")
    io.write()
    io.write("Selected:")
    _print_topography_details(io, selected, paths)
    return selected if _yes(io, "Confirm? [Y/N]:") else None


def _print_project_confirmation(
    io: TerminalIO,
    exploration: ExplorationInspection,
    topography: TopographyInspection,
    paths: ProjectPaths,
) -> None:
    manifest = exploration.manifest
    project_name = str(manifest.get("project_name") or manifest["project_id"])
    io.write()
    io.write("=" * 60)
    io.write("PROJECT INPUTS")
    io.write("=" * 60)
    io.write()
    io.write(f"Project:          {project_name}")
    io.write(f"Dataset:          {manifest['dataset_id']}")
    io.write(f"Release:          {manifest['release_id']}")
    io.write()
    io.write("Exploration data:")
    io.write(_display_path(exploration.path, paths.project_root))
    io.write()
    io.write("Topography:")
    io.write(_display_path(topography.path, paths.project_root))
    io.write()
    io.write(f"Drillholes:       {exploration.counts['collar.csv']:,}")
    io.write(f"Survey stations:  {exploration.counts['survey.csv']:,}")
    io.write(f"Assays:           {exploration.counts['assay.csv']:,}")
    io.write(f"Density samples:  {exploration.counts['density.csv']:,}")
    io.write(f"Topo points:      {topography.point_count:,}")
    io.write()


def configure_active_project(paths: ProjectPaths, io: TerminalIO) -> ActiveProject | None:
    """Discover inputs only in Data/ and activate them after explicit confirmation."""

    io.write("=" * 60)
    io.write("PLANMINPY")
    io.write("MINE PLANNING SYSTEM")
    io.write("=" * 60)
    io.write()
    io.write("No project data are currently active.")
    rescan_requested = False
    while True:
        if rescan_requested:
            answer = "r"
            rescan_requested = False
        else:
            answer = io.prompt(
                "Are the project inputs located in the Data folder? [Y/N]:"
            ).lower()
        if answer == "0":
            return None
        if answer in {"n", "no"}:
            io.write()
            io.write("PlanMinPy expects project inputs inside:")
            io.write(paths.data_root)
            io.write()
            io.write("Place the exploration dataset folder and topography file there,")
            io.write("then return and rescan.")
            if not _rescan_or_exit(io):
                return None
            answer = "r"
        elif answer not in {"y", "yes", "r"}:
            io.write("Enter Y, N, or 0.")
            continue

        io.write()
        io.write("Scanning:")
        io.write(paths.data_root)
        exploration_candidates = discover_exploration_datasets(paths.data_root)
        if not exploration_candidates:
            io.write()
            io.write("No valid exploration dataset was detected inside Data/.")
            io.write()
            io.write("Expected core files:")
            for name in CORE_SOURCE_FILES:
                io.write(name)
            io.write()
            io.write(
                "The current M01 contract also validates lithology.csv, "
                "alteration.csv and density.csv."
            )
            io.write("Place the dataset folder inside Data/ and select Rescan.")
            if not _rescan_or_exit(io):
                return None
            rescan_requested = True
            continue
        exploration = _select_exploration(exploration_candidates, paths, io)
        if exploration is None:
            io.write("Dataset was not activated. Returning to discovery.")
            continue

        topography_candidates = discover_topographies(paths.data_root)
        if not topography_candidates:
            io.write()
            io.write("No valid topography CSV was detected inside Data/.")
            io.write()
            io.write("A topography file must contain:")
            io.write("PID, X, Y, Z")
            io.write()
            io.write("Place the file inside Data/ and rescan.")
            if not _rescan_or_exit(io):
                return None
            rescan_requested = True
            continue
        topography = _select_topography(topography_candidates, paths, io)
        if topography is None:
            io.write("Topography was not activated. Returning to discovery.")
            continue

        _print_project_confirmation(io, exploration, topography, paths)
        if not _yes(io, "Use these project inputs? [Y/N]:"):
            io.write("Inputs were not activated. Returning to discovery.")
            continue
        manifest = exploration.manifest
        return ActiveProject(
            exploration_data_path=exploration.path,
            topography_path=topography.path,
            project_id=str(manifest["project_id"]),
            project_name=str(manifest.get("project_name") or manifest["project_id"]),
            dataset_id=str(manifest["dataset_id"]),
            release_id=str(manifest["release_id"]),
            manifest_path=exploration.manifest_path,
            manifest=manifest,
            source_counts=MappingProxyType(
                {**dict(exploration.counts), "topography.csv": topography.point_count}
            ),
            analytical_variables=exploration.analytical_variables,
        )
