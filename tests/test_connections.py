"""Sprint 7 mutual connection state, security, privacy, and UI tests."""

import os
import tempfile
import unittest
from datetime import timedelta

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-only-secret"

from app import app, db  # noqa: E402
from connections import utc_now  # noqa: E402
from discovery import years_ago  # noqa: E402
from models import ConnectionIntent, ConnectionRequest, Interest, Language, Profile, User  # noqa: E402


class ConnectionFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()
            self.assertEqual(app.test_cli_runner().invoke(args=["seed-profile-data"]).exit_code, 0)
            self.languages = list(db.session.scalars(db.select(Language).order_by(Language.id).limit(2)))
            self.interests = list(db.session.scalars(db.select(Interest).order_by(Interest.id).limit(3)))
            self.intention = db.session.scalar(db.select(ConnectionIntent).order_by(ConnectionIntent.id))
            self.alice = self.make_user("Alice", "alice@example.com")
            self.bob = self.make_user("Bob", "bob@example.com")
            self.cara = self.make_user("Cara", "cara@example.com")
            db.session.commit()
            self.ids = {user.first_name: user.id for user in (self.alice, self.bob, self.cara)}
        self.client = app.test_client()
        self.login("Alice")

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    def make_user(self, name, email, *, complete=True, open_to_connections=True):
        user = User(first_name=name, last_name="PrivateSurname", email=email, password_hash="private-hash", date_of_birth=years_ago(30))
        profile = Profile(
            user=user, gender="woman", bio=f"Hello from {name}",
            profile_photo_key=f"profiles/{name.lower()}.webp" if complete else None,
            home_country_code="UA", home_city="Private Home", discovery_country_code="IT",
            discovery_city="Milan", open_to_connections=open_to_connections,
        )
        profile.languages = self.languages
        profile.interests = self.interests
        profile.connection_intents = [self.intention]
        db.session.add(user)
        db.session.flush()
        return user

    def login(self, name):
        with self.client.session_transaction() as session:
            session["user_id"] = self.ids[name]

    def send(self, sender="Alice", recipient="Bob", introduction=""):
        self.login(sender)
        return self.client.post(
            f"/people/{self.ids[recipient]}/connect",
            data={"introduction": introduction},
            follow_redirects=True,
        )

    def relationship(self, first="Alice", second="Bob"):
        low, high = sorted((self.ids[first], self.ids[second]))
        with app.app_context():
            return db.session.scalar(db.select(ConnectionRequest).where(ConnectionRequest.pair_low_id == low, ConnectionRequest.pair_high_id == high))

    def test_unauthenticated_connections_page_is_blocked(self):
        response = app.test_client().get("/connections")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_incomplete_sender_self_and_unavailable_recipient_are_rejected(self):
        with app.app_context():
            db.session.get(User, self.ids["Alice"]).profile.profile_photo_key = None
            db.session.commit()
        response = self.client.post(f"/people/{self.ids['Bob']}/connect", data={})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/profile/edit", response.location)
        with app.app_context():
            db.session.get(User, self.ids["Alice"]).profile.profile_photo_key = "profiles/alice.webp"
            db.session.get(User, self.ids["Bob"]).profile.open_to_connections = False
            db.session.commit()
        self.assertEqual(self.client.post(f"/people/{self.ids['Alice']}/connect", data={}).status_code, 400)
        self.assertEqual(self.client.get(f"/people/{self.ids['Bob']}/connect").status_code, 404)

    def test_send_without_and_with_trimmed_introduction(self):
        response = self.send()
        self.assertIn(b"Connection request sent", response.data)
        with app.app_context():
            relationship = db.session.scalar(db.select(ConnectionRequest))
            self.assertEqual(relationship.status, "pending")
            self.assertIsNone(relationship.introductory_message)
        self.login("Alice")
        self.client.post(f"/connections/{self.relationship().id}/cancel")
        self.send(introduction="  Hello Bob!  ")
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(ConnectionRequest)).introductory_message, "Hello Bob!")

    def test_introduction_over_300_characters_is_rejected(self):
        response = self.send(introduction="x" * 301)
        self.assertIn(b"Field cannot be longer than 300 characters", response.data)
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(ConnectionRequest.id))), 0)

    def test_duplicate_and_reciprocal_pending_requests_are_prevented(self):
        self.send()
        duplicate = self.send()
        self.assertIn(b"Request sent", duplicate.data)
        reciprocal = self.send("Bob", "Alice")
        self.assertIn(b"already have a connection request", reciprocal.data)
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(ConnectionRequest.id))), 1)

    def test_pending_states_appear_in_discover_and_public_profile(self):
        self.send()
        self.login("Alice")
        self.assertIn(b"Request sent", self.client.get("/discover").data)
        self.assertIn(b"Request sent", self.client.get(f"/people/{self.ids['Bob']}").data)
        self.login("Bob")
        self.assertIn(b"Respond to request", self.client.get("/discover").data)
        self.assertIn(b"Respond to request", self.client.get(f"/people/{self.ids['Alice']}").data)

    def test_only_recipient_can_accept_and_accept_is_mutual(self):
        self.send()
        relationship_id = self.relationship().id
        self.login("Alice")
        self.client.post(f"/connections/{relationship_id}/accept")
        self.assertEqual(self.relationship().status, "pending")
        self.login("Cara")
        self.client.post(f"/connections/{relationship_id}/accept")
        self.assertEqual(self.relationship().status, "pending")
        self.login("Bob")
        response = self.client.post(f"/connections/{relationship_id}/accept", follow_redirects=True)
        self.assertIn(b"now connected", response.data)
        self.assertEqual(self.relationship().status, "accepted")
        for user in ("Alice", "Bob"):
            self.login(user)
            self.assertIn(b"Connected", self.client.get("/connections").data)
            self.assertIn(b"Connected", self.client.get("/discover").data)
        with app.app_context():
            db.session.get(User, self.ids["Bob"]).profile.open_to_connections = False
            db.session.commit()
        self.login("Alice")
        self.assertEqual(self.client.get(f"/people/{self.ids['Bob']}").status_code, 200)
        self.send("Alice", "Bob")
        self.assertEqual(self.relationship().status, "accepted")

    def test_only_recipient_can_decline_and_decline_stays_private(self):
        self.send(introduction="A private hello")
        relationship_id = self.relationship().id
        self.login("Alice")
        self.client.post(f"/connections/{relationship_id}/decline")
        self.assertEqual(self.relationship().status, "pending")
        self.login("Bob")
        self.client.post(f"/connections/{relationship_id}/decline")
        self.assertEqual(self.relationship().status, "declined")
        for user, tab in (("Alice", "sent"), ("Bob", "received")):
            self.login(user)
            page = self.client.get(f"/connections?tab={tab}")
            self.assertNotIn(b"A private hello", page.data)
            self.assertNotIn(b"declined", page.data.lower())

    def test_decline_cooldown_then_resend_after_30_days(self):
        self.send()
        relationship_id = self.relationship().id
        self.login("Bob")
        self.client.post(f"/connections/{relationship_id}/decline")
        blocked = self.send("Alice", "Bob")
        self.assertIn(b"Connection unavailable for now", blocked.data)
        with app.app_context():
            relationship = db.session.get(ConnectionRequest, relationship_id)
            relationship.responded_at = utc_now() - timedelta(days=31)
            db.session.commit()
        allowed = self.send("Alice", "Bob", "Hello again")
        self.assertIn(b"Connection request sent", allowed.data)
        self.assertEqual(self.relationship().status, "pending")

    def test_reverse_direction_allowed_during_decline_cooldown(self):
        self.send("Alice", "Bob")
        relationship_id = self.relationship().id
        self.login("Bob")
        self.client.post(f"/connections/{relationship_id}/decline")
        response = self.send("Bob", "Alice", "Hello from the other direction")
        self.assertIn(b"Connection request sent", response.data)
        relationship = self.relationship()
        self.assertEqual((relationship.sender_id, relationship.recipient_id), (self.ids["Bob"], self.ids["Alice"]))

    def test_cancel_authorization_and_immediate_new_request(self):
        self.send()
        relationship_id = self.relationship().id
        self.login("Bob")
        self.client.post(f"/connections/{relationship_id}/cancel")
        self.assertIsNotNone(self.relationship())
        self.login("Alice")
        self.client.post(f"/connections/{relationship_id}/cancel")
        self.assertIsNone(self.relationship())
        self.assertIn(b"Connection request sent", self.send("Bob", "Alice").data)

    def test_remove_authorization_and_immediate_reconnection(self):
        self.send()
        relationship_id = self.relationship().id
        self.login("Bob")
        self.client.post(f"/connections/{relationship_id}/accept")
        self.login("Cara")
        self.client.post(f"/connections/{relationship_id}/remove")
        self.assertIsNotNone(self.relationship())
        self.login("Alice")
        self.client.post(f"/connections/{relationship_id}/remove")
        self.assertIsNone(self.relationship())
        self.assertIn(b"Connection request sent", self.send("Alice", "Bob").data)

    def test_connections_tabs_counts_and_empty_states(self):
        page = self.client.get("/connections")
        self.assertIn(b"Connections <span>0</span>", page.data)
        self.assertIn(b"Received <span>0</span>", page.data)
        self.assertIn(b"Sent <span>0</span>", page.data)
        self.assertIn(b"haven't made any connections", page.data)
        self.assertIn(b"No new connection requests", self.client.get("/connections?tab=received").data)
        self.assertIn(b"No pending requests", self.client.get("/connections?tab=sent").data)
        self.send()
        self.login("Alice")
        self.assertIn(b"Sent <span>1</span>", self.client.get("/connections?tab=sent").data)
        self.login("Bob")
        self.assertIn(b"Received <span>1</span>", self.client.get("/connections?tab=received").data)

    def test_introduction_is_escaped_and_private_fields_are_absent(self):
        self.send(introduction='<script>alert("x")</script>')
        self.login("Bob")
        page = self.client.get("/connections?tab=received")
        self.assertIn(b"&lt;script&gt;", page.data)
        self.assertNotIn(b"<script>", page.data)
        for private in (b"PrivateSurname", b"alice@example.com", b"Private Home", b"private-hash"):
            self.assertNotIn(private, page.data)

    def test_csrf_is_enforced_on_all_mutation_routes(self):
        self.send()
        relationship_id = self.relationship().id
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            for path in (
                f"/people/{self.ids['Cara']}/connect",
                f"/connections/{relationship_id}/accept",
                f"/connections/{relationship_id}/decline",
                f"/connections/{relationship_id}/cancel",
                f"/connections/{relationship_id}/remove",
            ):
                self.assertEqual(self.client.post(path, data={}).status_code, 400, path)
        finally:
            app.config["WTF_CSRF_ENABLED"] = False

    def test_database_pair_constraint_prevents_duplicate_rows(self):
        self.send()
        with app.app_context():
            duplicate = ConnectionRequest(
                sender_id=self.ids["Bob"], recipient_id=self.ids["Alice"],
                pair_low_id=min(self.ids["Alice"], self.ids["Bob"]),
                pair_high_id=max(self.ids["Alice"], self.ids["Bob"]), status="pending",
            )
            db.session.add(duplicate)
            with self.assertRaises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_connection_schema_compiles_for_mysql_with_safe_names(self):
        table = ConnectionRequest.__table__
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        self.assertIn("UNIQUE", ddl)
        self.assertIn("CHECK", ddl)
        self.assertIn("VARCHAR(300)", ddl)
        for constraint in table.constraints:
            if constraint.name:
                self.assertLessEqual(len(constraint.name), 64)
        for index in table.indexes:
            self.assertLessEqual(len(index.name), 64)
            self.assertIn("CREATE INDEX", str(CreateIndex(index).compile(dialect=mysql.dialect())))


if __name__ == "__main__":
    unittest.main()
