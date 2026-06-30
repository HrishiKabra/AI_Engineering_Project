"""Parser for FIA result/classification documents (race, qualifying, practice, grid).

These are timing-sheet PDFs with no ruled-table structure, so raw text extraction
scrambles the columns (and sometimes drops the P1 row). We instead reconstruct rows
by their y-coordinate, which keeps each row intact and in finishing/ranking order,
then pull the position + driver + team out of each row. The result is one
self-describing chunk per document (e.g. "... Race result. Winner: Lando Norris.
Full order: P1 ...") so the agent can answer "who won / who was on pole / FP order"
grounded in the official classification — no hallucinated standings.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import fitz  # PyMuPDF

from app.ingestion.models import ChunkRow

# Subtypes (from classify_doc) handled here.
RESULT_SUBTYPES = {"classification", "starting_grid"}

# Row: "<pos> <car> <Firstname SURNAME> <team + times>". Firstname is Title-case
# (lowercase tail), surname is ALL-CAPS — that boundary separates name from the rest.
_NAME = r"[A-Z][a-zà-ÿ'’.-]+(?:\s[A-Z][a-zà-ÿ'’.-]+)*\s+[A-Z][A-Z'’-]+(?:[-\s][A-Z'’-]{2,})*"
_ROW = re.compile(rf"^(\d{{1,2}})\s+(\d{{1,2}})\s+({_NAME})\s+(.+)$")

# Match a row's trailing text to a clean team name.
_TEAMS = [
    ("mclaren", "McLaren"),
    ("ferrari", "Ferrari"),
    ("red bull", "Red Bull Racing"),
    ("mercedes", "Mercedes"),
    ("aston", "Aston Martin"),
    ("alpine", "Alpine"),
    ("williams", "Williams"),
    ("haas", "Haas"),
    ("sauber", "Kick Sauber"),
    ("racing bulls", "Racing Bulls"),
    ("visa", "Racing Bulls"),
]


def _rows_by_y(pdf_path: Path | str) -> list[str]:
    """Reconstruct visual rows across all pages by grouping words on their y-position."""
    out: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            bands: dict[int, list[tuple[float, str]]] = defaultdict(list)
            for w in page.get_text("words"):  # x0, y0, x1, y1, word, ...
                bands[round(w[1] / 3)].append((w[0], w[4]))
            for y in sorted(bands):
                out.append(" ".join(t for _, t in sorted(bands[y])))
    return out


def _doc_title(rows: list[str]) -> str:
    for i, line in enumerate(rows):
        s = line.strip()
        if s == "Title" and i + 1 < len(rows):
            return rows[i + 1].strip()
        m = re.match(r"Title\s+(.+)", s)
        if m:
            return m.group(1).strip()
    return "Classification"


def _team_of(rest: str) -> str:
    low = rest.lower()
    for key, name in _TEAMS:
        if key in low:
            return name
    return ""


def _session_meta(title: str) -> tuple[str, str]:
    """(session label, leader label) from the document title."""
    t = title.lower()
    if "starting grid" in t:
        return "starting grid", "Pole position (P1 on the grid)"
    if "sprint" in t and "grid" not in t:
        return ("sprint qualifying result", "Sprint pole") if "qualifying" in t else (
            "sprint race result", "Sprint winner")
    if "qualifying" in t:
        return "qualifying result", "Pole position"
    if "race" in t:
        return "race result", "Winner"
    m = re.search(r"\bP([123])\b", title)
    if m:
        return f"free practice {m.group(1)} (FP{m.group(1)}) result", "Fastest"
    return "session result", "P1"


def parse_results(pdf_path: Path | str, season: int | None, grand_prix: str | None) -> list[ChunkRow]:
    rows = _rows_by_y(pdf_path)
    title = _doc_title(rows)

    seen: set[int] = set()
    ordered: list[tuple[int, str, str]] = []
    for line in rows:
        m = _ROW.match(line.strip())
        if not m:
            continue
        pos = int(m.group(1))
        if pos in seen:
            continue
        seen.add(pos)
        driver = m.group(3).strip().title()  # "Max VERSTAPPEN" -> "Max Verstappen"
        ordered.append((pos, driver, _team_of(m.group(4))))

    if len(ordered) < 3:  # not a parseable classification (e.g. championship grid) — skip
        return []
    ordered.sort()

    session, leader = _session_meta(title)
    gp = (grand_prix or "").replace("_", " ").title()
    p1 = ordered[0][1]
    entries = ", ".join(f"P{p} {d}" + (f" ({t})" if t else "") for p, d, t in ordered)
    content = (
        f"{season or ''} {gp} Grand Prix — {title} ({session}). "
        f"{leader}: {p1}. Full order: {entries}."
    ).strip()
    return [ChunkRow(kind="result", content=content, field_name=session)]
