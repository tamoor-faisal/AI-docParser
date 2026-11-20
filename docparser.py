"""DocParse: turn a resume (PDF or text) into structured JSON.

Primary path: an LLM (Anthropic API) extracts the fields as JSON.
Fallback path: simple regex/keyword rules, used when no API key is set or the
LLM call fails, so the app always returns something useful.
"""
import io
import json
import os
import re

TEXT_FIELDS = ("name", "email", "phone")
LIST_FIELDS = ("skills", "education", "experience")
MAX_CHARS = 20000

SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "sql", "html",
    "css", "react", "react native", "flask", "django", "node.js", "git",
    "docker", "aws", "azure", "pytest", "postgresql", "sqlite", "supabase",
    "rest", "machine learning", "pandas", "excel", "power bi", "tableau",
]
EDU_WORDS = ("bachelor", "master", "phd", "diploma", "university", "ncea", "degree")

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
DATE_RANGE_RE = re.compile(
    r"(?:[A-Za-z]{3,9}\s+)?(?:19|20)\d{2}\s*[-–]\s*"
    r"(?:(?:[A-Za-z]{3,9}\s+)?(?:19|20)\d{2}|present)",
    re.IGNORECASE,
)


def extract_text(data: bytes, filename: str) -> str:
    """Return plain text from a PDF or text upload."""
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return data.decode("utf-8", errors="ignore")


def parse_with_rules(text: str) -> dict:
    """Heuristic extraction used as a fallback."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    lower = text.lower()
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    skills = sorted(
        s for s in SKILL_KEYWORDS
        if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", lower)
    )
    education = [ln for ln in lines if any(w in ln.lower() for w in EDU_WORDS)]
    experience = [
        ln for ln in lines
        if DATE_RANGE_RE.search(ln) and not any(w in ln.lower() for w in EDU_WORDS)
    ]
    return {
        "name": lines[0] if lines else "",
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "skills": skills,
        "education": education,
        "experience": experience,
    }


def load_json_reply(reply: str) -> dict:
    """Pull a JSON object out of an LLM reply (handles ``` fences and chatter)."""
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in model reply")
    data = json.loads(reply[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Model reply was not a JSON object")
    return data


def normalise(data: dict) -> dict:
    """Force the expected shape: strings for text fields, list of strings otherwise."""
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    out = {}
    for key in TEXT_FIELDS:
        value = data.get(key)
        out[key] = "" if value is None else str(value).strip()
    for key in LIST_FIELDS:
        value = data.get(key)
        if value is None:
            out[key] = []
        elif isinstance(value, list):
            out[key] = [str(v).strip() for v in value if str(v).strip()]
        else:
            out[key] = [str(value).strip()] if str(value).strip() else []
    return out


PROMPT = (
    "Extract the following from this resume and reply with ONLY a JSON object "
    "with these keys: name (string), email (string), phone (string), "
    "skills (list of strings), education (list of strings), "
    "experience (list of strings, one per role). Use an empty string or empty "
    "list when something is missing. Do not invent information.\n\nRESUME:\n"
)


def parse_with_llm(text: str, client=None) -> dict:
    """Extract fields with the Anthropic API. `client` can be injected for tests."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    message = client.messages.create(
        model=os.environ.get("DOCPARSE_MODEL", "claude-sonnet-5-5"),
        max_tokens=1500,
        messages=[{"role": "user", "content": PROMPT + text[:MAX_CHARS]}],
    )
    return normalise(load_json_reply(message.content[0].text))


def parse_document(text: str) -> dict:
    """Use the LLM when an API key is set, otherwise (or on failure) use rules."""
    if not text.strip():
        raise ValueError("No text could be extracted from the document")
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return {**parse_with_llm(text), "method": "llm"}
        except Exception:
            return {**normalise(parse_with_rules(text)), "method": "rules (llm failed)"}
    return {**normalise(parse_with_rules(text)), "method": "rules (no api key)"}
