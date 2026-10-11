"""Section-aware chunking for Docsense uploads (no Chroma or LLM needed)."""
from langchain_core.documents import Document

from app.rag.sections import clean_pages, heading_level, section_documents, sections_named_in

PAGE_1 = """Page 10 of 94
Third Year B. Tech. AY (2026-27)
[2625PC31]: Computer Networks Lab (CNL)
Course Objectives: configure network servers.
COURSE CONTENTS
Expt. No. Problem Statement
1. Implement LAN and transfer data using OS sharing protocol.
2. Execution of PING/PATHPING & Tracert application."""

PAGE_2 = """Page 11 of 94
Third Year B. Tech. AY (2026-27)
3. Configure and implement routing protocol using cisco packet tracer
[2625PC12]: Embedded Processors (EP)
Module-I Introduction to Microcontrollers 10 Hrs.
Difference between Microprocessor and Microcontroller."""


def pages(n=4):
    # Repeat so the running header counts as a header (needs >= 4 pages).
    return [Document(page_content=t, metadata={"page": i, "source": "s.pdf"})
            for i, t in enumerate([PAGE_1, PAGE_2] * (n // 2))]


def test_headings():
    assert heading_level("[2625PC31]: Computer Networks Lab (CNL)") == 1
    assert heading_level("## Leave policy") == 1
    assert heading_level("COURSE CONTENTS") == 2
    assert heading_level("Module-II Data Link Layer 10 Hrs.") == 2
    assert heading_level("[2625PC31]: Computer Networks Lab (CNL) ......... 10") == 0  # table of contents
    assert heading_level("[20] [20] [60] TW P OR") == 0
    assert heading_level("CO1") == 0
    assert heading_level("1. Implement LAN and transfer data.") == 0


def test_page_numbers_and_running_headers_removed():
    cleaned = clean_pages([d.page_content for d in pages()])
    assert all("Page 1" not in c and "Third Year" not in c for c in cleaned)
    assert "[2625PC31]: Computer Networks Lab (CNL)" in cleaned[0]


def test_list_across_page_break_stays_in_its_section():
    chunks = section_documents(pages(), chunk_size=800, chunk_overlap=100)
    lab = [c for c in chunks if c.metadata.get("section", "").startswith("[2625PC31]")]
    text = "\n".join(c.page_content for c in lab[:3])
    for item in ("1. Implement LAN", "2. Execution of PING", "3. Configure and implement routing"):
        assert item in text
    # Every chunk says where it came from, so search can match the section name.
    assert all(c.page_content.startswith("Section: [2625PC31]: Computer Networks Lab (CNL)") for c in lab)
    assert lab[0].metadata["page"] == 0  # chunks keep the page they start on
    assert any(c.metadata.get("subsection") == "COURSE CONTENTS" for c in lab)


def test_question_names_section():
    titles = {
        "[2625PC11]: Computer Networks (CN)",
        "[2625PC31]: Computer Networks Lab (CNL)",
        "[2626PE13]: Machine Learning (ML)",
        "[2626PE33]: Machine Learning Lab (MLL)",
    }
    assert sections_named_in("list the experiments for computer networks lab", titles) == [
        "[2625PC31]: Computer Networks Lab (CNL)"]
    assert sections_named_in("modules of computer networks", titles) == ["[2625PC11]: Computer Networks (CN)"]
    assert sections_named_in("practicals in CNL?", titles) == ["[2625PC31]: Computer Networks Lab (CNL)"]
    assert sections_named_in("list ML lab experiments", titles) == ["[2626PE33]: Machine Learning Lab (MLL)"]
    assert sections_named_in("what is ml?", titles) == []          # short abbreviations need capitals
    assert sections_named_in("what is the leave policy", titles) == []
