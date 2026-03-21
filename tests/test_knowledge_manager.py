import json

from pypdf import PdfWriter

from src.knowledge import KnowledgeManager


def make_manager_without_init():
    return KnowledgeManager.__new__(KnowledgeManager)


def test_read_document_txt(tmp_path):
    manager = make_manager_without_init()
    file_path = tmp_path / "menu.txt"
    file_path.write_text("Суп дня", encoding="utf-8")

    source_type, content = manager._read_document(file_path)
    assert source_type == "txt"
    assert content == "Суп дня"


def test_read_document_json(tmp_path):
    manager = make_manager_without_init()
    file_path = tmp_path / "faq.json"
    file_path.write_text(json.dumps({"q": "A?"}, ensure_ascii=False), encoding="utf-8")

    source_type, content = manager._read_document(file_path)
    assert source_type == "json"
    assert '"q": "A?"' in content


def test_read_document_pdf(tmp_path):
    manager = make_manager_without_init()
    file_path = tmp_path / "doc.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with file_path.open("wb") as f:
        writer.write(f)

    source_type, content = manager._read_document(file_path)
    assert source_type == "pdf"
    assert isinstance(content, str)


def test_split_chunks():
    manager = make_manager_without_init()
    chunks = manager._split_chunks("x" * 2200)
    assert len(chunks) >= 2
    assert all(chunk for chunk in chunks)
