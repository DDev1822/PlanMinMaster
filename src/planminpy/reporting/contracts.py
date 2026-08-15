"""Contracts for cumulative project/dataset/release report state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from planminpy.core.contracts import (
    ContractValidationError,
    ModuleResult,
    PlanMinPyError,
    validate_identifier,
)

REPORT_SCHEMA_VERSION = "1.0"


class ReportContractError(PlanMinPyError):
    """Raised when cumulative report state is malformed or inconsistent."""


def _aware_datetime(field_name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReportContractError(f"{field_name} must include timezone information")


@dataclass(frozen=True)
class ReportSection:
    result: ModuleResult
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.result, ModuleResult):
            raise ReportContractError("report section must contain a ModuleResult")
        if not isinstance(self.updated_at, datetime):
            raise ReportContractError("section updated_at must be a datetime")
        _aware_datetime("section updated_at", self.updated_at)

    @property
    def module_id(self) -> str:
        return self.result.module_id

    def to_dict(self) -> dict[str, Any]:
        data = self.result.to_dict()
        data["section_updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportSection:
        try:
            updated_at = datetime.fromisoformat(data["section_updated_at"])
            result_data = dict(data)
            result_data.pop("section_updated_at", None)
            result = ModuleResult.from_dict(result_data)
        except (KeyError, TypeError, ValueError, ContractValidationError) as exc:
            raise ReportContractError("invalid serialized report section") from exc
        return cls(result=result, updated_at=updated_at)


@dataclass(frozen=True)
class ReportState:
    project_id: str
    dataset_id: str
    release_id: str
    created_at: datetime
    updated_at: datetime
    sections: tuple[ReportSection, ...]
    schema_version: str = REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            validate_identifier("project_id", self.project_id)
            validate_identifier("dataset_id", self.dataset_id)
            validate_identifier("release_id", self.release_id)
        except ContractValidationError as exc:
            raise ReportContractError(str(exc)) from exc
        if self.schema_version != REPORT_SCHEMA_VERSION:
            raise ReportContractError(
                f"unsupported report schema version: {self.schema_version!r}"
            )
        if not isinstance(self.created_at, datetime) or not isinstance(
            self.updated_at, datetime
        ):
            raise ReportContractError("report timestamps must be datetime values")
        _aware_datetime("created_at", self.created_at)
        _aware_datetime("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ReportContractError("updated_at cannot precede created_at")

        ordered_sections = tuple(sorted(self.sections, key=lambda item: item.module_id))
        seen: set[str] = set()
        for section in ordered_sections:
            if not isinstance(section, ReportSection):
                raise ReportContractError("sections must contain ReportSection values")
            if section.module_id in seen:
                raise ReportContractError(
                    f"duplicate report section for module {section.module_id}"
                )
            seen.add(section.module_id)
            result = section.result
            expected = (self.project_id, self.dataset_id, self.release_id)
            actual = (result.project_id, result.dataset_id, result.release_id)
            if actual != expected:
                raise ReportContractError(
                    f"section {section.module_id} identity does not match report state"
                )
        object.__setattr__(self, "sections", ordered_sections)

    @classmethod
    def from_result(cls, result: ModuleResult, timestamp: datetime) -> ReportState:
        section = ReportSection(result=result, updated_at=timestamp)
        return cls(
            project_id=result.project_id,
            dataset_id=result.dataset_id,
            release_id=result.release_id,
            created_at=timestamp,
            updated_at=timestamp,
            sections=(section,),
        )

    def upsert(self, result: ModuleResult, timestamp: datetime) -> ReportState:
        expected = (self.project_id, self.dataset_id, self.release_id)
        actual = (result.project_id, result.dataset_id, result.release_id)
        if actual != expected:
            raise ReportContractError("ModuleResult identity does not match report state")
        sections = {
            section.module_id: section
            for section in self.sections
            if section.module_id != result.module_id
        }
        sections[result.module_id] = ReportSection(result=result, updated_at=timestamp)
        return ReportState(
            project_id=self.project_id,
            dataset_id=self.dataset_id,
            release_id=self.release_id,
            created_at=self.created_at,
            updated_at=timestamp,
            sections=tuple(sections.values()),
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "dataset_id": self.dataset_id,
            "release_id": self.release_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "sections": [section.to_dict() for section in self.sections],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReportState:
        try:
            raw_sections = data["sections"]
            if not isinstance(raw_sections, list):
                raise TypeError("sections must be a list")
            return cls(
                schema_version=data["schema_version"],
                project_id=data["project_id"],
                dataset_id=data["dataset_id"],
                release_id=data["release_id"],
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                sections=tuple(
                    ReportSection.from_dict(section) for section in raw_sections
                ),
            )
        except (KeyError, TypeError, ValueError, ContractValidationError) as exc:
            raise ReportContractError("invalid serialized report state") from exc
