"""Offline parser tests on inline fixtures mirroring the real PDF layout."""

from app.ingestion.classify_doc import classify
from app.ingestion.decisions_parser import parse_decision
from app.ingestion.penalty_parser import parse_penalty_points
from app.ingestion.regs_parser import parse_regs

REGS_FIXTURE = """\
ARTICLE B1: ORGANISATION OF A COMPETITION
ARTICLE B2: FORMAT OF A COMPETITION
ARTICLE B1: ORGANISATION OF A COMPETITION
B1.1
General Principles & Provisions
B1.1.1
Competitions are reserved for Formula One Cars as defined in the Technical Regulations.
B1.1.2
Each Competition will have the status of an international restricted competition.
ARTICLE B2: FORMAT OF A COMPETITION
B2.1
The format of the Competition is defined below.
"""

DECISION_FIXTURE = """\
2025 BRITISH GRAND PRIX
From
The Stewards
Document
40
No / Driver
22 - Yuki Tsunoda
Competitor
Oracle Red Bull Racing
Session
Race
Fact
Car 22 collided with Car 87 in Turn 6.
Infringement Breach of Article 33.3 of the FIA Formula One Sporting Regulations.
Decision
10 second time penalty.
Reason
The Stewards reviewed video evidence and determined Car 22 caused the collision.
Competitors are reminded that they have the right to appeal certain decisions of the
Stewards in accordance with Article 15.
"""

PENALTY_FIXTURE = """\
Use of tyres without appropriate identification
30.3(e)
Grid place penalty
Failing to change incorrect tyres within three laps
30.5(b)
10s stop and go (mandatory)
"""


def test_regs_parent_child_skips_toc():
    rows = parse_regs(REGS_FIXTURE)
    parents = [r for r in rows if r.kind == "parent"]
    children = [r for r in rows if r.kind == "child"]
    # TOC (first B1/B2) skipped; body has 2 article parents.
    assert {p.article_id for p in parents} == {"B1", "B2"}
    child_ids = {c.article_id for c in children}
    assert {"B1.1", "B1.1.1", "B1.1.2", "B2.1"} <= child_ids
    # Parent aggregates are not embedded; child narrative is.
    assert all(p.embed is False for p in parents)
    b111 = next(c for c in children if c.article_id == "B1.1.1")
    assert b111.embed is True
    assert "Article B1.1.1:" in b111.content
    assert b111.parent_index is not None


def test_decision_fields_and_citation():
    meta, rows = parse_decision(DECISION_FIXTURE)
    assert meta["No / Driver"] == "22 - Yuki Tsunoda"
    assert meta["Session"] == "Race"
    fields = {r.field_name: r for r in rows}
    assert set(fields) == {"Fact", "Infringement", "Decision", "Reason"}
    # Inline-label form parsed; the cited sporting-reg article is tagged.
    assert fields["Infringement"].article_id == "33.3"
    # Reason boilerplate (appeal notice) is trimmed off.
    assert "right to appeal" not in fields["Reason"].content


def test_penalty_rows_tag_article():
    rows = parse_penalty_points(PENALTY_FIXTURE)
    arts = {r.article_id for r in rows}
    assert "30.3(e)" in arts
    assert "30.5(b)" in arts
    row = next(r for r in rows if r.article_id == "30.3(e)")
    assert "tyres" in row.content.lower()


def test_classify_decision_metadata():
    src = "data/decision_docs/2025_british/013_Doc 40 - Infringement - Car 22 - Causing a collision.pdf"
    meta = classify(src, DECISION_FIXTURE, content_hash="abc")
    assert meta.doc_type == "steward_decision"
    assert meta.doc_subtype == "infringement"
    assert meta.season == 2025
    assert meta.grand_prix == "british"
    assert meta.document_number == "40"
    assert meta.is_table_only is False


def test_classify_classification_is_parsed_not_skipped():
    # Classification/result docs are now parsed into ordered-result chunks, not skipped.
    src = "data/decision_docs/2025_british/002_Doc 51 - Final Race Classification.pdf"
    meta = classify(src, "LAPS TIME NO DRIVER\n52 1:37 4 NORRIS", content_hash="xyz")
    assert meta.doc_subtype == "classification"
    assert meta.is_table_only is False


def test_classify_true_table_only_doc():
    # Genuinely table-only / administrative docs are still skipped from embedding.
    src = "data/decision_docs/2025_british/050_Doc 7 - Entry List.pdf"
    meta = classify(src, "NO DRIVER ENTRANT\n4 Lando NORRIS McLaren", content_hash="xyz")
    assert meta.doc_subtype == "entry_list"
    assert meta.is_table_only is True
