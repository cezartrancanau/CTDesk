import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import session, flash, redirect, url_for
from werkzeug.utils import secure_filename

from app_core import app
from config import DB_NAME, ALLOWED_EXTENSIONS

def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_ticket_attachment(file, ticket_id, conn):
    if not file or not file.filename:
        return False

    if not allowed_file(file.filename):
        flash("Attachment type is not allowed.", "danger")
        return False

    original_filename = secure_filename(file.filename)
    ticket_folder = os.path.join(app.config["UPLOAD_FOLDER"], "tickets", str(ticket_id))
    os.makedirs(ticket_folder, exist_ok=True)

    stored_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_filename}"
    file.save(os.path.join(ticket_folder, stored_filename))

    conn.execute("""
        INSERT INTO ticket_attachments
        (ticket_id, user_id, original_filename, stored_filename, uploaded_at)
        VALUES (?, ?, ?, ?, ?)
    """, (ticket_id, session["user_id"], original_filename, stored_filename, now()))
    return True


def ensure_schema():
    conn = db()

    # v3 migration: allow tickets to remain unclassified until staff triage
    tickets_table = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tickets'"
    ).fetchone()
    if tickets_table and (
        "Unclassified" not in tickets_table["sql"]
        or "sla_due_at TEXT NOT NULL" in tickets_table["sql"]
    ):
        conn.executescript("""
            CREATE TABLE tickets_v3 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL CHECK(priority IN ('Unclassified', 'Low', 'Medium', 'High', 'Urgent')),
                status TEXT NOT NULL CHECK(status IN ('Open', 'In Progress', 'Resolved', 'Closed')),
                customer_id INTEGER NOT NULL,
                assigned_to INTEGER,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sla_due_at TEXT,
                resolved_at TEXT,
                FOREIGN KEY(customer_id) REFERENCES customers(id),
                FOREIGN KEY(assigned_to) REFERENCES users(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            INSERT INTO tickets_v3 (
                id, subject, description, category, priority, status, customer_id, assigned_to,
                created_by, created_at, updated_at, sla_due_at, resolved_at
            )
            SELECT id, subject, description, category, priority, status, customer_id, assigned_to,
                   created_by, created_at, updated_at, sla_due_at, resolved_at
            FROM tickets;

            DROP TABLE tickets;
            ALTER TABLE tickets_v3 RENAME TO tickets;
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            UNIQUE(ticket_id, tag)
        )
    """)
    conn.commit()
    conn.close()


def parse_tags(raw_tags):
    tags = []
    for tag in raw_tags.split(','):
        clean = tag.strip().lower().replace(' ', '-')
        if clean and clean not in tags:
            tags.append(clean[:30])
    return tags[:8]


def save_ticket_tags(conn, ticket_id, raw_tags):
    conn.execute("DELETE FROM ticket_tags WHERE ticket_id = ?", (ticket_id,))
    for tag in parse_tags(raw_tags or ''):
        conn.execute("INSERT OR IGNORE INTO ticket_tags (ticket_id, tag) VALUES (?, ?)", (ticket_id, tag))


def filter_label(q, status, priority, category, tag, quick):
    active = []
    if q:
        active.append(f"search: {q}")
    if status:
        active.append(f"status: {status}")
    if priority:
        active.append(f"priority: {priority}")
    if category:
        active.append(f"category: {category}")
    if tag:
        active.append(f"tag: {tag}")
    if quick:
        active.append(f"quick: {quick}")
    return ", ".join(active) if active else "all tickets"


ensure_schema()


def calculate_sla(priority, start_time=None):
    hours = {
        "Urgent": 4,
        "High": 8,
        "Medium": 24,
        "Low": 48,
    }.get(priority)

    if hours is None:
        return None

    if start_time:
        start = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    else:
        start = datetime.now()

    return (start + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper


def staff_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("admin", "agent"):
            flash("Staff access required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper


def get_customer_id_for_user(conn):
    if session.get("role") != "customer":
        return None
    customer = conn.execute("SELECT id FROM customers WHERE user_id = ?", (session["user_id"],)).fetchone()
    return customer["id"] if customer else None


def log_activity(ticket_id, action):
    conn = db()
    conn.execute(
        "INSERT INTO activity_logs (ticket_id, user_id, action, created_at) VALUES (?, ?, ?, ?)",
        (ticket_id, session["user_id"], action, now())
    )
    conn.commit()
    conn.close()
