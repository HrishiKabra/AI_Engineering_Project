"""Parser for steward decision documents.

Fields appear as a label on its own line followed by the value on subsequent
lines, with the occasional inline ``Infringement Breach of ...`` form. We split on
the known labels, capture each value, and emit one ``field`` chunk per high-signal
field (Fact / Infringement / Decision / Reason), each tagged with the first
article it cites. Administrative metadata (No / Driver, Session, ...) is returned
separately for the document row.
"""

from __future__ import annotations

from app.guardrails.citation import first_article
from app.ingestion.models import ChunkRow

# All recognized labels (used as value boundaries). Longest-first so "No / Driver"
# is matched before a hypothetical "No".
_LABELS = [
    "No / Driver",
    "Competitor",
    "Infringement",
    "Decision",
    "Session",
    "Reason",
    "Offence",
    "Document",
    "Date",
    "Time",
    "From",
    "To",
    "Fact",
    "Note",
    "Title",
    "Description",
]
_LABELS_BY_LEN = sorted(_LABELS, key=len, reverse=True)

# Fields whose narrative we embed for retrieval.
_HIGH_SIGNAL = ["Fact", "Infringement", "Decision", "Reason"]

# Boilerplate that terminates the Reason field (appeal notice + signatures).
_BOILERPLATE_MARKERS = (
    "Competitors are reminded that they have the right to appeal",
    "Decisions of the Stewards are taken independently",
)


def _match_label(line: str) -> tuple[str, str] | None:
    """If a line begins a labeled field, return (label, inline_value)."""
    stripped = line.strip()
    for label in _LABELS_BY_LEN:
        if stripped == label:
            return label, ""
        if stripped.startswith(label):
            rest = stripped[len(label) :]
            # require a boundary so "Decisions of the Stewards" != "Decision"
            if rest[:1] in ("", " ", ":"):
                return label, rest.lstrip(": ").strip()
    return None


def parse_decision(text: str) -> tuple[dict[str, str], list[ChunkRow]]:
    lines = text.split("\n")
    fields: dict[str, list[str]] = {}
    current: str | None = None

    for ln in lines:
        matched = _match_label(ln)
        if matched:
            label, inline = matched
            current = label
            fields.setdefault(label, [])
            if inline:
                fields[label].append(inline)
        elif current is not None:
            fields[current].append(ln)

    # Collapse to strings; trim Reason boilerplate.
    meta: dict[str, str] = {}
    for label, vals in fields.items():
        joined = "\n".join(vals).strip()
        if label == "Reason":
            joined = _trim_boilerplate(joined)
        meta[label] = joined

    rows: list[ChunkRow] = []
    for label in _HIGH_SIGNAL:
        val = meta.get(label, "").strip()
        if not val:
            continue
        rows.append(
            ChunkRow(
                kind="field",
                content=f"{label}: {val}",
                field_name=label,
                article_id=first_article(val),
            )
        )
    return meta, rows


def _trim_boilerplate(reason: str) -> str:
    lines = reason.split("\n")
    out: list[str] = []
    for ln in lines:
        if any(ln.strip().startswith(m) for m in _BOILERPLATE_MARKERS):
            break
        out.append(ln)
    return "\n".join(out).strip()
