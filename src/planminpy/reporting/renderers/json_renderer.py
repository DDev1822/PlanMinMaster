"""Deterministic JSON rendering for report_state.json."""

from __future__ import annotations

import json

from planminpy.reporting.contracts import ReportState


def render_json(state: ReportState) -> str:
    return (
        json.dumps(
            state.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
