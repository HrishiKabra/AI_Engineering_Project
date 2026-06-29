"""Small shared utilities (lifted/adapted from the v1 notebook)."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def stable_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def append_jsonl(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
