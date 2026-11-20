# DocParse

A small Flask web app that turns a résumé (PDF or .txt) into structured JSON:
name, email, phone, skills, education and experience.

## How it works

1. **Text extraction**: `pypdf` reads PDFs; text files are decoded directly.
2. **AI extraction**: if `ANTHROPIC_API_KEY` is set, the text is sent to an LLM with a
   prompt that asks for a fixed JSON shape. The reply is parsed defensively
   (code fences and extra chatter are stripped) and normalised so the output
   always has the same fields and types.
3. **Fallback**: with no API key, or if the LLM call fails, regex and keyword
   rules extract the same fields, so the app still returns a result.
   The response includes a `method` field showing which path was used.

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here   # optional; without it the rules fallback is used
python app.py
```

Open http://127.0.0.1:5000, upload a file, or call the API:

```bash
curl -F "file=@sample_resume.txt" http://127.0.0.1:5000/api/parse
```

Set `DOCPARSE_MODEL` to change the model (default `claude-sonnet-5-5`).

## Tests

```bash
pytest
```

18 tests cover the rules parser, LLM reply handling (with a fake client, so no
network or key is needed), the fallback path, and the upload endpoint
(wrong file type, missing, empty and oversized files, blank PDFs). GitHub
Actions runs them on every push (`.github/workflows/test.yml`).

## Limitations

- The rules fallback is heuristic: it is much weaker than the LLM path on
  unusual layouts.
- Scanned (image-only) PDFs have no extractable text and are rejected; OCR is
  not included.
- Uploads are capped at 2 MB, and text sent to the LLM is truncated to 20,000
  characters.
- Résumés contain personal data: files are processed in memory and not stored.
