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
CHAMPIONSHIP_SUBTYPE = "championship_points"

# Distinctive single tokens -> canonical constructor name (handles wrapped names like
# "Mercedes-AMG …", "Oracle Red Bull Racing", "Racing Bulls").
_CONSTRUCTOR_TOKENS = [
    ("McLaren", "McLaren"),
    ("Mercedes", "Mercedes"),
    ("Oracle", "Red Bull Racing"),
    ("Ferrari", "Ferrari"),
    ("Williams", "Williams"),
    ("Bulls", "Racing Bulls"),
    ("Aston", "Aston Martin"),
    ("Haas", "Haas"),
    ("Sauber", "Kick Sauber"),
    ("Alpine", "Alpine"),
]
# A drivers'-standings row: "1 L. NORRIS 423" (rank, initial+surname, total points).
_DRIVER_STANDING = re.compile(r"^(\d{1,2})\s+([A-Z]\.\s*[A-Z][A-Za-zà-ÿ'’-]+)\s+(\d{1,4})$")

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


def _parse_drivers_standings(pdf_path: Path | str) -> list[tuple[int, str, int]]:
    out: list[tuple[int, str, int]] = []
    seen: set[int] = set()
    for line in _rows_by_y(pdf_path):
        m = _DRIVER_STANDING.match(line.strip())
        if not m:
            continue
        rank = int(m.group(1))
        if rank in seen:
            continue
        seen.add(rank)
        out.append((rank, " ".join(m.group(2).split()), int(m.group(3))))
    out.sort()
    return out


def _parse_constructor_standings(pdf_path: Path | str) -> list[tuple[int, str, int]]:
    """Read the constructors table by the x-position of the TOTAL column (robust to
    the wide per-race columns and wrapped team names)."""
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            words = page.get_text("words")  # x0, y0, x1, y1, word, ...
            if not any(w[4] == "ENTRANT" for w in words):
                continue
            totals_hdr = [w for w in words if w[4] == "TOTAL"]
            if not totals_hdr:
                continue
            xt = (totals_hdr[0][0] + totals_hdr[0][2]) / 2
            yh = totals_hdr[0][1]
            totals = [
                v
                for _, v in sorted(
                    (w[1], int(w[4]))
                    for w in words
                    if re.fullmatch(r"\d{2,4}", w[4])
                    and abs((w[0] + w[2]) / 2 - xt) < 14
                    and w[1] > yh
                )
            ]
            first_y: dict[str, float] = {}
            for w in words:
                for key, name in _CONSTRUCTOR_TOKENS:
                    if w[4].startswith(key):
                        first_y[name] = min(first_y.get(name, 1e9), w[1])
                        break
            teams = [n for n, _ in sorted(first_y.items(), key=lambda kv: kv[1])]
            return [(i + 1, t, v) for i, (t, v) in enumerate(zip(teams, totals, strict=False))]
    return []


def parse_championship(
    pdf_path: Path | str, season: int | None, grand_prix: str | None
) -> list[ChunkRow]:
    """Drivers' + constructors' championship standings -> two retrievable chunks."""
    gp = (grand_prix or "").replace("_", " ").title()
    after = f" after the {gp} Grand Prix" if gp else ""
    rows: list[ChunkRow] = []

    drivers = _parse_drivers_standings(pdf_path)
    if drivers:
        lead = drivers[0]
        order = ", ".join(f"P{r} {d} {p}" for r, d, p in drivers)
        rows.append(
            ChunkRow(
                kind="result",
                field_name="drivers championship",
                content=(
                    f"{season or ''} Formula 1 Drivers' Championship standings{after}. "
                    f"Championship leader: {lead[1]} with {lead[2]} points. "
                    f"Full standings (points): {order}."
                ).strip(),
            )
        )

    constructors = _parse_constructor_standings(pdf_path)
    if constructors:
        lead = constructors[0]
        order = ", ".join(f"P{r} {t} {p}" for r, t, p in constructors)
        rows.append(
            ChunkRow(
                kind="result",
                field_name="constructors championship",
                content=(
                    f"{season or ''} Formula 1 Constructors' Championship standings{after}. "
                    f"Leading constructor: {lead[1]} with {lead[2]} points. "
                    f"Full standings (points): {order}."
                ).strip(),
            )
        )
    return rows
