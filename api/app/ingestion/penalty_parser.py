"""Parser for the flat penalty-points overview table.

After extraction the table flows as: offence text line(s), then an SR-article
line (``18.2``, ``23.6 & 23.5``, ``30.3(e)``), then sanction line(s). We pivot on
each article line and grab the text block immediately before it (offence) and
after it (sanction, up to the next pivot) into one ``row`` chunk. Adjacent rows
may overlap slightly; that is harmless for retrieval.
"""

from __future__ import annotations

import re

from app.ingestion.models import ChunkRow

# A line that is *primarily* an SR-article reference (allows "&", "App.", "(e)").
_ARTICLE_LINE_RE = re.compile(
    r"^\s*\d{1,3}\.\d+(?:\([a-z0-9]\))?(?:\s*(?:&|and|App\.|Ch\.|,|;|\d|\.|\(|\)|[a-z]|[IVX]+|\s))*$",
    re.IGNORECASE,
)
_FIRST_ARTICLE_RE = re.compile(r"(\d{1,3}\.\d+(?:\([a-z]\))?)")


def _is_article_line(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 45:
        return False
    if not _FIRST_ARTICLE_RE.match(s):
        return False
    return bool(_ARTICLE_LINE_RE.match(s))


def parse_penalty_points(text: str, window: int = 4) -> list[ChunkRow]:
    lines = [ln.strip() for ln in text.split("\n")]
    article_idxs = [i for i, ln in enumerate(lines) if _is_article_line(ln)]
    rows: list[ChunkRow] = []

    for n, i in enumerate(article_idxs):
        prev_pivot = article_idxs[n - 1] if n > 0 else -1
        next_pivot = article_idxs[n + 1] if n + 1 < len(article_idxs) else len(lines)

        offence_start = max(prev_pivot + 1, i - window)
        offence = " ".join(ln for ln in lines[offence_start:i] if ln)
        sanction = " ".join(ln for ln in lines[i + 1 : min(next_pivot, i + 1 + window)] if ln)

        art = lines[i]
        m = _FIRST_ARTICLE_RE.search(art)
        if not m:
            continue
        content = f"Offence: {offence} | SR Article: {art} | Sanction: {sanction}"
        rows.append(ChunkRow(kind="row", content=content, article_id=m.group(1)))

    return rows
