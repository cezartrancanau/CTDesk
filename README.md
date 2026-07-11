# CTDesk

Advanced Help Desk & Customer Support Ticketing System built with **Python**, **Flask** and **SQLite**.

CTDesk is a lightweight portfolio project that demonstrates a complete support workflow with authentication, role-based access, tickets, customers, replies, attachments, SLA tracking, dashboards and CSV export.

---

## Features

### Authentication & Roles
- Secure login system
- Admin, Agent and Customer roles
- Role-based permissions

### Ticket Management
- Create, edit and assign tickets
- Ticket priorities and statuses
- SLA deadline tracking
- Ticket conversation/comments
- Public replies and internal notes
- File attachments
- Activity history
- Ticket categories: Hardware, Software, Network, Account, Printer and Other
- Ticket tags such as `printer`, `vpn`, `outlook` or `urgent`
- Reopen button for resolved or closed tickets

### Customer Portal
- Customers can create support tickets
- Customers can view only their own tickets
- Dedicated customer dashboard

### Knowledge Base
- Admin can create articles
- Agents have read-only access
- Customers cannot access the Knowledge Base

### Dashboard
- Ticket statistics
- Open/Closed ticket overview
- Tickets by status
- Tickets by category
- Agent workload overview
- High priority and SLA overdue counters

### Search, Filters & Export
- Search by ticket ID, subject, description or customer
- Filter by status, priority, category and tag
- Quick filters: My Tickets, High Priority, Overdue, Unassigned and Open/In Progress
- CSV export uses the currently selected filters

### Other Features
- Customer database
- Light/Dark mode
- Fake email notification simulation
- Windows `.bat` runner included

---

## How to run

### Option 1: Windows quick start

Double-click:

```text
run_ctdesk.bat
```

The script will:

1. Create a virtual environment if missing
2. Install the requirements
3. Create the database if missing
4. Start the Flask app

Then open:

```text
http://127.0.0.1:5000
```

### Option 2: Manual start

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

## Default Accounts

### Administrator

```text
Email: admin@ctdesk.local
Password: admin123
```

### Agent

```text
Email: agent@ctdesk.local
Password: agent123
```

### Customers

```text
Email: customer1@ctdesk.local
Password: customer123
```

```text
Email: customer2@ctdesk.local
Password: customer123
```

---

## Tech Stack

- Python
- Flask
- SQLite
- Jinja2
- HTML5
- CSS3
- Bootstrap
- JavaScript

---

## v1.0 Update

### Added

- Customer authentication system
- Customer support portal
- Ticket conversation/comments
- File attachment support
- Dashboard statistics
- Ticket search
- Ticket filtering
- Simulated email notifications
- Role-based Knowledge Base permissions

### Changed

- Removed demo tickets
- Simplified initial database
- Customers can only access their own tickets
- Knowledge Base is now:
  - **Admin:** can create articles
  - **Agent:** read-only access
  - **Customer:** no access

---

## v2.0 Update

### Added

- Ticket categories as a controlled dropdown
- Ticket tags for easier organization and filtering
- Reopen ticket functionality for resolved or closed tickets
- Quick filters for common support views:
  - My Tickets
  - High Priority
  - Overdue
  - Unassigned
  - Open/In Progress
- Improved dashboard statistics:
  - Tickets by status
  - Tickets by category
  - Agent workload overview
- Filtered CSV export
- Dark mode readability fixes so all dashboard, table, card and form text remains visible

### Improved

- Ticket list now displays category and tags
- Ticket detail page now allows staff to update category and tags
- CSV export now respects the filters selected on the Tickets page
- Dark mode CSS improved: fixed black text on dark backgrounds in cards, tables, forms and navigation

---

## v3.0 Update

### Added

- Staff-controlled ticket triage workflow
- New `Unclassified` priority for customer-created tickets
- SLA activation only after an admin or agent assigns a real priority
- Automatic SLA deadline recalculation when staff changes ticket priority
- Automatic database migration for existing CTDesk installations

### Changed

- Customers no longer select or submit ticket priority
- Customer-created tickets now start as `Unclassified` instead of `Medium`
- Unclassified tickets have no SLA deadline until staff completes triage
- SLA deadlines are calculated from the ticket's original creation time:
  - **Urgent:** 4 hours
  - **High:** 8 hours
  - **Medium:** 24 hours
  - **Low:** 48 hours
- Changing a ticket's priority recalculates its SLA deadline from the original creation time
- Resolved and closed tickets are excluded from SLA overdue tracking
- Dashboard displays `Not started` when an SLA has not yet been activated
- Priority filters and ticket controls now support `Unclassified`

### SLA Workflow

1. A customer creates a ticket without choosing priority.
2. The ticket is stored as `Unclassified` with no SLA deadline.
3. An admin or agent reviews the ticket and assigns a priority.
4. CTDesk calculates the SLA deadline from the original ticket creation time.
5. If staff later changes the priority, CTDesk recalculates the deadline using the new SLA target.
6. An unresolved ticket is marked overdue only when it has an active SLA deadline and that deadline has passed.

---

## Project Goal

CTDesk is designed as a practical help desk project for demonstrating IT support, technical support and customer support workflows. It focuses on realistic ticket management features while keeping the stack simple and beginner-friendly.
