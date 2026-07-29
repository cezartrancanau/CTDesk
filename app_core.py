import os
import secrets

from flask import Flask, abort, request, session

from config import MAX_CONTENT_LENGTH, UPLOAD_FOLDER

app = Flask(__name__)
app.secret_key = os.environ.get("CTDESK_SECRET_KEY", secrets.token_hex(32))
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


@app.before_request
def csrf_protection():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(24)
    if request.method == "POST" and request.form.get("_csrf_token") != session["_csrf_token"]:
        abort(400, description="Invalid or missing form security token.")


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": session.get("_csrf_token", "")}
