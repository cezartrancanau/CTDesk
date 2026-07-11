import os

from flask import render_template, request, redirect, url_for, session, flash, send_from_directory, abort

from app_core import app
from helpers import (
    db, now, login_required, calculate_sla, save_ticket_tags,
    save_ticket_attachment, log_activity, filter_label
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
        tags = request.form.get("tags", "")

        if session.get("role") == "customer":
            customer_id = session.get("customer_id")
            assigned_to = None
            priority = "Unclassified"
        else:
            customer_id = request.form["customer_id"]
            assigned_to = request.form.get("assigned_to") or None
            priority = request.form["priority"]

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

            sla_due_at = old["sla_due_at"]
            if priority != old["priority"]:
                # SLA always uses the original ticket creation time. Selecting
                # Unclassified pauses SLA tracking until staff completes triage.
                sla_due_at = calculate_sla(priority, old["created_at"])

            conn.execute("""
                UPDATE tickets
                SET status=?, priority=?, category=?, assigned_to=?, updated_at=?, resolved_at=?, sla_due_at=?
                WHERE id=?
            """, (status, priority, category, assigned_to, now(), resolved_at, sla_due_at, ticket_id))
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

    overdue = (
        ticket["status"] not in ("Resolved", "Closed")
        and ticket["sla_due_at"] is not None
        and ticket["sla_due_at"] < now()
    )

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
