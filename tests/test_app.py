import os
import tempfile
import unittest
from pathlib import Path


class CTDeskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["CTDESK_DB"] = str(Path(cls.temp_dir.name) / "test.db")
        os.environ["CTDESK_UPLOADS"] = str(Path(cls.temp_dir.name) / "uploads")
        os.environ["CTDESK_SECRET_KEY"] = "test-only-secret"

        import database
        from app import app

        cls.database = database
        cls.app = app
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        self.database.init_db()
        self.client = self.app.test_client()

    def csrf(self):
        with self.client.session_transaction() as session:
            return session["_csrf_token"]

    def login(self, email, password):
        self.client.get("/login")
        return self.client.post("/login", data={
            "email": email,
            "password": password,
            "_csrf_token": self.csrf(),
        }, follow_redirects=False)

    def test_login_and_protected_redirect(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.login("agent@ctdesk.local", "agent123").status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_invalid_login(self):
        self.client.get("/login")
        response = self.client.post("/login", data={
            "email": "agent@ctdesk.local",
            "password": "wrong",
            "_csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn(b"Invalid email or password", response.data)

    def test_customer_cannot_open_another_customers_ticket(self):
        self.login("customer1@ctdesk.local", "customer123")
        response = self.client.get("/tickets/3", follow_redirects=True)
        self.assertIn(b"You can only view your own tickets", response.data)

    def test_customer_cannot_access_staff_pages(self):
        self.login("customer1@ctdesk.local", "customer123")
        self.assertEqual(self.client.get("/users", follow_redirects=False).status_code, 302)
        self.assertEqual(self.client.get("/knowledge-base", follow_redirects=False).status_code, 302)

    def test_customer_cannot_post_internal_note(self):
        self.login("customer1@ctdesk.local", "customer123")
        response = self.client.post("/tickets/1", data={
            "action": "message",
            "message": "Customer response",
            "message_type": "internal_note",
            "_csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertNotIn(b"internal note", response.data.lower())

    def test_agent_can_document_resolution(self):
        self.login("agent@ctdesk.local", "agent123")
        response = self.client.post("/tickets/1", data={
            "action": "update", "status": "Resolved", "priority": "High",
            "category": "Network", "assigned_to": "2", "tags": "vpn",
            "troubleshooting": "Cleared cached credentials and retested.",
            "root_cause": "Expired cached credentials.",
            "resolution": "User confirmed stable connection.",
            "resolution_code": "Fixed", "escalation_reason": "",
            "_csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn(b"User confirmed stable connection", response.data)
        self.assertIn(b"Fixed", response.data)

    def test_csrf_rejects_missing_token(self):
        response = self.client.post("/login", data={
            "email": "agent@ctdesk.local", "password": "agent123",
        })
        self.assertEqual(response.status_code, 400)

    def test_csv_export_respects_filter(self):
        self.login("agent@ctdesk.local", "agent123")
        response = self.client.get("/export/tickets.csv?priority=Urgent")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cannot reset Microsoft 365 password", response.data)
        self.assertNotIn(b"Office printer shows offline", response.data)


if __name__ == "__main__":
    unittest.main()
