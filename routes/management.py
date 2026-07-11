from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash

from app_core import app
from helpers import db, now, login_required, staff_required, admin_required

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
