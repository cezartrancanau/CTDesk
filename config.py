import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_NAME = os.environ.get("CTDESK_DB", str(BASE_DIR / "ctdesk.db"))
UPLOAD_FOLDER = os.environ.get("CTDESK_UPLOADS", str(BASE_DIR / "uploads"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "log", "doc", "docx", "xls", "xlsx", "zip"}
MAX_CONTENT_LENGTH = 8 * 1024 * 1024
