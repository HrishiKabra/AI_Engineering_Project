"""PDF text extraction and normalization (PyMuPDF).

The downstream structure-aware parsers rely on clean line starts (e.g. an
``ARTICLE B1`` header or a ``Fact:`` label). A garbled header silently breaks the
parent-child split, so :func:`clean_text` repairs the known extraction artifacts
before any parsing happens.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

# Ligature / glyph artifacts seen in the FIA PDFs. The "ff -> =" case ("O=icials")
# came from pdftotext; PyMuPDF usually emits the real ligature codepoints, so we
# map both the unicode ligatures and the stray "=" form defensively.
_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    " ": " ",
}

# Words mangled by the "ff" -> "=" artifact. Applied only as whole words to avoid
# clobbering legitimate "=" usage.
_EQ_WORDS = {
    "O=icials": "Officials",
    "o=icials": "officials",
    "O=ice": "Office",
    "o=ice": "office",
    "o=icial": "official",
    "O=icial": "Official",
    "e=ect": "effect",
    "a=ected": "affected",
}


def pdf_to_text(pdf_path: Path | str) -> str:
    """Extract text from a PDF, one page joined per newline."""
    parts: list[str] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def _strip_repeated_lines(text: str, threshold: float = 0.5) -> str:
    """Drop running headers/footers: short lines repeated on most pages."""
    lines = text.split("\n")
    page_count = max(text.count("\f") + 1, text.count("\n\n\n") + 1, 1)
    counts = Counter(ln.strip() for ln in lines if ln.strip())
    repeated = {
        ln
        for ln, n in counts.items()
        if len(ln) < 80 and n >= 3 and n >= threshold * page_count
    }
    if not repeated:
        return text
    return "\n".join(ln for ln in lines if ln.strip() not in repeated)


def clean_text(raw: str) -> str:
    """Normalize ligatures, repair glyph artifacts, strip headers/footers, collapse blanks."""
    text = raw
    for bad, good in _LIGATURES.items():
        text = text.replace(bad, good)
    for bad, good in _EQ_WORDS.items():
        text = text.replace(bad, good)

    text = text.replace("\f", "\n")
    text = _strip_repeated_lines(text)

    # Normalize whitespace: trim trailing spaces, collapse 3+ blank lines to 2.
    text = "\n".join(ln.rstrip() for ln in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_pdf(pdf_path: Path | str) -> str:
    """Extract + clean in one call."""
    return clean_text(pdf_to_text(pdf_path))
