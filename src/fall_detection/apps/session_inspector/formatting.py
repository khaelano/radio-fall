"""Qt-free formatting helpers and constants shared by the inspector views."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .review import ReviewDocument

REVIEW_FILE = "session_review.json"


def _review_state(document: ReviewDocument) -> dict[str, Any]:
    return {
        "metadata": deepcopy(document.metadata),
        "attempts": {
            key: value.to_mapping() for key, value in sorted(document.attempts.items())
        },
    }


def _human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{value} B"


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
