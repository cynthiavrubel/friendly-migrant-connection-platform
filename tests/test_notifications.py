"""Sprint 10 notification creation, coalescing, security, and UI tests."""

import os
import tempfile
import unittest
from datetime import date, timedelta

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False); database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-secret"

from app import app, db  # noqa: E402
from community_plans import create_plan, utc_now  # noqa: E402
from models import CommunityPlan, ConnectionIntent, ConnectionRequest, Conversation, Interest, Language, Message, Notification, PlanParticipant, Profile, User  # noqa: E402
from notifications import create_notification, unread_notification_count  # noqa: E402


class NotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all(); db.create_all()
            language=Language(name="English",code="en"); interests=[Interest(name=f"Interest {i}",slug=f"interest-{i}",category="Social") for i in range(3)]; intent=ConnectionIntent(name="Friendship",slug="friendship"); db.session.add_all([language,*interests,intent])
            self.users={}
            for name in ("Alice","Bob","Cara"):
                user=User(first_name=name,last_name="Private",email=f"{name.lower()}@example.com",password_hash="hash",date_of_birth=date(1990,1,1)); profile=Profile(user=user,gender="woman",profile_photo_key=f"{name}.webp",home_country_code="UA",home_city="Private",discovery_country_code="IE",discovery_city="Cork",open_to_connections=True); profile.languages=[language];profile.interests=interests;profile.connection_intents=[intent];db.session.add(user);db.session.flush();self.users[name]=user.id
            db.session.commit()
        self.client=app.test_client();self.login("Alice")

    def tearDown(self):
        with app.app_context(): db.session.remove()

    def login(self,name):
        with self.client.session_transaction() as session: session["user_id"]=self.users[name]

    def relationship(self,status="accepted"):
        low,high=sorted((self.users["Alice"],self.users["Bob"])); row=ConnectionRequest(sender_id=self.users["Alice"],recipient_id=self.users["Bob"],pair_low_id=low,pair_high_id=high,status=status,responded_at=utc_now() if status=="accepted" else None);db.session.add(row);db.session.flush();return row

    def plan(self,title="Coffee in Cork"):
        return create_plan(db.session,db.session.get(User,self.users["Alice"]),{"title":title,"category":"coffee-food","description":"A welcoming coffee meetup in a public place.","country_code":"IE","city":"Cork","starts_at":utc_now()+timedelta(days=2),"meeting_place_text":"Cafe entrance","capacity":5})

    def notifications(self,user="Alice"):
        return list(db.session.scalars(db.select(Notification).where(Notification.user_id==self.users[user]).order_by(Notification.id)))

    def test_auth_and_owner_isolation(self):
        with app.app_context(): create_notification(db.session,self.users["Bob"],"connection_request_received",actor_id=self.users["Alice"]);db.session.commit()
        self.assertNotIn(b"sent you",self.client.get("/notifications").data)
        with self.client.session_transaction() as session:session.clear()
        self.assertIn("/login",self.client.get("/notifications").headers["Location"])

    def test_connection_request_and_accept_notifications_only_on_success(self):
        self.client.post(f"/people/{self.users['Bob']}/connect",data={"introduction":"Hi"})
        self.client.post(f"/people/{self.users['Bob']}/connect",data={"introduction":"duplicate"})
        with app.app_context(): self.assertEqual([n.type for n in self.notifications("Bob")],["connection_request_received"]);relationship=db.session.scalar(db.select(ConnectionRequest));relationship_id=relationship.id
        self.login("Bob");self.client.post(f"/connections/{relationship_id}/accept")
        with app.app_context(): self.assertEqual([n.type for n in self.notifications("Alice")],["connection_request_accepted"])

    def test_self_notification_is_centrally_prevented(self):
        with app.app_context():
            self.assertIsNone(create_notification(db.session,self.users["Alice"],"new_message",actor_id=self.users["Alice"],entity_type="conversation",entity_id=1));db.session.commit();self.assertEqual(len(self.notifications()),0)

    def test_message_notification_coalesces_until_read_then_creates_new(self):
        with app.app_context(): relationship=self.relationship();low,high=sorted((self.users["Alice"],self.users["Bob"]));conversation=Conversation(user_low_id=low,user_high_id=high);db.session.add(conversation);db.session.commit();cid=conversation.id
        for body in ("One","Two","Three"):self.client.post(f"/messages/{cid}/send",data={"body":body})
        with app.app_context():
            notices=self.notifications("Bob");self.assertEqual(len(notices),1);notice_id=notices[0].id;self.assertEqual(db.session.scalar(db.select(db.func.count(Message.id))),3)
        self.login("Bob");self.client.post(f"/notifications/{notice_id}/read")
        self.login("Alice");self.client.post(f"/messages/{cid}/send",data={"body":"Later"})
        with app.app_context():self.assertEqual(len(self.notifications("Bob")),2)

    def test_failed_message_creates_nothing(self):
        with app.app_context(): relationship=self.relationship();low,high=sorted((self.users["Alice"],self.users["Bob"]));c=Conversation(user_low_id=low,user_high_id=high);db.session.add(c);db.session.commit();cid=c.id
        self.client.post(f"/messages/{cid}/send",data={"body":"   "})
        with app.app_context():self.assertEqual(len(self.notifications("Bob")),0)

    def test_plan_join_leave_remove_notifications_and_failures(self):
        with app.app_context():plan=self.plan();db.session.commit();pid=plan.id
        self.login("Bob");self.client.post(f"/plans/{pid}/join");self.client.post(f"/plans/{pid}/join");self.client.post(f"/plans/{pid}/leave")
        with app.app_context():self.assertEqual([n.type for n in self.notifications("Alice")],["plan_participant_joined","plan_participant_left"])
        self.client.post(f"/plans/{pid}/join");self.login("Alice");self.client.post(f"/plans/{pid}/participants/{self.users['Bob']}/remove")
        with app.app_context():self.assertEqual([n.type for n in self.notifications("Bob")],["plan_participant_removed"])

    def test_cancel_fanout_only_current_non_host_participants(self):
        with app.app_context():plan=self.plan();db.session.add_all([PlanParticipant(plan=plan,user_id=self.users["Bob"]),PlanParticipant(plan=plan,user_id=self.users["Cara"])]);db.session.commit();pid=plan.id
        self.login("Cara");self.client.post(f"/plans/{pid}/leave");self.login("Alice");self.client.post(f"/plans/{pid}/cancel")
        with app.app_context():
            self.assertEqual([n.type for n in self.notifications("Bob")],["plan_cancelled"]);self.assertEqual([n.type for n in self.notifications("Cara")],[]);self.assertNotIn("plan_cancelled",[n.type for n in self.notifications("Alice")])

    def test_mark_one_all_read_idempotent_and_idor_safe(self):
        with app.app_context():
            a=create_notification(db.session,self.users["Alice"],"connection_request_accepted",actor_id=self.users["Bob"]);b=create_notification(db.session,self.users["Alice"],"plan_cancelled",actor_id=self.users["Bob"],entity_type="plan",entity_id=999);other=create_notification(db.session,self.users["Bob"],"new_message",actor_id=self.users["Alice"],entity_type="conversation",entity_id=999);db.session.commit();aid=a.id;oid=other.id
        self.client.post(f"/notifications/{aid}/read");self.client.post(f"/notifications/{aid}/read");self.assertEqual(self.client.post(f"/notifications/{oid}/read").status_code,404);self.client.post("/notifications/read-all");self.client.post("/notifications/read-all")
        with app.app_context():self.assertEqual(unread_notification_count(db.session,self.users["Alice"]),0);self.assertEqual(unread_notification_count(db.session,self.users["Bob"]),1)

    def test_page_order_pagination_and_unread_navigation_count(self):
        with app.app_context():
            for i in range(21):create_notification(db.session,self.users["Alice"],"connection_request_accepted",actor_id=self.users["Bob"],now=utc_now()+timedelta(seconds=i))
            db.session.commit()
        page=self.client.get("/notifications").data;self.assertIn(b"Notifications (21)",page);self.assertIn(b"Page 1 of 2",page);self.assertEqual(page.count(b'class="notification-row'),20)
        self.assertEqual(self.client.get("/notifications?page=not-a-number").status_code,200)

    def test_controlled_destinations_and_no_redirect_injection(self):
        with app.app_context():n=create_notification(db.session,self.users["Alice"],"connection_request_received",actor_id=self.users["Bob"]);db.session.commit();nid=n.id
        response=self.client.post(f"/notifications/{nid}/open?next=https://evil.example")
        self.assertTrue(response.headers["Location"].endswith("/connections?tab=received"))

    def test_missing_actor_and_entity_render_and_fallback_safely(self):
        with app.app_context():
            n=create_notification(db.session,self.users["Alice"],"plan_cancelled",actor_id=None,entity_type="plan",entity_id=999999);db.session.commit();nid=n.id
        page=self.client.get("/notifications").data;self.assertIn(b"a community plan was cancelled by A user",page)
        self.assertTrue(self.client.post(f"/notifications/{nid}/open").headers["Location"].endswith("/plans/mine"))

    def test_xss_and_private_actor_fields_are_not_exposed(self):
        with app.app_context():
            bob=db.session.get(User,self.users["Bob"]);bob.first_name="<script>alert(1)</script>";create_notification(db.session,self.users["Alice"],"connection_request_accepted",actor_id=bob.id);db.session.commit()
        page=self.client.get("/notifications").data;self.assertNotIn(b"<script>alert",page);self.assertIn(b"&lt;script&gt;",page);self.assertNotIn(b"bob@example.com",page);self.assertNotIn(b"Private",page)

    def test_notification_read_state_is_independent_of_message_and_domain_state(self):
        with app.app_context():
            relationship=self.relationship();low,high=sorted((self.users["Alice"],self.users["Bob"]));c=Conversation(user_low_id=low,user_high_id=high);db.session.add(c);db.session.flush();m=Message(conversation_id=c.id,sender_id=self.users["Bob"],body="Unread",created_at=utc_now());db.session.add(m);n=create_notification(db.session,self.users["Alice"],"new_message",actor_id=self.users["Bob"],entity_type="conversation",entity_id=c.id);db.session.commit();nid=n.id;mid=m.id;rid=relationship.id
        self.client.post(f"/notifications/{nid}/read")
        with app.app_context():self.assertIsNone(db.session.get(Message,mid).read_at);self.assertEqual(db.session.get(ConnectionRequest,rid).status,"accepted")

    def test_csrf_and_mysql_schema(self):
        with app.app_context():n=create_notification(db.session,self.users["Alice"],"connection_request_accepted",actor_id=self.users["Bob"]);db.session.commit();nid=n.id
        app.config["WTF_CSRF_ENABLED"]=True
        try:
            for url in (f"/notifications/{nid}/read",f"/notifications/{nid}/open","/notifications/read-all"):self.assertEqual(self.client.post(url).status_code,400)
        finally:app.config["WTF_CSRF_ENABLED"]=False
        compiled=str(CreateTable(Notification.__table__).compile(dialect=mysql.dialect()));self.assertIn("CREATE TABLE",compiled)
        for index in Notification.__table__.indexes:self.assertLessEqual(len(index.name),64);str(CreateIndex(index).compile(dialect=mysql.dialect()))


if __name__=="__main__":unittest.main()
