"""Typed, mining-agnostic contracts shared by all PlanMinPy modules."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Callable, Mapping

if TYPE_CHECKING:
    from planminpy.core.context import ModuleContext


class PlanMinPyError(Exception):
    """Base class for expected application/domain failures."""


class ContractValidationError(PlanMinPyError):
    """Raised when a normalized application contract is invalid."""


class ProvenanceKind(str, Enum):
    OBSERVED = "OBSERVED"
    CALCULATED = "CALCULATED"
    INFERRED = "INFERRED"
    ASSUMED = "ASSUMED"


class ModuleStatus(str, Enum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    COMPLETED = "COMPLETED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    FAILED = "FAILED"


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_identifier(field_name: str, value: object) -> str:
    """Validate an identity value that may also be used as a safe path segment."""

    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{field_name} must be a non-empty string")
    if not _IDENTIFIER_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise ContractValidationError(
            f"{field_name} contains unsupported characters: {value!r}"
        )
    return value


def _validate_optional_text(field_name: str, value: object) -> None:
    if value is not None and not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be a string or None")


def _validate_aware_datetime(field_name: str, value: object) -> None:
    if not isinstance(value, datetime):
        raise ContractValidationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must include timezone information")


def _validate_json_value(field_name: str, value: object) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(
            f"{field_name} must contain JSON-compatible finite values"
        ) from exc


@dataclass(frozen=True)
class ProvenanceRecord:
    kind: ProvenanceKind
    name: str
    value: Any = None
    unit: str | None = None
    source: str | None = None
    method: str | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProvenanceKind):
            raise ContractValidationError("kind must be a ProvenanceKind value")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ContractValidationError("provenance name must be a non-empty string")
        for field_name in ("unit", "source", "method", "rationale"):
            _validate_optional_text(field_name, getattr(self, field_name))
        _validate_json_value(f"provenance[{self.name}].value", self.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "method": self.method,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProvenanceRecord:
        try:
            kind = ProvenanceKind(data["kind"])
            name = data["name"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractValidationError("invalid serialized provenance record") from exc
        return cls(
            kind=kind,
            name=name,
            value=data.get("value"),
            unit=data.get("unit"),
            source=data.get("source"),
            method=data.get("method"),
            rationale=data.get("rationale"),
        )


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    artifact_type: str
    relative_path: str
    description: str
    schema_version: str = "1.0"
    sha256: str | None = None
    byte_size: int | None = None
    record_count: int | None = None

    def __post_init__(self) -> None:
        validate_identifier("artifact_id", self.artifact_id)
        if not isinstance(self.artifact_type, str) or not self.artifact_type.strip():
            raise ContractValidationError("artifact_type must be a non-empty string")
        if not isinstance(self.description, str):
            raise ContractValidationError("artifact description must be a string")
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ContractValidationError("artifact schema_version must be non-empty")
        if not isinstance(self.relative_path, str) or not self.relative_path:
            raise ContractValidationError("artifact relative_path must be non-empty")
        relative = PurePosixPath(self.relative_path.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ContractValidationError("artifact relative_path must remain relative")
        if self.sha256 is not None:
            if not isinstance(self.sha256, str) or not re.fullmatch(
                r"[0-9a-fA-F]{64}", self.sha256
            ):
                raise ContractValidationError("artifact sha256 must be a 64-digit hash")
        if self.byte_size is not None and (
            not isinstance(self.byte_size, int) or self.byte_size < 0
        ):
            raise ContractValidationError("artifact byte_size must be a non-negative int")
        if self.record_count is not None and (
            not isinstance(self.record_count, int) or self.record_count < 0
        ):
            raise ContractValidationError("artifact record_count must be a non-negative int")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "relative_path": self.relative_path,
            "description": self.description,
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "record_count": self.record_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ArtifactRecord:
        try:
            return cls(
                artifact_id=data["artifact_id"],
                artifact_type=data["artifact_type"],
                relative_path=data["relative_path"],
                description=data["description"],
                schema_version=data.get("schema_version", "1.0"),
                sha256=data.get("sha256"),
                byte_size=data.get("byte_size"),
                record_count=data.get("record_count"),
            )
        except (KeyError, TypeError) as exc:
            raise ContractValidationError("invalid serialized artifact record") from exc


@dataclass(frozen=True)
class ModuleResult:
    module_id: str
    module_version: str
    status: ModuleStatus
    project_id: str
    dataset_id: str
    release_id: str
    started_at: datetime
    completed_at: datetime
    summary: str
    metrics: Mapping[str, Any] = field(default_factory=dict)
    provenance: tuple[ProvenanceRecord, ...] = field(default_factory=tuple)
    artifacts: tuple[ArtifactRecord, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    report_payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier("module_id", self.module_id)
        if not isinstance(self.module_version, str) or not self.module_version.strip():
            raise ContractValidationError("module_version must be a non-empty string")
        if not isinstance(self.status, ModuleStatus):
            raise ContractValidationError("status must be a ModuleStatus value")
        for field_name in ("project_id", "dataset_id", "release_id"):
            validate_identifier(field_name, getattr(self, field_name))
        _validate_aware_datetime("started_at", self.started_at)
        _validate_aware_datetime("completed_at", self.completed_at)
        if self.completed_at < self.started_at:
            raise ContractValidationError("completed_at cannot precede started_at")
        if not isinstance(self.summary, str):
            raise ContractValidationError("summary must be a string")

        metrics = dict(self.metrics)
        report_payload = dict(self.report_payload)
        provenance = tuple(self.provenance)
        artifacts = tuple(self.artifacts)
        warnings = tuple(self.warnings)
        errors = tuple(self.errors)

        if not all(isinstance(key, str) for key in metrics):
            raise ContractValidationError("metric names must be strings")
        if not all(isinstance(item, ProvenanceRecord) for item in provenance):
            raise ContractValidationError("provenance must contain ProvenanceRecord values")
        if not all(isinstance(item, ArtifactRecord) for item in artifacts):
            raise ContractValidationError("artifacts must contain ArtifactRecord values")
        if not all(isinstance(item, str) for item in warnings):
            raise ContractValidationError("warnings must contain strings")
        if not all(isinstance(item, str) for item in errors):
            raise ContractValidationError("errors must contain strings")

        _validate_json_value("metrics", metrics)
        _validate_json_value("report_payload", report_payload)

        expected_identity = {
            "module_id": self.module_id,
            "project_id": self.project_id,
            "dataset_id": self.dataset_id,
            "release_id": self.release_id,
        }
        for key, expected in expected_identity.items():
            if key in report_payload and report_payload[key] != expected:
                raise ContractValidationError(
                    f"report_payload {key} does not match ModuleResult identity"
                )

        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "report_payload", report_payload)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "errors", errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "module_version": self.module_version,
            "status": self.status.value,
            "project_id": self.project_id,
            "dataset_id": self.dataset_id,
            "release_id": self.release_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "summary": self.summary,
            "metrics": dict(self.metrics),
            "provenance": [item.to_dict() for item in self.provenance],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "report_payload": dict(self.report_payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModuleResult:
        try:
            return cls(
                module_id=data["module_id"],
                module_version=data["module_version"],
                status=ModuleStatus(data["status"]),
                project_id=data["project_id"],
                dataset_id=data["dataset_id"],
                release_id=data["release_id"],
                started_at=datetime.fromisoformat(data["started_at"]),
                completed_at=datetime.fromisoformat(data["completed_at"]),
                summary=data["summary"],
                metrics=data.get("metrics", {}),
                provenance=tuple(
                    ProvenanceRecord.from_dict(item)
                    for item in data.get("provenance", [])
                ),
                artifacts=tuple(
                    ArtifactRecord.from_dict(item)
                    for item in data.get("artifacts", [])
                ),
                warnings=tuple(data.get("warnings", [])),
                errors=tuple(data.get("errors", [])),
                report_payload=data.get("report_payload", {}),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractValidationError("invalid serialized ModuleResult") from exc


ModuleCallable = Callable[["ModuleContext"], ModuleResult]
