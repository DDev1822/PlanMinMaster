"""Scoped, atomic artifact persistence for independently executed modules."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from planminpy.core.context import ModuleContext
from planminpy.core.contracts import ArtifactRecord, PlanMinPyError, validate_identifier


class ArtifactWorkspaceError(PlanMinPyError):
    """Raised when a module artifact violates its scoped output boundary."""


class ArtifactWorkspace:
    def __init__(self, context: ModuleContext, module_id: str) -> None:
        validate_identifier("module_id", module_id)
        self._context = context
        self.module_id = module_id
        self.root = (
            context.output_root
            / context.project_id
            / context.dataset_id
            / context.release_id
            / module_id
        ).resolve(strict=False)
        output_root = context.output_root.resolve(strict=False)
        if self.root == output_root or not self.root.is_relative_to(output_root):
            raise ArtifactWorkspaceError("module workspace must remain below outputs/")
        if self.root.is_relative_to(context.data_root.resolve()):
            raise ArtifactWorkspaceError("module workspace cannot target Data/")

    def resolve(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ArtifactWorkspaceError("artifact path must be safe and relative")
        target = (self.root / relative).resolve(strict=False)
        if target == self.root or not target.is_relative_to(self.root):
            raise ArtifactWorkspaceError("artifact path escapes the module workspace")
        return target

    def _write_bytes(self, relative_path: str | Path, payload: bytes) -> Path:
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.resolve(relative_path)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.replace(temporary_name, target)
        except OSError as exc:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
            raise ArtifactWorkspaceError(f"could not write artifact: {target}") from exc
        return target

    def write_json(
        self,
        relative_path: str | Path,
        value: Mapping[str, Any],
    ) -> Path:
        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        return self._write_bytes(relative_path, payload)

    def write_text(self, relative_path: str | Path, content: str) -> Path:
        if not isinstance(content, str):
            raise ArtifactWorkspaceError("text artifact content must be a string")
        return self._write_bytes(relative_path, content.encode("utf-8"))

    def write_csv(
        self,
        relative_path: str | Path,
        fieldnames: Sequence[str],
        rows: Iterable[Mapping[str, Any]],
    ) -> tuple[Path, int]:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer,
            fieldnames=fieldnames,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        count = 0
        for row in rows:
            writer.writerow(row)
            count += 1
        return self._write_bytes(relative_path, buffer.getvalue().encode("utf-8")), count

    def record(
        self,
        path: Path,
        *,
        artifact_id: str,
        artifact_type: str,
        description: str,
        schema_version: str,
        record_count: int | None,
    ) -> ArtifactRecord:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ArtifactWorkspaceError("artifact record path is outside workspace")
        payload = resolved.read_bytes()
        return ArtifactRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            relative_path=resolved.relative_to(self._context.output_root).as_posix(),
            description=description,
            schema_version=schema_version,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_size=len(payload),
            record_count=record_count,
        )
