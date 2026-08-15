"""Manifest-based dataset resolution and output path safety."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from planminpy.core.contracts import (
    ContractValidationError,
    PlanMinPyError,
    validate_identifier,
)


class PathSafetyError(PlanMinPyError):
    """Raised when a path violates the Data/outputs boundary."""


class DatasetResolutionError(PlanMinPyError):
    """Base class for manifest-based dataset resolution failures."""


class DatasetNotFoundError(DatasetResolutionError):
    """Raised when no canonical dataset release matches a request."""


class DuplicateDatasetError(DatasetResolutionError):
    """Raised when more than one manifest has the requested identity."""


class MalformedManifestError(DatasetResolutionError):
    """Raised when a release manifest lacks valid canonical identity."""


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    data_root: Path
    output_root: Path

    def __post_init__(self) -> None:
        project_root = Path(self.project_root).resolve()
        data_root = Path(self.data_root).resolve()
        output_root = Path(self.output_root).resolve(strict=False)
        expected_data_root = (project_root / "Data").resolve()
        expected_output_root = (project_root / "outputs").resolve(strict=False)

        if data_root != expected_data_root:
            raise PathSafetyError("data_root must be the project's Data directory")
        if output_root != expected_output_root:
            raise PathSafetyError("output_root must be the project's outputs directory")
        if output_root == data_root or output_root.is_relative_to(data_root):
            raise PathSafetyError("Data cannot be used as an output target")

        object.__setattr__(self, "project_root", project_root)
        object.__setattr__(self, "data_root", data_root)
        object.__setattr__(self, "output_root", output_root)

    @classmethod
    def from_project_root(cls, project_root: Path | str) -> ProjectPaths:
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise PathSafetyError(f"project root does not exist: {root}")
        data_root = root / "Data"
        if not data_root.is_dir():
            raise PathSafetyError(f"immutable Data directory does not exist: {data_root}")
        return cls(root, data_root, root / "outputs")

    def output_path(self, *relative_parts: str | Path) -> Path:
        if not relative_parts:
            raise PathSafetyError("an output path below outputs/ is required")

        for part in relative_parts:
            candidate_part = Path(part)
            if candidate_part.is_absolute() or candidate_part.drive:
                raise PathSafetyError("absolute generated output paths are not allowed")
            if ".." in candidate_part.parts:
                raise PathSafetyError("output path traversal is not allowed")

        candidate = self.output_root.joinpath(*relative_parts).resolve(strict=False)
        if candidate == self.output_root or not candidate.is_relative_to(self.output_root):
            raise PathSafetyError("generated path must remain strictly below outputs/")
        if candidate == self.data_root or candidate.is_relative_to(self.data_root):
            raise PathSafetyError("generated paths may not target Data/")
        return candidate

    def atomic_write_text(
        self,
        relative_parts: tuple[str | Path, ...],
        content: str,
    ) -> Path:
        target = self.output_path(*relative_parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.output_path(*relative_parts)

        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.replace(temporary_name, target)
        except OSError as exc:
            if temporary_name is not None:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise PathSafetyError(f"could not safely write output: {target}") from exc
        return target


@dataclass(frozen=True)
class ResolvedDataset:
    dataset_path: Path
    manifest_path: Path
    project_id: str
    dataset_id: str
    release_id: str
    manifest: Mapping[str, Any]


def _load_manifest(manifest_path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MalformedManifestError(
            f"cannot read valid JSON manifest: {manifest_path}"
        ) from exc
    if not isinstance(data, dict):
        raise MalformedManifestError(f"manifest must contain a JSON object: {manifest_path}")

    try:
        for field_name in ("project_id", "dataset_id", "release_id"):
            validate_identifier(field_name, data.get(field_name))
    except ContractValidationError as exc:
        raise MalformedManifestError(
            f"manifest has malformed canonical identity: {manifest_path}"
        ) from exc
    return MappingProxyType(dict(data))


def resolve_dataset(
    paths: ProjectPaths,
    dataset_id: str,
    release_id: str,
    project_id: str | None = None,
) -> ResolvedDataset:
    """Resolve a canonical release without assuming its physical folder name."""

    try:
        validate_identifier("dataset_id", dataset_id)
        validate_identifier("release_id", release_id)
        if project_id is not None:
            validate_identifier("project_id", project_id)
    except ContractValidationError as exc:
        raise DatasetResolutionError(str(exc)) from exc

    matches: list[ResolvedDataset] = []
    for manifest_path in sorted(paths.data_root.rglob("release_manifest.json")):
        resolved_manifest_path = manifest_path.resolve()
        if not resolved_manifest_path.is_relative_to(paths.data_root):
            raise PathSafetyError(
                f"manifest resolves outside immutable Data/: {manifest_path}"
            )
        manifest = _load_manifest(resolved_manifest_path)
        if manifest["dataset_id"] != dataset_id or manifest["release_id"] != release_id:
            continue
        if project_id is not None and manifest["project_id"] != project_id:
            continue
        matches.append(
            ResolvedDataset(
                dataset_path=resolved_manifest_path.parent,
                manifest_path=resolved_manifest_path,
                project_id=manifest["project_id"],
                dataset_id=manifest["dataset_id"],
                release_id=manifest["release_id"],
                manifest=manifest,
            )
        )

    requested = f"dataset={dataset_id!r}, release={release_id!r}"
    if project_id is not None:
        requested += f", project={project_id!r}"
    if not matches:
        raise DatasetNotFoundError(f"no manifest matches {requested}")
    if len(matches) > 1:
        locations = ", ".join(str(match.manifest_path) for match in matches)
        raise DuplicateDatasetError(
            f"multiple manifests match {requested}: {locations}"
        )
    return matches[0]
