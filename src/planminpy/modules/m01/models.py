"""M01-specific findings and deterministic readiness evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ReadinessVerdict(str, Enum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Finding:
    finding_id: str
    rule_id: str
    severity: Severity
    blocking: bool
    requires_review: bool
    table: str | None
    row_number: int | None
    hole_id: str | None
    record_id: str | None
    field: str | None
    observed_value: Any
    expected_condition: str
    message: str
    provenance_kind: str
    source: str | None

    @classmethod
    def create(
        cls,
        rule_id: str,
        severity: Severity,
        message: str,
        *,
        blocking: bool = False,
        requires_review: bool = False,
        table: str | None = None,
        row_number: int | None = None,
        hole_id: str | None = None,
        record_id: str | None = None,
        field: str | None = None,
        observed_value: Any = None,
        expected_condition: str = "",
        provenance_kind: str = "INFERRED",
        source: str | None = None,
    ) -> Finding:
        identity = {
            "rule_id": rule_id,
            "table": table,
            "row_number": row_number,
            "hole_id": hole_id,
            "record_id": record_id,
            "field": field,
            "observed_value": observed_value,
        }
        finding_id = "F-" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            finding_id=finding_id,
            rule_id=rule_id,
            severity=severity,
            blocking=blocking,
            requires_review=requires_review,
            table=table,
            row_number=row_number,
            hole_id=hole_id,
            record_id=record_id,
            field=field,
            observed_value=observed_value,
            expected_condition=expected_condition,
            message=message,
            provenance_kind=provenance_kind,
            source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "blocking": self.blocking,
            "requires_review": self.requires_review,
            "table": self.table,
            "row_number": self.row_number,
            "hole_id": self.hole_id,
            "record_id": self.record_id,
            "field": self.field,
            "observed_value": self.observed_value,
            "expected_condition": self.expected_condition,
            "message": self.message,
            "provenance_kind": self.provenance_kind,
            "source": self.source,
        }


def readiness_verdict(findings: list[Finding]) -> ReadinessVerdict:
    if any(item.severity is Severity.ERROR and item.blocking for item in findings):
        return ReadinessVerdict.FAILED
    if any(item.requires_review for item in findings):
        return ReadinessVerdict.REQUIRES_REVIEW
    if any(item.severity is Severity.WARNING for item in findings):
        return ReadinessVerdict.PASS_WITH_WARNINGS
    return ReadinessVerdict.PASS


def finding_counts(findings: list[Finding]) -> dict[str, int]:
    return {
        "blocking_error_count": sum(
            item.severity is Severity.ERROR and item.blocking for item in findings
        ),
        "review_count": sum(item.requires_review for item in findings),
        "warning_count": sum(item.severity is Severity.WARNING for item in findings),
        "info_count": sum(item.severity is Severity.INFO for item in findings),
        "total_count": len(findings),
    }
