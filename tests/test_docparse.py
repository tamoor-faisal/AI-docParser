import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import docparser  # noqa: E402
from app import app  # noqa: E402

SAMPLE = open(
    os.path.join(os.path.dirname(__file__), "..", "sample_resume.txt"), encoding="utf-8"
).read()


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


# ---------- rules-based parsing ----------
def test_rules_extracts_contact_details():
    result = docparser.parse_with_rules(SAMPLE)
    assert result["name"] == "Jane Example"
    assert result["email"] == "jane.example@example.com"
    assert result["phone"] == "+64 21 555 0123"


def test_rules_extracts_skills_including_symbols():
    skills = docparser.parse_with_rules(SAMPLE)["skills"]
    for expected in ("python", "sql", "flask", "git", "react", "c++"):
        assert expected in skills


def test_rules_does_not_match_skill_inside_other_word():
    # "java" must not match "javascript"-only text, and "rest" must not match "interest"
    result = docparser.parse_with_rules("Someone\nI have an interest in javascript")
    assert "java" not in result["skills"]
    assert "rest" not in result["skills"]
    assert "javascript" in result["skills"]


def test_rules_splits_education_and_experience():
    result = docparser.parse_with_rules(SAMPLE)
    assert any("University of Auckland" in line for line in result["education"])
    assert len(result["experience"]) == 2
    assert not any("University" in line for line in result["experience"])


# ---------- LLM reply handling ----------
def test_load_json_reply_handles_code_fences():
    reply = 'Here you go:\n```json\n{"name": "A"}\n```'
    assert docparser.load_json_reply(reply) == {"name": "A"}


def test_load_json_reply_rejects_non_json():
    with pytest.raises(ValueError):
        docparser.load_json_reply("sorry, I cannot do that")


def test_normalise_fixes_shape():
    out = docparser.normalise(
        {"name": None, "email": " a@b.com ", "skills": "python", "education": None}
    )
    assert out == {
        "name": "",
        "email": "a@b.com",
        "phone": "",
        "skills": ["python"],
        "education": [],
        "experience": [],
    }


class FakeClient:
    """Stands in for anthropic.Anthropic so tests need no network or key."""

    def __init__(self, reply):
        self.reply = reply
        self.messages = self

    def create(self, **kwargs):
        class Block:
            pass

        block = Block()
        block.text = self.reply

        class Msg:
            content = [block]

        return Msg()


def test_parse_with_llm_uses_injected_client():
    client = FakeClient('{"name": "Jane", "email": "j@x.com", "skills": ["Python"]}')
    out = docparser.parse_with_llm("some resume", client=client)
    assert out["name"] == "Jane"
    assert out["skills"] == ["Python"]
    assert out["experience"] == []


def test_parse_document_falls_back_when_llm_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")

    def boom(text, client=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(docparser, "parse_with_llm", boom)
    out = docparser.parse_document(SAMPLE)
    assert out["method"] == "rules (llm failed)"
    assert out["email"] == "jane.example@example.com"


def test_parse_document_without_key_uses_rules():
    assert docparser.parse_document(SAMPLE)["method"] == "rules (no api key)"


def test_parse_document_rejects_empty_text():
    with pytest.raises(ValueError):
        docparser.parse_document("   \n  ")


# ---------- web app ----------
def test_api_parse_txt(client):
    resp = client.post(
        "/api/parse",
        data={"file": (io.BytesIO(SAMPLE.encode()), "resume.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.get_json()["email"] == "jane.example@example.com"


def test_api_rejects_wrong_file_type(client):
    resp = client.post(
        "/api/parse",
        data={"file": (io.BytesIO(b"x"), "resume.docx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_api_rejects_missing_file(client):
    resp = client.post("/api/parse", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_api_rejects_empty_file(client):
    resp = client.post(
        "/api/parse",
        data={"file": (io.BytesIO(b""), "empty.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_api_rejects_oversized_file(client):
    big = io.BytesIO(b"a" * (2 * 1024 * 1024 + 10))
    resp = client.post(
        "/api/parse",
        data={"file": (big, "big.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413


def test_homepage_loads(client):
    assert client.get("/").status_code == 200


def test_pdf_upload_with_no_text_returns_400(client):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    resp = client.post(
        "/api/parse",
        data={"file": (buf, "blank.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
