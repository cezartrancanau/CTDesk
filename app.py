import csv
import sqlite3
from io import StringIO
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import check_password_hash, generate_password_hash

DB_NAME = "ctdesk.db"

app = Flask(__name__)
app.secret_key = "change-this-secret-key"


def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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

    stats = {
        "total": conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0],
        "open": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='Open'").fetchone()[0],
        "progress": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='In Progress'").fetchone()[0],
        "resolved": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='Resolved'").fetchone()[0],
        "closed": conn.execute("SELECT COUNT(*) FROM tickets WHERE status='Closed'").fetchone()[0],
        "overdue": conn.execute("SELECT COUNT(*) FROM tickets WHERE status NOT IN ('Resolved', 'Closed') AND sla_due_at < ?", (now(),)).fetchone()[0],
    }

    recent_tickets = conn.execute("""
        SELECT t.*, c.name AS customer_name, u.name AS agent_name
        FROM tickets t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN users u ON u.id = t.assigned_to
        ORDER BY t.created_at DESC
        LIMIT 8
    """).fetchall()

    priority_rows = conn.execute("""
        SELECT priority, COUNT(*) AS count
        FROM tickets
        GROUP BY priority
    """).fetchall()

    conn.close()
    return render_template("dashboard.html", stats=stats, recent_tickets=recent_tickets, priority_rows=priority_rows)


@app.route("/tickets")
@login_required
def tickets():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()

    query = """
        SELECT t.*, c.name AS customer_name, c.email AS customer_email, u.name AS agent_name
        FROM tickets t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN users u ON u.id = t.assigned_to
        WHERE 1=1
    """
    params = []

    if q:
        query += " AND (t.subject LIKE ? OR t.description LIKE ? OR c.name LIKE ? OR c.email LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])

    if status:
        query += " AND t.status = ?"
        params.append(status)

    if priority:
        query += " AND t.priority = ?"
        params.append(priority)

    query += " ORDER BY t.updated_at DESC"

    conn = db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return render_template("tickets.html", tickets=rows, q=q, status=status, priority=priority)


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
        conn.commit()
        conn.close()

        log_activity(ticket_id, "Ticket created")
        flash("Ticket created successfully.", "success")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    conn.close()
    return render_template("create_ticket.html", customers=customers, agents=agents)


@app.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def ticket_detail(ticket_id):
    conn = db()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update":
            old = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()

            status = request.form["status"]
            priority = request.form["priority"]
            assigned_to = request.form.get("assigned_to") or None

            resolved_at = old["resolved_at"]
            if status in ("Resolved", "Closed") and not resolved_at:
                resolved_at = now()
            if status not in ("Resolved", "Closed"):
                resolved_at = None

            conn.execute("""
                UPDATE tickets
                SET status=?, priority=?, assigned_to=?, updated_at=?, resolved_at=?
                WHERE id=?
            """, (status, priority, assigned_to, now(), resolved_at, ticket_id))

            conn.commit()
            log_activity(ticket_id, f"Ticket updated: status={status}, priority={priority}")

        elif action == "message":
            message = request.form["message"]
            message_type = request.form["message_type"]

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
        ORDER BY m.created_at ASC
    """, (ticket_id,)).fetchall()

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
        logs=logs,
        overdue=overdue
    )


@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    conn = db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO customers (name, email, phone, company, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            request.form["name"],
            request.form["email"],
            request.form["phone"],
            request.form["company"],
            now()
        ))
        conn.commit()
        flash("Customer added.", "success")

    rows = conn.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("customers.html", customers=rows)


@app.route("/knowledge-base", methods=["GET", "POST"])
@login_required
def knowledge_base():
    conn = db()

    if request.method == "POST":
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


@app.route("/export/tickets.csv")
@login_required
def export_tickets():
    conn = db()
    rows = conn.execute("""
        SELECT t.id, t.subject, t.category, t.priority, t.status, c.name AS customer,
               c.email AS customer_email, u.name AS agent, t.created_at, t.updated_at, t.sla_due_at, t.resolved_at
        FROM tickets t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN users u ON u.id = t.assigned_to
        ORDER BY t.created_at DESC
    """).fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Subject", "Category", "Priority", "Status", "Customer", "Customer Email", "Agent", "Created", "Updated", "SLA Due", "Resolved"])

    for r in rows:
        writer.writerow(list(r))

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ctdesk_tickets.csv"}
    )


if __name__ == "__main__":
    app.run(debug=True)
