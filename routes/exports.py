import csv
from io import StringIO

from flask import request, session, Response

from app_core import app
from helpers import db, now, login_required

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

