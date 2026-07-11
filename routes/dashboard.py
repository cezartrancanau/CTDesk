from flask import render_template, session

from app_core import app
from helpers import db, now, login_required, get_customer_id_for_user

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
