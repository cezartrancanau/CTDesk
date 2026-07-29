import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

from config import DB_NAME


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
        device_name TEXT,
        asset_tag TEXT,
        operating_system TEXT,
        location TEXT,
        support_channel TEXT,
        troubleshooting TEXT,
        root_cause TEXT,
        resolution TEXT,
        resolution_code TEXT,
        escalation_reason TEXT,
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

    demo_tickets = [
        ("VPN disconnects after sign-in", "The VPN connects, then disconnects after about 30 seconds.", "Network", "High", "In Progress", 1, 2, 3, -10, 8, None, "LT-BS-014", "BS-1042", "Windows 11", "Bucharest - Remote", "Portal", "Confirmed internet access; cleared cached VPN credentials; reviewed client logs.", "Expired cached credentials after a password change.", "", "", ""),
        ("Cannot reset Microsoft 365 password", "Password reset page says the account cannot be verified.", "Account", "Urgent", "Resolved", 1, 2, 3, -30, 4, -27, "LT-BS-008", "BS-1008", "Windows 11", "Bucharest HQ", "Phone", "Verified identity using the support checklist; checked account status; issued temporary password.", "User had replaced their phone and could not complete MFA.", "Updated MFA method and confirmed successful sign-in with the user.", "Fixed", ""),
        ("Office printer shows offline", "The finance printer appears offline for everyone on the second floor.", "Printer", "Medium", "Open", 2, None, 4, -3, 24, None, "PRN-TN-02", "TN-PR-002", "Printer firmware", "Cluj - Floor 2", "Email", "Confirmed impact with two users; ping failed; asked on-site contact to check power and network cable.", "", "", "", "Requires an on-site physical connectivity check."),
        ("Outlook mailbox not synchronizing", "New messages appear on the phone but not in desktop Outlook.", "Software", "Medium", "Resolved", 2, 2, 4, -72, 24, -70, "LT-TN-023", "TN-1023", "Windows 10", "Cluj - Remote", "Portal", "Checked webmail; verified service health; started Outlook in safe mode; recreated the mail profile.", "Corrupted local Outlook profile.", "Recreated the profile and verified send/receive with the user.", "Fixed", ""),
        ("Laptop overheating during video calls", "The fan becomes very loud and the laptop shuts down during Teams calls.", "Hardware", "High", "Open", 1, 2, 3, -14, 8, None, "LT-BS-019", "BS-1019", "Windows 11", "Bucharest HQ", "Walk-up", "Checked Task Manager and vents; reproduced high temperature during a test call.", "Cooling system likely obstructed by dust.", "", "", "Escalated to hardware repair for cleaning and thermal inspection."),
        ("Request: new starter workstation", "Prepare a laptop and standard applications for a new employee starting Monday.", "Hardware", "Low", "In Progress", 2, 2, 4, -20, 48, None, "Pending allocation", "", "Windows 11", "Cluj HQ", "Email", "Confirmed manager approval, role, start date, and required applications.", "", "", "", ""),
        ("Blue screen when connecting USB dock", "The laptop restarts with a blue screen whenever the desk dock is connected.", "Hardware", "High", "Resolved", 2, 2, 4, -96, 8, -90, "LT-TN-011", "TN-1011", "Windows 11", "Cluj HQ", "Phone", "Captured stop code; tested without dock; updated dock firmware and display driver.", "Outdated dock firmware conflicted with the display driver.", "Updated firmware and driver, restarted, and tested three reconnects successfully.", "Fixed", ""),
        ("Wi-Fi slow in meeting room", "Video meetings freeze in meeting room Atlas, but work elsewhere.", "Network", "Medium", "Open", 1, None, 3, -50, 24, None, "Multiple devices", "", "Mixed", "Bucharest - Atlas", "Portal", "Confirmed issue on two laptops; signal strength is low in the room.", "Suspected wireless coverage issue.", "Provided wired-room workaround while network team reviews access-point coverage.", "Workaround", "Network infrastructure change requires escalation."),
    ]
    ticket_ids = []
    for item in demo_tickets:
        (subject, description, category, priority, status, customer_id, assigned_to,
         created_by, age_hours, sla_hours, resolved_age, device_name, asset_tag,
         operating_system, location, channel, troubleshooting, root_cause,
         resolution, resolution_code, escalation_reason) = item
        created = (datetime.now() + timedelta(hours=age_hours)).strftime("%Y-%m-%d %H:%M:%S")
        due = (datetime.now() + timedelta(hours=age_hours + sla_hours)).strftime("%Y-%m-%d %H:%M:%S")
        resolved = ((datetime.now() + timedelta(hours=resolved_age)).strftime("%Y-%m-%d %H:%M:%S")
                    if resolved_age is not None else None)
        cur.execute("""
            INSERT INTO tickets (
                subject, description, category, priority, status, customer_id, assigned_to,
                created_by, created_at, updated_at, sla_due_at, resolved_at, device_name,
                asset_tag, operating_system, location, support_channel, troubleshooting,
                root_cause, resolution, resolution_code, escalation_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (subject, description, category, priority, status, customer_id, assigned_to,
              created_by, created, now, due, resolved, device_name, asset_tag,
              operating_system, location, channel, troubleshooting, root_cause,
              resolution, resolution_code, escalation_reason))
        ticket_ids.append(cur.lastrowid)

    cur.executemany(
        "INSERT INTO ticket_tags (ticket_id, tag) VALUES (?, ?)",
        [(ticket_ids[0], "vpn"), (ticket_ids[0], "remote-work"),
         (ticket_ids[1], "microsoft-365"), (ticket_ids[2], "printer"),
         (ticket_ids[3], "outlook"), (ticket_ids[4], "hardware"),
         (ticket_ids[5], "onboarding"), (ticket_ids[6], "blue-screen"),
         (ticket_ids[7], "wifi")]
    )

    cur.executemany("""
        INSERT INTO ticket_messages (ticket_id, user_id, message, message_type, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (ticket_ids[0], 2, "I reproduced the issue and am checking the VPN client logs.", "public_reply", now),
        (ticket_ids[0], 2, "Likely linked to yesterday's password change. Test after clearing cached credentials.", "internal_note", now),
        (ticket_ids[1], 2, "Your MFA method has been updated. We confirmed that you can sign in again.", "public_reply", now),
        (ticket_ids[3], 4, "Outlook is now receiving messages normally. Thank you!", "public_reply", now),
    ])

    for ticket_id in ticket_ids:
        cur.execute(
            "INSERT INTO activity_logs (ticket_id, user_id, action, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, 1, "Demo ticket created", now)
        )

    articles = [
        ("Microsoft 365 password and MFA reset", "Account Access", "Symptoms: user cannot sign in or complete MFA.\n\nSteps:\n1. Verify the user's identity using the approved checklist.\n2. Confirm the account is enabled and not locked.\n3. Reset the password or MFA method.\n4. Ask the user to sign in and register a new method.\n5. Document the result in the ticket.\n\nEscalate when: identity cannot be verified or the account shows an administrative restriction.", 1, now),
        ("VPN connects and immediately disconnects", "Network", "Symptoms: VPN drops shortly after authentication.\n\nSteps:\n1. Confirm normal internet access.\n2. Verify date and time are correct.\n3. Check whether the password changed recently.\n4. Clear cached VPN credentials and retry.\n5. Record the client error and review logs.\n\nEscalate when: several users are affected or gateway/service health is degraded.", 1, now),
        ("Outlook is not receiving new email", "Software", "Symptoms: mail works in webmail but not desktop Outlook.\n\nSteps:\n1. Check webmail and service health.\n2. Confirm Outlook is not in offline mode.\n3. Start Outlook in safe mode.\n4. Disable the faulty add-in if identified.\n5. Recreate the mail profile if synchronization remains stuck.\n\nEscalate when: webmail is also affected or multiple users report the issue.", 1, now),
        ("Network printer appears offline", "Printer", "Symptoms: one or more users cannot print.\n\nSteps:\n1. Confirm the printer has power and no physical error.\n2. Check network cable or Wi-Fi status.\n3. Ping the printer and verify its IP address.\n4. Clear stuck print jobs and restart the spooler.\n5. Print a test page and document the outcome.\n\nEscalate when: hardware error codes remain or an on-site repair is required.", 1, now),
        ("Windows blue-screen information gathering", "Hardware", "Before escalation collect: asset tag, Windows version, stop code, recent hardware/software changes, frequency, and steps to reproduce. Disconnect non-essential peripherals, apply approved updates, and preserve logs. Do not repeatedly reproduce a crash if data loss is possible.", 1, now),
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
