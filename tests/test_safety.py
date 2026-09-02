"""Sprint 12 blocking, reporting, privacy, and regression tests."""

import os
import tempfile
import unittest
from datetime import date, timedelta

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{database_file.name}")
os.environ.setdefault("SECRET_KEY", "test-only-secret")

from app import app, db  # noqa: E402
from community_plans import create_plan, join_plan, utc_now  # noqa: E402
from connections import ConnectionError, send_request  # noqa: E402
from messaging import MessagingError, send_message, start_conversation  # noqa: E402
from models import (  # noqa: E402
    CommunityPlan, ConnectionIntent, ConnectionRequest, Conversation, Interest,
    Language, Message, Notification, PlanParticipant, Profile, User, UserBlock,
    UserReport,
)
from safety import SafetyError, block_user, is_blocked_pair, report_user, unblock_user  # noqa: E402


class SafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all(); db.create_all()
            self.assertEqual(app.test_cli_runner().invoke(args=["seed-profile-data"]).exit_code, 0)
            languages=list(db.session.scalars(db.select(Language).limit(2)))
            interests=list(db.session.scalars(db.select(Interest).limit(3)))
            intent=db.session.scalar(db.select(ConnectionIntent))
            users=[]
            for name in ("Alice","Bob","Cara","Dara"):
                user=User(first_name=name,last_name="Private",email=f"{name.lower()}@example.com",password_hash="hash",date_of_birth=date(1990,1,1))
                profile=Profile(user=user,gender="woman",bio=f"About {name}",profile_photo_key=f"profiles/{name.lower()}.webp",home_country_code="IE",home_city="Galway",discovery_country_code="IE",discovery_city="Cork",open_to_connections=True)
                profile.languages=languages; profile.interests=interests; profile.connection_intents=[intent]
                db.session.add(user); users.append(user)
            db.session.commit(); self.ids={user.first_name:user.id for user in users}
        self.client=app.test_client(); self.login("Alice")

    def tearDown(self):
        with app.app_context(): db.session.remove()

    def login(self,name):
        with self.client.session_transaction() as browser_session: browser_session["user_id"]=self.ids[name]

    def relationship(self,first="Alice",second="Bob",status="accepted"):
        first_id,second_id=self.ids[first],self.ids[second]; low,high=sorted((first_id,second_id))
        row=ConnectionRequest(sender_id=first_id,recipient_id=second_id,pair_low_id=low,pair_high_id=high,status=status,created_at=utc_now(),updated_at=utc_now())
        db.session.add(row); db.session.flush(); return row

    def plan(self,host="Alice",**changes):
        values={"title":"Safety walk","category":"walks-outdoors","description":"A welcoming walk in the city.","country_code":"IE","city":"Cork","starts_at":utc_now()+timedelta(days=7),"timezone":"UTC","meeting_place_text":"Library","capacity":6}
        values.update(changes); return create_plan(db.session,db.session.get(User,self.ids[host]),values)

    def test_block_auth_self_direction_and_duplicate_are_safe(self):
        with self.client.session_transaction() as browser_session: browser_session.clear()
        self.assertIn("/login",self.client.post(f"/people/{self.ids['Bob']}/block").headers["Location"])
        self.login("Alice"); self.assertEqual(self.client.post(f"/people/{self.ids['Alice']}/block").status_code,400)
        self.client.post(f"/people/{self.ids['Bob']}/block"); self.client.post(f"/people/{self.ids['Bob']}/block")
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(UserBlock.id))),1)
            self.assertTrue(is_blocked_pair(db.session,self.ids["Alice"],self.ids["Bob"]))
            self.assertTrue(is_blocked_pair(db.session,self.ids["Bob"],self.ids["Alice"]))

    def test_block_quietly_removes_pair_connection_and_future_cross_plan_membership(self):
        with app.app_context():
            self.relationship(); unrelated=self.relationship("Alice","Cara")
            alice_plan=self.plan(); bob_plan=self.plan("Bob",title="Bob plan")
            past=self.plan(title="Past"); past.starts_at=utc_now()-timedelta(days=2)
            cancelled=self.plan(title="Cancelled"); cancelled.status="cancelled"
            for plan,user in ((alice_plan,"Bob"),(bob_plan,"Alice"),(past,"Bob"),(cancelled,"Bob")):
                if db.session.get(PlanParticipant,(plan.id,self.ids[user])) is None: db.session.add(PlanParticipant(plan_id=plan.id,user_id=self.ids[user],joined_at=utc_now()))
            conversation=Conversation(user_low_id=min(self.ids["Alice"],self.ids["Bob"]),user_high_id=max(self.ids["Alice"],self.ids["Bob"]),created_at=utc_now(),last_activity_at=utc_now())
            db.session.add(conversation); db.session.flush(); db.session.add(Message(conversation_id=conversation.id,sender_id=self.ids["Alice"],body="History",created_at=utc_now()))
            db.session.commit(); ids=(alice_plan.id,bob_plan.id,past.id,cancelled.id,unrelated.id,conversation.id)
            block_user(db.session,self.ids["Alice"],self.ids["Bob"]); db.session.commit()
            self.assertIsNone(db.session.scalar(db.select(ConnectionRequest).where(ConnectionRequest.pair_low_id==min(self.ids["Alice"],self.ids["Bob"]),ConnectionRequest.pair_high_id==max(self.ids["Alice"],self.ids["Bob"]))))
            self.assertIsNotNone(db.session.get(ConnectionRequest,ids[4]))
            self.assertIsNone(db.session.get(PlanParticipant,(ids[0],self.ids["Bob"])))
            self.assertIsNone(db.session.get(PlanParticipant,(ids[1],self.ids["Alice"])))
            self.assertIsNotNone(db.session.get(PlanParticipant,(ids[2],self.ids["Bob"])))
            self.assertIsNotNone(db.session.get(PlanParticipant,(ids[3],self.ids["Bob"])))
            self.assertIsNotNone(db.session.scalar(db.select(Message).where(Message.conversation_id==ids[5])))
            self.assertEqual(db.session.scalar(db.select(db.func.count(Notification.id))),0)

    def test_blocked_pair_is_mutually_hidden_and_cannot_connect(self):
        self.client.post(f"/people/{self.ids['Bob']}/block")
        self.assertNotIn(b"Bob",self.client.get("/discover").data)
        self.assertEqual(self.client.get(f"/people/{self.ids['Bob']}").status_code,404)
        self.assertEqual(self.client.get(f"/people/{self.ids['Bob']}/connect").status_code,404)
        self.login("Bob")
        self.assertNotIn(b"Alice",self.client.get("/discover").data)
        self.assertEqual(self.client.get(f"/people/{self.ids['Alice']}").status_code,404)
        with app.app_context():
            with self.assertRaisesRegex(ConnectionError,"not available"): send_request(db.session,db.session.get(User,self.ids["Bob"]),self.ids["Alice"])

    def test_blocked_message_history_is_read_only_and_creates_no_activity(self):
        with app.app_context():
            self.relationship(); conversation=start_conversation(db.session,self.ids["Alice"],self.ids["Bob"]); send_message(db.session,conversation.id,self.ids["Alice"],"Before block"); db.session.commit(); conversation_id=conversation.id
            block_user(db.session,self.ids["Alice"],self.ids["Bob"]); db.session.commit()
            with self.assertRaisesRegex(MessagingError,"unavailable"): start_conversation(db.session,self.ids["Alice"],self.ids["Bob"])
            with self.assertRaisesRegex(MessagingError,"unavailable"): send_message(db.session,conversation_id,self.ids["Alice"],"After block")
            db.session.rollback()
        page=self.client.get(f"/messages/{conversation_id}").data
        self.assertIn(b"Before block",page); self.assertIn(b"Messaging is unavailable",page); self.assertNotIn(b"message-composer",page)
        self.client.post(f"/messages/{conversation_id}/send",data={"body":"Crafted"})
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Message.id))),1)
            self.assertEqual(db.session.scalar(db.select(db.func.count(Notification.id))),0)

    def test_blocked_pair_cannot_join_either_host_plan(self):
        with app.app_context():
            alice_plan=self.plan(); bob_plan=self.plan("Bob",title="Bob plan"); block_user(db.session,self.ids["Alice"],self.ids["Bob"]); db.session.commit()
            with self.assertRaisesRegex(Exception,"not available"): join_plan(db.session,alice_plan.id,self.ids["Bob"])
            with self.assertRaisesRegex(Exception,"not available"): join_plan(db.session,bob_plan.id,self.ids["Alice"])

    def test_unblock_only_removes_own_direction_and_restores_nothing(self):
        with app.app_context():
            self.relationship(); plan=self.plan(); db.session.add(PlanParticipant(plan_id=plan.id,user_id=self.ids["Bob"],joined_at=utc_now())); block_user(db.session,self.ids["Alice"],self.ids["Bob"]); db.session.add(UserBlock(blocker_id=self.ids["Bob"],blocked_id=self.ids["Alice"])); db.session.commit(); plan_id=plan.id
            unblock_user(db.session,self.ids["Alice"],self.ids["Bob"]); db.session.commit()
            self.assertTrue(is_blocked_pair(db.session,self.ids["Alice"],self.ids["Bob"]))
            self.assertIsNone(db.session.scalar(db.select(ConnectionRequest)))
            self.assertIsNone(db.session.get(PlanParticipant,(plan_id,self.ids["Bob"])))
            unblock_user(db.session,self.ids["Bob"],self.ids["Alice"]); db.session.commit()
            send_request(db.session,db.session.get(User,self.ids["Alice"]),self.ids["Bob"]); db.session.commit()
            self.assertEqual(db.session.scalar(db.select(ConnectionRequest.status)),"pending")

    def test_blocked_users_page_shows_outbound_only_and_unblock_is_owned(self):
        with app.app_context():
            db.session.add_all([UserBlock(blocker_id=self.ids["Alice"],blocked_id=self.ids["Bob"]),UserBlock(blocker_id=self.ids["Cara"],blocked_id=self.ids["Alice"])]); db.session.commit()
        page=self.client.get("/settings/blocked-users").data
        self.assertIn(b"Bob",page); self.assertNotIn(b"Cara",page)
        self.login("Dara"); self.client.post(f"/people/{self.ids['Bob']}/unblock")
        with app.app_context(): self.assertIsNotNone(db.session.scalar(db.select(UserBlock).where(UserBlock.blocker_id==self.ids["Alice"],UserBlock.blocked_id==self.ids["Bob"])))

    def test_report_is_private_non_punitive_and_allows_separate_incidents(self):
        with app.app_context():
            relationship=self.relationship(); plan=self.plan(); db.session.add(PlanParticipant(plan_id=plan.id,user_id=self.ids["Bob"],joined_at=utc_now())); db.session.commit(); relationship_id=relationship.id; plan_id=plan.id
        for details in ("First concern","A later incident"):
            response=self.client.post(f"/people/{self.ids['Bob']}/report",data={"reason":"harassment","details":details},follow_redirects=True)
            self.assertIn(b"submitted for review",response.data)
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(UserReport.id))),2)
            self.assertEqual(db.session.scalar(db.select(db.func.count(UserBlock.id))),0)
            self.assertIsNotNone(db.session.get(ConnectionRequest,relationship_id)); self.assertIsNotNone(db.session.get(PlanParticipant,(plan_id,self.ids["Bob"])))
            self.assertEqual(db.session.scalar(db.select(db.func.count(Notification.id))),0)
        self.login("Bob"); self.assertEqual(self.client.get("/reports/1").status_code,404)

    def test_report_validation_auth_self_reason_length_and_xss(self):
        with self.client.session_transaction() as browser_session: browser_session.clear()
        self.assertIn("/login",self.client.post(f"/people/{self.ids['Bob']}/report").headers["Location"])
        self.login("Alice"); self.assertEqual(self.client.get(f"/people/{self.ids['Alice']}/report").status_code,400)
        with app.app_context():
            with self.assertRaisesRegex(SafetyError,"cannot report yourself"):
                report_user(db.session,self.ids["Alice"],self.ids["Alice"],"other")
        invalid=self.client.post(f"/people/{self.ids['Bob']}/report",data={"reason":"invented","details":"x"})
        self.assertIn(b"Not a valid choice",invalid.data)
        long=self.client.post(f"/people/{self.ids['Bob']}/report",data={"reason":"other","details":"x"*2001})
        self.assertIn(b"longer than 2000",long.data)
        xss=self.client.post(f"/people/{self.ids['Bob']}/report",data={"reason":"other","details":"<script>alert(1)</script>"},follow_redirects=True)
        self.assertNotIn(b"<script>alert(1)</script>",xss.data)
        with app.app_context(): self.assertEqual(db.session.scalar(db.select(db.func.count(UserReport.id))),1)

    def test_csrf_and_mysql_schema_contract(self):
        app.config["WTF_CSRF_ENABLED"]=True
        try:
            for url in (f"/people/{self.ids['Bob']}/block",f"/people/{self.ids['Bob']}/unblock",f"/people/{self.ids['Bob']}/report"):
                self.assertEqual(self.client.post(url,data={"reason":"other"}).status_code,400)
        finally: app.config["WTF_CSRF_ENABLED"]=False
        for model in (UserBlock,UserReport):
            ddl=str(CreateTable(model.__table__).compile(dialect=mysql.dialect())); self.assertIn("CREATE TABLE",ddl)
            for constraint in model.__table__.constraints:
                if constraint.name: self.assertLessEqual(len(constraint.name),64)
            for index in model.__table__.indexes:
                self.assertLessEqual(len(index.name),64); str(CreateIndex(index).compile(dialect=mysql.dialect()))


if __name__ == "__main__": unittest.main()
