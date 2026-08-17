"""Sprint 8 private messaging, authorization, history, and schema tests."""

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-only-secret"

from app import app, db  # noqa: E402
from messaging import inbox_page, unread_conversation_count, utc_now  # noqa: E402
from models import ConnectionRequest, Conversation, Message, Profile, User  # noqa: E402


class MessagingFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()
            self.alice = self.make_user("Alice")
            self.bob = self.make_user("Bob")
            self.cara = self.make_user("Cara")
            db.session.flush()
            self.ids = {user.first_name: user.id for user in (self.alice, self.bob, self.cara)}
            self.connect("Alice", "Bob")
            db.session.commit()
        self.client = app.test_client()
        self.login("Alice")

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    def make_user(self, name):
        user = User(
            first_name=name,
            last_name="Private",
            email=f"{name.lower()}@example.com",
            password_hash="hash",
            date_of_birth=date(1990, 1, 1),
        )
        user.profile = Profile(
            gender="woman",
            bio=f"About {name}",
            profile_photo_key=None,
            home_country_code="UA",
            home_city="Private city",
            discovery_country_code="IE",
            discovery_city="Dublin",
            open_to_connections=True,
        )
        db.session.add(user)
        return user

    def connect(self, first, second):
        first_user = getattr(self, first.lower())
        second_user = getattr(self, second.lower())
        low, high = sorted((first_user.id, second_user.id))
        relationship = ConnectionRequest(
            sender_id=first_user.id,
            recipient_id=second_user.id,
            pair_low_id=low,
            pair_high_id=high,
            status="accepted",
            responded_at=utc_now(),
        )
        db.session.add(relationship)
        return relationship

    def login(self, name):
        with self.client.session_transaction() as browser_session:
            browser_session["user_id"] = self.ids[name]

    def start(self, target="Bob"):
        return self.client.get(f"/messages/start/{self.ids[target]}", follow_redirects=False)

    def conversation_id(self):
        with app.app_context():
            return db.session.scalar(db.select(Conversation.id))

    def test_authentication_guards_all_messaging_routes(self):
        self.client.get("/logout")
        with self.client.session_transaction() as browser_session:
            browser_session.clear()
        for method, url in (("get", "/messages"), ("get", f"/messages/start/{self.ids['Bob']}"), ("get", "/messages/1"), ("post", "/messages/1/send")):
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("/login", response.headers["Location"])

    def test_only_accepted_connection_can_start_and_pair_is_unique(self):
        blocked = self.client.get(f"/messages/start/{self.ids['Cara']}")
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(self.start().status_code, 302)
        first_id = self.conversation_id()
        self.assertEqual(self.start().status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Conversation.id))), 1)
        self.login("Bob")
        self.start("Alice")
        self.assertEqual(self.conversation_id(), first_id)

    def test_self_and_missing_start_do_not_create_conversations(self):
        self.assertEqual(self.client.get(f"/messages/start/{self.ids['Alice']}").status_code, 404)
        self.assertEqual(self.client.get("/messages/start/999999").status_code, 404)
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Conversation.id))), 0)

    def test_send_trims_plain_text_and_ignores_forged_sender(self):
        self.start()
        conversation_id = self.conversation_id()
        response = self.client.post(
            f"/messages/{conversation_id}/send",
            data={"body": "  <script>alert(1)</script> hello  ", "sender_id": self.ids["Bob"]},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<script>alert", response.data)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt; hello", response.data)
        with app.app_context():
            message = db.session.scalar(db.select(Message))
            self.assertEqual(message.sender_id, self.ids["Alice"])
            self.assertEqual(message.body, "<script>alert(1)</script> hello")

    def test_blank_and_overlong_messages_are_rejected(self):
        self.start()
        conversation_id = self.conversation_id()
        for body in ("   ", "x" * 2001):
            self.client.post(f"/messages/{conversation_id}/send", data={"body": body})
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Message.id))), 0)

    def test_idor_blocks_non_participant_from_history_and_send(self):
        self.start()
        conversation_id = self.conversation_id()
        self.login("Cara")
        self.assertEqual(self.client.get(f"/messages/{conversation_id}").status_code, 404)
        self.assertEqual(self.client.post(f"/messages/{conversation_id}/send", data={"body": "intrusion"}).status_code, 404)

    def test_removal_preserves_history_and_makes_conversation_read_only(self):
        self.start()
        conversation_id = self.conversation_id()
        self.client.post(f"/messages/{conversation_id}/send", data={"body": "Still here"})
        with app.app_context():
            db.session.execute(db.delete(ConnectionRequest))
            db.session.commit()
        page = self.client.get(f"/messages/{conversation_id}")
        self.assertIn(b"Still here", page.data)
        self.assertIn(b"read-only", page.data)
        self.client.post(f"/messages/{conversation_id}/send", data={"body": "blocked"})
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Message.id))), 1)

    def test_reconnection_reuses_history_and_restores_sending(self):
        self.start()
        conversation_id = self.conversation_id()
        with app.app_context():
            db.session.execute(db.delete(ConnectionRequest))
            db.session.commit()
            self.alice = db.session.get(User, self.ids["Alice"])
            self.bob = db.session.get(User, self.ids["Bob"])
            self.connect("Alice", "Bob")
            db.session.commit()
        self.assertIn(str(conversation_id), self.start().headers["Location"])
        self.client.post(f"/messages/{conversation_id}/send", data={"body": "Back again"})
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Message.id))), 1)

    def test_open_marks_only_received_messages_read_and_count_is_by_conversation(self):
        self.start()
        conversation_id = self.conversation_id()
        now = utc_now()
        with app.app_context():
            db.session.add_all([
                Message(conversation_id=conversation_id, sender_id=self.ids["Bob"], body="One", created_at=now),
                Message(conversation_id=conversation_id, sender_id=self.ids["Bob"], body="Two", created_at=now),
                Message(conversation_id=conversation_id, sender_id=self.ids["Alice"], body="Mine", created_at=now),
            ])
            db.session.commit()
            self.assertEqual(unread_conversation_count(db.session, self.ids["Alice"]), 1)
        self.client.get(f"/messages/{conversation_id}")
        with app.app_context():
            incoming = list(db.session.scalars(db.select(Message).where(Message.sender_id == self.ids["Bob"])))
            mine = db.session.scalar(db.select(Message).where(Message.sender_id == self.ids["Alice"]))
            self.assertTrue(all(message.read_at is not None for message in incoming))
            self.assertIsNone(mine.read_at)
            self.assertEqual(unread_conversation_count(db.session, self.ids["Alice"]), 0)

    def test_inbox_order_preview_and_read_only_state(self):
        self.start()
        conversation_id = self.conversation_id()
        with app.app_context():
            conversation = db.session.get(Conversation, conversation_id)
            conversation.last_activity_at = utc_now()
            db.session.add(Message(conversation_id=conversation_id, sender_id=self.ids["Bob"], body="A   useful\npreview", created_at=utc_now()))
            db.session.execute(db.delete(ConnectionRequest))
            db.session.commit()
        page = self.client.get("/messages")
        self.assertIn(b"A useful preview", page.data)
        self.assertIn(b"Read-only", page.data)

    def test_inbox_and_history_pagination_sizes(self):
        self.start()
        conversation_id = self.conversation_id()
        with app.app_context():
            now = utc_now()
            db.session.add_all([
                Message(conversation_id=conversation_id, sender_id=self.ids["Alice"], body=f"Message {index}", created_at=now + timedelta(seconds=index))
                for index in range(51)
            ])
            db.session.commit()
            page = inbox_page(db.session, self.ids["Alice"], 1)
            self.assertEqual(page.total, 1)
        latest = self.client.get(f"/messages/{conversation_id}")
        self.assertNotIn(b"Message 0<", latest.data)
        self.assertIn(b"Message 50", latest.data)
        older = self.client.get(f"/messages/{conversation_id}?page=1")
        self.assertIn(b"Message 0", older.data)
        self.assertNotIn(b"Message 50", older.data)

    def test_csrf_is_required_for_sending(self):
        self.start()
        conversation_id = self.conversation_id()
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            self.assertEqual(self.client.post(f"/messages/{conversation_id}/send", data={"body": "No token"}).status_code, 400)
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_schema_compiles_for_mysql_with_safe_indexes(self):
        for table in (Conversation.__table__, Message.__table__):
            compiled = str(CreateTable(table).compile(dialect=mysql.dialect()))
            self.assertIn("CREATE TABLE", compiled)
            for index in table.indexes:
                self.assertLessEqual(len(index.name), 64)
                str(CreateIndex(index).compile(dialect=mysql.dialect()))

    def test_ui_wiring_includes_message_actions_and_responsive_safeguards(self):
        root = Path(app.root_path)
        connections = (root / "templates/connections.html").read_text(encoding="utf-8")
        profile = (root / "templates/person_profile.html").read_text(encoding="utf-8")
        css = (root / "static/css/messaging.css").read_text(encoding="utf-8")
        self.assertIn("start_message_conversation", connections)
        self.assertIn("start_message_conversation", profile)
        self.assertIn("overflow-wrap:anywhere", css)
        self.assertIn("max-width:480px", css)


if __name__ == "__main__":
    unittest.main()
