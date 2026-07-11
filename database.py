import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime

DB_NAME = "ctdesk.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    DROP TABLE IF EXISTS activity_logs;
    DROP TABLE IF EXISTS ticket_attachments;
    DROP TABLE IF EXISTS ticket_messages;
    DROP TABLE IF EXISTS ticket_tags;
    DROP TABLE IF EXISTS tickets;
    DROP TABLE IF EXISTS knowledge_base;
    DROP TABLE IF EXISTS customers;
    DROP TABLE IF EXISTS users;

    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'agent', 'customer')),
        created_at TEXT NOT NULL
    );

    CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT,
        company TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE tickets (
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

    CREATE TABLE ticket_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        message_type TEXT NOT NULL CHECK(message_type IN ('public_reply', 'internal_note')),
        created_at TEXT NOT NULL,
        FOREIGN KEY(ticket_id) REFERENCES tickets(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE ticket_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        original_filename TEXT NOT NULL,
        stored_filename TEXT NOT NULL,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY(ticket_id) REFERENCES tickets(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE ticket_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        FOREIGN KEY(ticket_id) REFERENCES tickets(id),
        UNIQUE(ticket_id, tag)
    );

    CREATE TABLE activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(ticket_id) REFERENCES tickets(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE knowledge_base (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        content TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id)
    );
    """)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    users = [
        ("Admin User", "admin@ctdesk.local", generate_password_hash("admin123"), "admin", now),
        ("Support Agent", "agent@ctdesk.local", generate_password_hash("agent123"), "agent", now),
        ("Customer One", "customer1@ctdesk.local", generate_password_hash("customer123"), "customer", now),
        ("Customer Two", "customer2@ctdesk.local", generate_password_hash("customer123"), "customer", now),
    ]

    cur.executemany(
        "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
        users
    )

    customers = [
        (3, "Customer One", "customer1@ctdesk.local", "+40711111111", "BlueSoft", now),
        (4, "Customer Two", "customer2@ctdesk.local", "+40722222222", "TechNova", now),
    ]

    cur.executemany(
        "INSERT INTO customers (user_id, name, email, phone, company, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        customers
    )

    # No default tickets are inserted. Customers can log in and create new tickets themselves.

    articles = [
        ("How to reset a password", "Account Access", "Steps: verify email, send reset link, confirm login, document the solution.", 1, now),
        ("Troubleshooting Windows software issues", "Technical Support", "Check updates, restart service, inspect logs, reinstall if needed.", 1, now),
    ]

    cur.executemany(
        "INSERT INTO knowledge_base (title, category, content, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        articles
    )

    conn.commit()
    conn.close()
    print("Database created successfully.")


if __name__ == "__main__":
    init_db()
