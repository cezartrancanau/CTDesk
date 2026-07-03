import csv
import os
import sqlite3
from io import StringIO
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, send_from_directory, abort
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

DB_NAME = "ctdesk.db"
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "txt", "log", "doc", "docx", "xls", "xlsx", "zip"}

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


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


def calculate_sla(priority):
    hours = {
        "Urgent": 4,
        "High": 8,
        "Medium": 24,
        "Low": 48,
    }.get(priority, 24)
    return (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


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


@app.context_processor
def inject_user():
    return {"current_user": session}


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "customer":
                conn = db()
                customer = conn.execute("SELECT id FROM customers WHERE user_id = ?", (user["id"],)).fetchone()
                conn.close()
                session["customer_id"] = customer["id"] if customer else None

            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = db()
    customer_id = get_customer_id_for_user(conn)
    where_sql = "WHERE customer_id = ?" if session.get("role") == "customer" else ""
    params = [customer_id] if session.get("role") == "customer" else []

    stats = {
        "total": conn.execute(f"SELECT COUNT(*) FROM tickets {where_sql}", params).fetchone()[0],
        "open": conn.execute(f"SELECT COUNT(*) FROM tickets {where_sql} {'AND' if where_sql else 'WHERE'} status='Open'", params).fetchone()[0],
        "progress": conn.execute(f"SELECT COUNT(*) FROM tickets {where_sql} {'AND' if where_sql else 'WHERE'} status='In Progress'", params).fetchone()[0],
        "resolved": conn.execute(f"SELECT COUNT(*) FROM tickets {where_sql} {'AND' if where_sql else 'WHERE'} status='Resolved'", params).fetchone()[0],
        "closed": conn.execute(f"SELECT COUNT(*) FROM tickets {where_sql} {'AND' if where_sql else 'WHERE'} status='Closed'", params).fetchone()[0],
        "high_priority": conn.execute(f"SELECT COUNT(*) FROM tickets {where_sql} {'AND' if where_sql else 'WHERE'} priority IN ('High', 'Urgent')", params).fetchone()[0],
        "overdue": conn.execute(f"SELECT COUNT(*) FROM tickets {where_sql} {'AND' if where_sql else 'WHERE'} status NOT IN ('Resolved', 'Closed') AND sla_due_at < ?", params + [now()]).fetchone()[0],
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] if session.get("role") != "customer" else 1,
        "agents": conn.execute("SELECT COUNT(*) FROM users WHERE role IN ('admin', 'agent')").fetchone()[0] if session.get("role") != "customer" else 0,
    }

    recent_tickets = conn.execute(f"""
        SELECT t.*, c.name AS customer_name, u.name AS agent_name
        FROM tickets t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN users u ON u.id = t.assigned_to
        {where_sql}
        ORDER BY t.created_at DESC
        LIMIT 8
    """, params).fetchall()

    priority_rows = conn.execute(f"""
        SELECT priority, COUNT(*) AS count
        FROM tickets
        {where_sql}
        GROUP BY priority
        ORDER BY count DESC
    """, params).fetchall()

    status_rows = conn.execute(f"""
        SELECT status, COUNT(*) AS count
        FROM tickets
        {where_sql}
        GROUP BY status
        ORDER BY count DESC
    """, params).fetchall()

    category_rows = conn.execute(f"""
        SELECT category, COUNT(*) AS count
        FROM tickets
        {where_sql}
        GROUP BY category
        ORDER BY count DESC
        LIMIT 6
    """, params).fetchall()

    agent_rows = []
    if session.get("role") != "customer":
        agent_rows = conn.execute("""
            SELECT COALESCE(u.name, 'Unassigned') AS agent_name, COUNT(t.id) AS count
            FROM tickets t
            LEFT JOIN users u ON u.id = t.assigned_to
            WHERE t.status NOT IN ('Resolved', 'Closed')
            GROUP BY COALESCE(u.name, 'Unassigned')
            ORDER BY count DESC
        """).fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        stats=stats,
        recent_tickets=recent_tickets,
        priority_rows=priority_rows,
        status_rows=status_rows,
        category_rows=category_rows,
        agent_rows=agent_rows
    )


@app.route("/tickets")
@login_required
def tickets():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    category = request.args.get("category", "").strip()
    tag = request.args.get("tag", "").strip().lower()
    quick = request.args.get("quick", "").strip()

    query = """
        SELECT t.*, c.name AS customer_name, c.email AS customer_email, u.name AS agent_name,
               GROUP_CONCAT(tt.tag, ', ') AS tags
        FROM tickets t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN users u ON u.id = t.assigned_to
        LEFT JOIN ticket_tags tt ON tt.ticket_id = t.id
        WHERE 1=1
    """
    params = []

    if session.get("role") == "customer":
        query += " AND t.customer_id = ?"
        params.append(session.get("customer_id"))

    if q:
        query += " AND (CAST(t.id AS TEXT) LIKE ? OR t.subject LIKE ? OR t.description LIKE ? OR c.name LIKE ? OR c.email LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like, like])

    if status:
        query += " AND t.status = ?"
        params.append(status)

    if priority:
        query += " AND t.priority = ?"
        params.append(priority)

    if category:
        query += " AND t.category = ?"
        params.append(category)

    if tag:
        query += " AND EXISTS (SELECT 1 FROM ticket_tags x WHERE x.ticket_id = t.id AND x.tag = ?)"
        params.append(tag)

    if quick == "my" and session.get("role") in ("admin", "agent"):
        query += " AND t.assigned_to = ?"
        params.append(session.get("user_id"))
    elif quick == "high":
        query += " AND t.priority IN ('High', 'Urgent')"
    elif quick == "overdue":
        query += " AND t.status NOT IN ('Resolved', 'Closed') AND t.sla_due_at < ?"
        params.append(now())
    elif quick == "unassigned" and session.get("role") in ("admin", "agent"):
        query += " AND t.assigned_to IS NULL"
    elif quick == "open":
        query += " AND t.status IN ('Open', 'In Progress')"

    query += " GROUP BY t.id ORDER BY t.updated_at DESC"

    conn = db()
    rows = conn.execute(query, params).fetchall()
    categories = conn.execute("SELECT DISTINCT category FROM tickets ORDER BY category").fetchall()
    tags = conn.execute("SELECT tag, COUNT(*) AS count FROM ticket_tags GROUP BY tag ORDER BY count DESC, tag LIMIT 20").fetchall()
    conn.close()

    return render_template(
        "tickets.html", tickets=rows, q=q, status=status, priority=priority,
        category=category, tag=tag, quick=quick, categories=categories, tags=tags,
        filter_label=filter_label(q, status, priority, category, tag, quick)
    )


@app.route("/tickets/create", methods=["GET", "POST"])
@login_required
def create_ticket():
    conn = db()
    customers = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
    agents = conn.execute("SELECT * FROM users WHERE role IN ('admin', 'agent') ORDER BY name").fetchall()

    if request.method == "POST":
        subject = request.form["subject"]
        description = request.form["description"]
        category = request.form["category"]
        priority = request.form["priority"]
        tags = request.form.get("tags", "")

        if session.get("role") == "customer":
            customer_id = session.get("customer_id")
            assigned_to = None
        else:
            customer_id = request.form["customer_id"]
            assigned_to = request.form.get("assigned_to") or None

        cur = conn.execute("""
            INSERT INTO tickets
            (subject, description, category, priority, status, customer_id, assigned_to, created_by,
             created_at, updated_at, sla_due_at)
            VALUES (?, ?, ?, ?, 'Open', ?, ?, ?, ?, ?, ?)
        """, (
            subject, description, category, priority, customer_id, assigned_to,
            session["user_id"], now(), now(), calculate_sla(priority)
        ))

        ticket_id = cur.lastrowid
        save_ticket_tags(conn, ticket_id, tags)

        attachment = request.files.get("attachment")
        attachment_saved = save_ticket_attachment(attachment, ticket_id, conn)

        conn.commit()
        conn.close()

        log_activity(ticket_id, "Ticket created")
        if attachment_saved:
            log_activity(ticket_id, "Attachment uploaded")
        log_activity(ticket_id, "Fake email notification sent to support team")
        print(f"[FAKE EMAIL] New ticket #{ticket_id} created. Notification sent to support team.")
        flash("Ticket created successfully. Fake email notification sent to support team.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    conn.close()
    return render_template("create_ticket.html", customers=customers, agents=agents)


@app.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def ticket_detail(ticket_id):
    conn = db()

    existing_ticket = conn.execute("SELECT customer_id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not existing_ticket:
        conn.close()
        flash("Ticket not found.", "danger")
        return redirect(url_for("tickets"))

    if session.get("role") == "customer" and existing_ticket["customer_id"] != session.get("customer_id"):
        conn.close()
        flash("You can only view your own tickets.", "danger")
        return redirect(url_for("tickets"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update":
            if session.get("role") not in ("admin", "agent"):
                flash("Only staff can update ticket status, priority or assigned agent.", "danger")
                conn.close()
                return redirect(url_for("ticket_detail", ticket_id=ticket_id))

            old = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()

            status = request.form["status"]
            priority = request.form["priority"]
            assigned_to = request.form.get("assigned_to") or None
            category = request.form.get("category", old["category"])
            tags = request.form.get("tags", "")

            resolved_at = old["resolved_at"]
            if status in ("Resolved", "Closed") and not resolved_at:
                resolved_at = now()
            if status not in ("Resolved", "Closed"):
                resolved_at = None

            conn.execute("""
                UPDATE tickets
                SET status=?, priority=?, category=?, assigned_to=?, updated_at=?, resolved_at=?
                WHERE id=?
            """, (status, priority, category, assigned_to, now(), resolved_at, ticket_id))
            save_ticket_tags(conn, ticket_id, tags)

            conn.commit()
            log_activity(ticket_id, f"Ticket updated: status={status}, priority={priority}, category={category}")

        elif action == "reopen":
            current = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if current and current["status"] in ("Resolved", "Closed"):
                conn.execute("""
                    UPDATE tickets
                    SET status='Open', resolved_at=NULL, updated_at=?
                    WHERE id=?
                """, (now(), ticket_id))
                conn.commit()
                log_activity(ticket_id, "Ticket reopened")
                flash("Ticket reopened.", "success")
            else:
                flash("Only resolved or closed tickets can be reopened.", "warning")

        elif action == "attachment":
            attachment = request.files.get("attachment")
            if save_ticket_attachment(attachment, ticket_id, conn):
                conn.execute("UPDATE tickets SET updated_at=? WHERE id=?", (now(), ticket_id))
                conn.commit()
                log_activity(ticket_id, "Attachment uploaded")
                flash("Attachment uploaded.", "success")
            else:
                conn.commit()

        elif action == "message":
            message = request.form["message"]
            message_type = request.form.get("message_type", "public_reply")
            if session.get("role") == "customer":
                message_type = "public_reply"

            conn.execute("""
                INSERT INTO ticket_messages (ticket_id, user_id, message, message_type, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (ticket_id, session["user_id"], message, message_type, now()))

            conn.execute("UPDATE tickets SET updated_at=? WHERE id=?", (now(), ticket_id))
            conn.commit()
            log_activity(ticket_id, "Added " + ("internal note" if message_type == "internal_note" else "public reply"))

        flash("Ticket updated.", "success")
        conn.close()
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    ticket = conn.execute("""
        SELECT t.*, c.name AS customer_name, c.email AS customer_email, c.phone, c.company,
               u.name AS agent_name
        FROM tickets t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN users u ON u.id = t.assigned_to
        WHERE t.id=?
    """, (ticket_id,)).fetchone()

    agents = conn.execute("SELECT * FROM users ORDER BY name").fetchall()

    messages = conn.execute("""
        SELECT m.*, u.name AS user_name
        FROM ticket_messages m
        JOIN users u ON u.id = m.user_id
        WHERE m.ticket_id=?
        {message_filter}
        ORDER BY m.created_at ASC
    """.format(message_filter="AND m.message_type != 'internal_note'" if session.get("role") == "customer" else ""), (ticket_id,)).fetchall()

    attachments = conn.execute("""
        SELECT a.*, u.name AS user_name
        FROM ticket_attachments a
        JOIN users u ON u.id = a.user_id
        WHERE a.ticket_id=?
        ORDER BY a.uploaded_at DESC
    """, (ticket_id,)).fetchall()

    tag_rows = conn.execute("SELECT tag FROM ticket_tags WHERE ticket_id=? ORDER BY tag", (ticket_id,)).fetchall()
    ticket_tags = ", ".join([r["tag"] for r in tag_rows])

    logs = conn.execute("""
        SELECT l.*, u.name AS user_name
        FROM activity_logs l
        JOIN users u ON u.id = l.user_id
        WHERE l.ticket_id=?
        ORDER BY l.created_at DESC
    """, (ticket_id,)).fetchall()

    conn.close()

    if not ticket:
        flash("Ticket not found.", "danger")
        return redirect(url_for("tickets"))

    overdue = ticket["status"] not in ("Resolved", "Closed") and ticket["sla_due_at"] < now()

    return render_template(
        "ticket_detail.html",
        ticket=ticket,
        agents=agents,
        messages=messages,
        attachments=attachments,
        logs=logs,
        overdue=overdue,
        ticket_tags=ticket_tags
    )


@app.route("/customers", methods=["GET", "POST"])
@login_required
@staff_required
def customers():
    conn = db()

    if request.method == "POST":
        customer_name = request.form["name"]
        customer_email = request.form["email"].strip().lower()
        customer_password = request.form.get("password") or "customer123"

        cur = conn.execute("""
            INSERT INTO users (name, email, password_hash, role, created_at)
            VALUES (?, ?, ?, 'customer', ?)
        """, (
            customer_name,
            customer_email,
            generate_password_hash(customer_password),
            now()
        ))
        user_id = cur.lastrowid

        conn.execute("""
            INSERT INTO customers (user_id, name, email, phone, company, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            customer_name,
            customer_email,
            request.form["phone"],
            request.form["company"],
            now()
        ))
        conn.commit()
        flash("Customer account added.", "success")

    rows = conn.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("customers.html", customers=rows)


@app.route("/knowledge-base", methods=["GET", "POST"])
@login_required
@staff_required
def knowledge_base():
    conn = db()

    if request.method == "POST":
        if session.get("role") != "admin":
            flash("Only admins can create knowledge base articles.", "danger")
            conn.close()
            return redirect(url_for("knowledge_base"))

        conn.execute("""
            INSERT INTO knowledge_base (title, category, content, created_by, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            request.form["title"],
            request.form["category"],
            request.form["content"],
            session["user_id"],
            now()
        ))
        conn.commit()
        flash("Article added.", "success")

    articles = conn.execute("""
        SELECT kb.*, u.name AS author
        FROM knowledge_base kb
        JOIN users u ON u.id = kb.created_by
        ORDER BY kb.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("knowledge_base.html", articles=articles)


@app.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    conn = db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO users (name, email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["email"],
            generate_password_hash(request.form["password"]),
            request.form["role"],
            now()
        ))
        conn.commit()
        flash("User created.", "success")

    rows = conn.execute("SELECT id, name, email, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("users.html", users=rows)


@app.route("/tickets/<int:ticket_id>/attachments/<int:attachment_id>")
@login_required
def download_attachment(ticket_id, attachment_id):
    conn = db()
    ticket = conn.execute("SELECT customer_id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not ticket:
        conn.close()
        abort(404)

    if session.get("role") == "customer" and ticket["customer_id"] != session.get("customer_id"):
        conn.close()
        flash("You can only download attachments from your own tickets.", "danger")
        return redirect(url_for("tickets"))

    attachment = conn.execute(
        "SELECT * FROM ticket_attachments WHERE id = ? AND ticket_id = ?",
        (attachment_id, ticket_id)
    ).fetchone()
    conn.close()

    if not attachment:
        abort(404)

    folder = os.path.join(app.config["UPLOAD_FOLDER"], "tickets", str(ticket_id))
    return send_from_directory(folder, attachment["stored_filename"], as_attachment=True, download_name=attachment["original_filename"])


@app.route("/export/tickets.csv")
@login_required
def export_tickets():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    category = request.args.get("category", "").strip()
    tag = request.args.get("tag", "").strip().lower()
    quick = request.args.get("quick", "").strip()

    query = """
        SELECT t.id, t.subject, t.category, t.priority, t.status, c.name AS customer,
               c.email AS customer_email, u.name AS agent, GROUP_CONCAT(tt.tag, ', ') AS tags,
               t.created_at, t.updated_at, t.sla_due_at, t.resolved_at
        FROM tickets t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN users u ON u.id = t.assigned_to
        LEFT JOIN ticket_tags tt ON tt.ticket_id = t.id
        WHERE 1=1
    """
    params = []

    if session.get("role") == "customer":
        query += " AND t.customer_id = ?"
        params.append(session.get("customer_id"))
    if q:
        query += " AND (CAST(t.id AS TEXT) LIKE ? OR t.subject LIKE ? OR t.description LIKE ? OR c.name LIKE ? OR c.email LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like, like])
    if status:
        query += " AND t.status = ?"
        params.append(status)
    if priority:
        query += " AND t.priority = ?"
        params.append(priority)
    if category:
        query += " AND t.category = ?"
        params.append(category)
    if tag:
        query += " AND EXISTS (SELECT 1 FROM ticket_tags x WHERE x.ticket_id = t.id AND x.tag = ?)"
        params.append(tag)
    if quick == "my" and session.get("role") in ("admin", "agent"):
        query += " AND t.assigned_to = ?"
        params.append(session.get("user_id"))
    elif quick == "high":
        query += " AND t.priority IN ('High', 'Urgent')"
    elif quick == "overdue":
        query += " AND t.status NOT IN ('Resolved', 'Closed') AND t.sla_due_at < ?"
        params.append(now())
    elif quick == "unassigned" and session.get("role") in ("admin", "agent"):
        query += " AND t.assigned_to IS NULL"
    elif quick == "open":
        query += " AND t.status IN ('Open', 'In Progress')"

    query += " GROUP BY t.id ORDER BY t.created_at DESC"

    conn = db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Subject", "Category", "Priority", "Status", "Customer", "Customer Email", "Agent", "Tags", "Created", "Updated", "SLA Due", "Resolved"])

    for r in rows:
        writer.writerow(list(r))

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ctdesk_tickets.csv"}
    )


if __name__ == "__main__":
    app.run(debug=True)
