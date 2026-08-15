from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from planminpy.core.contracts import (
    ContractValidationError,
    ModuleResult,
    ModuleStatus,
    ProvenanceKind,
    ProvenanceRecord,
)


class ContractTests(unittest.TestCase):
    def test_all_valid_provenance_categories_are_accepted(self) -> None:
        for kind in ProvenanceKind:
            with self.subTest(kind=kind):
                record = ProvenanceRecord(kind=kind, name="example", value=1)
                self.assertIs(record.kind, kind)

    def test_invalid_provenance_category_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProvenanceRecord(kind="MEASURED", name="example")  # type: ignore[arg-type]

    def test_module_result_rejects_inconsistent_internal_identity(self) -> None:
        now = datetime.now(timezone.utc)
        with self.assertRaises(ContractValidationError):
            ModuleResult(
                module_id="m01",
                module_version="0.1.0",
                status=ModuleStatus.COMPLETED,
                project_id="project_a",
                dataset_id="DS00",
                release_id="EXP03",
                started_at=now,
                completed_at=now,
                summary="test",
                report_payload={"dataset_id": "DS99"},
            )

    def test_module_result_rejects_reversed_timestamps(self) -> None:
        now = datetime.now(timezone.utc)
        with self.assertRaises(ContractValidationError):
            ModuleResult(
                module_id="m01",
                module_version="0.1.0",
                status=ModuleStatus.COMPLETED,
                project_id="project_a",
                dataset_id="DS00",
                release_id="EXP03",
                started_at=now,
                completed_at=now - timedelta(seconds=1),
                summary="test",
            )


if __name__ == "__main__":
    unittest.main()
