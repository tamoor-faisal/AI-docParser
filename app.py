from flask import Flask, jsonify, render_template_string, request

from docparser import extract_text, parse_document

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB upload limit

PAGE = """
<!doctype html>
<title>DocParse</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
  pre { background: #f4f4f4; padding: 1rem; overflow-x: auto; border-radius: 6px; }
  .err { color: #b00020; }
</style>
<h1>DocParse</h1>
<p>Upload a r&eacute;sum&eacute; (PDF or .txt) and get structured JSON back.</p>
<form method="post" action="/" enctype="multipart/form-data">
  <input type="file" name="file" accept=".pdf,.txt" required>
  <button type="submit">Parse</button>
</form>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
{% if result %}<h2>Result</h2><pre>{{ result }}</pre>{% endif %}
"""

ALLOWED = (".pdf", ".txt")


def handle_upload():
    """Return (result_dict, error_message, status_code)."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return None, "Please choose a file.", 400
    if not upload.filename.lower().endswith(ALLOWED):
        return None, "Only .pdf and .txt files are supported.", 400
    try:
        text = extract_text(upload.read(), upload.filename)
        return parse_document(text), None, 200
    except ValueError as exc:
        return None, str(exc), 400
    except Exception:
        return None, "Could not read that file.", 400


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(PAGE)
    result, error, status = handle_upload()
    pretty = None
    if result is not None:
        import json

        pretty = json.dumps(result, indent=2)
    return render_template_string(PAGE, result=pretty, error=error), status


@app.route("/api/parse", methods=["POST"])
def api_parse():
    result, error, status = handle_upload()
    if error:
        return jsonify({"error": error}), status
    return jsonify(result)


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "File is too large (2 MB max)."}), 413


if __name__ == "__main__":
    app.run(debug=True)
