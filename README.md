# CTDesk

Advanced Help Desk & Customer Support Ticketing System built with **Python**, **Flask**, and **SQLite**.

---

## Features

### Authentication & Roles
- Secure login system
- Admin, Agent and Customer roles
- Customer self-registration
- Role-based permissions

### Ticket Management
- Create, edit and assign tickets
- Ticket priorities and statuses
- SLA deadline tracking
- Ticket conversation/comments
- Public replies and internal notes
- File attachments
- Activity history

### Customer Portal
- Customers can create support tickets
- Customers can view only their own tickets
- Dedicated customer dashboard

### Knowledge Base
- Admin can create, edit and delete articles
- Agents have read-only access
- Customers cannot access the Knowledge Base

### Dashboard
- Ticket statistics
- Open/Closed ticket overview
- Search tickets
- Filter by status and priority

### Other Features
- Customer database
- CSV export
- Light/Dark mode
- Fake email notification simulation

---

# How to run

```bash
pip install -r requirements.txt
python database.py
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

---

# Default Accounts

## Administrator

```text
Email: admin@ctdesk.local
Password: admin123
```

## Agent

```text
Email: agent@ctdesk.local
Password: agent123
```

## Customers

```text
Email: customer1@ctdesk.local
Password: customer123
```

```text
Email: customer2@ctdesk.local
Password: customer123
```

---

# Tech Stack

- Python
- Flask
- SQLite
- SQLAlchemy
- Jinja2
- HTML5
- CSS3
- Bootstrap
- JavaScript

---

# v1.0 Update

## Added

- Customer authentication system
- Customer self-registration
- Customer support portal
- Ticket conversation/comments
- File attachment support
- Dashboard statistics
- Ticket search
- Ticket filtering
- Simulated email notifications
- Role-based Knowledge Base permissions

## Changed

- Removed demo tickets
- Simplified initial database
- Customers can only access their own tickets
- Knowledge Base is now:
  - **Admin:** full access
  - **Agent:** read-only
  - **Customer:** no access

---

CTDesk is a lightweight Help Desk application designed to demonstrate a complete ticket management workflow with authentication, role-based authorization, customer support, and administrative tools.