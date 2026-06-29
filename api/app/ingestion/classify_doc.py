"""Classify a source PDF into doc_type / subtype + extract path metadata."""

from __future__ import annotations

import re
from pathlib import Path

from app.ingestion.models import DocMeta

# Filename keyword -> steward-decision subtype. Order matters (first match wins).
_SUBTYPE_KEYWORDS = [
    ("infringement", "infringement"),
    ("summons", "summons"),
    ("decision", "decision"),
    ("championship points", "championship_points"),
    ("classification", "classification"),
    ("starting grid", "starting_grid"),
    ("scrutineering", "scrutineering"),
    ("entry list", "entry_list"),
    ("event notes", "event_notes"),
    ("race director", "event_notes"),
    ("procedure", "procedure"),
    ("pirelli", "event_notes"),
    ("curfew", "event_notes"),
    ("car presentation", "event_notes"),
    ("pu elements", "event_notes"),
    ("penalty points", "penalty_points"),
]

# Subtypes that are pure tables / administrative — store the document row but do
# not embed (they add retrieval noise and carry no Fact/Reason narrative).
_TABLE_ONLY_SUBTYPES = {
    "classification",
    "championship_points",
    "starting_grid",
    "entry_list",
    "scrutineering",
}

_DOC_NUM_RE = re.compile(r"Doc(?:ument)?\.?\s+(\d+)", re.IGNORECASE)
_GP_FOLDER_RE = re.compile(r"^(\d{4})_(.+)$")


def _subtype_from_name(name: str) -> str | None:
    low = name.lower()
    for kw, subtype in _SUBTYPE_KEYWORDS:
        if kw in low:
            return subtype
    return None


def classify(source_file: str, text: str, content_hash: str) -> DocMeta:
    path = Path(source_file)
    parts = {p.lower() for p in path.parts}
    name = path.stem

    # --- regulations ---
    if "regulations" in parts:
        if "penalty_points" in name.lower() or "penalties" in name.lower():
            return DocMeta(
                doc_type="penalty_points",
                doc_subtype="penalty_points",
                source_file=source_file,
                content_hash=content_hash,
                season=_season_from_name(name),
            )
        return DocMeta(
            doc_type="sporting_regulation",
            doc_subtype="sporting_regulation",
            source_file=source_file,
            content_hash=content_hash,
            season=_season_from_name(name),
        )

    # --- steward decisions ---
    season, grand_prix = _season_gp_from_folder(path)
    subtype = _subtype_from_name(name)
    doc_num_match = _DOC_NUM_RE.search(name)
    document_number = doc_num_match.group(1) if doc_num_match else None

    has_narrative = bool(
        re.search(r"(?m)^(Fact|Infringement|Reason)\b", text)
    )
    is_table_only = subtype in _TABLE_ONLY_SUBTYPES or not has_narrative

    return DocMeta(
        doc_type="steward_decision",
        doc_subtype=subtype,
        source_file=source_file,
        content_hash=content_hash,
        season=season,
        grand_prix=grand_prix,
        document_number=document_number,
        is_table_only=is_table_only,
    )


def _season_from_name(name: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", name)
    return int(m.group(1)) if m else None


def _season_gp_from_folder(path: Path) -> tuple[int | None, str | None]:
    for part in path.parts:
        m = _GP_FOLDER_RE.match(part)
        if m:
            return int(m.group(1)), m.group(2)
    return None, None
