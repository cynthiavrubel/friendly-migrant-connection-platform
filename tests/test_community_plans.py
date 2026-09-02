"""Sprint 9 Community Plans behavior, security, privacy, and schema tests."""

import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-only-secret"

from app import app, db  # noqa: E402
from community_plans import CATEGORY_LABELS, PlanError, create_plan, join_plan, utc_now, validate_plan_values  # noqa: E402
from models import CommunityPlan, ConnectionIntent, Interest, Language, PlanParticipant, Profile, User  # noqa: E402


class CommunityPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all(); db.create_all()
            self.assertEqual(app.test_cli_runner().invoke(args=["seed-profile-data"]).exit_code, 0)
            self.languages = list(db.session.scalars(db.select(Language).limit(2)))
            self.interests = list(db.session.scalars(db.select(Interest).limit(3)))
            self.intent = db.session.scalar(db.select(ConnectionIntent))
            self.alice = self.make_user("Alice", discovery_city="Milan", home_city="Cork")
            self.bob = self.make_user("Bob", discovery_city="MILAN", home_city="Galway")
            self.cara = self.make_user("Cara", discovery_city="Dublin", home_city="Milan")
            self.incomplete = self.make_user("Incomplete", complete=False)
            db.session.commit()
            self.ids = {user.first_name: user.id for user in (self.alice, self.bob, self.cara, self.incomplete)}
        self.client = app.test_client(); self.login("Alice")

    def tearDown(self):
        with app.app_context(): db.session.remove()

    def make_user(self, name, *, discovery_city="Milan", home_city="Kyiv", complete=True):
        user = User(first_name=name, last_name="PrivateSurname", email=f"{name.lower()}@example.com", password_hash="hash", date_of_birth=date(1990, 1, 1))
        profile = Profile(user=user, gender="woman", bio=f"About {name}", profile_photo_key=f"profiles/{name.lower()}.webp" if complete else None, home_country_code="IE", home_city=home_city, discovery_country_code="IT", discovery_city=discovery_city, open_to_connections=True)
        profile.languages=self.languages; profile.interests=self.interests; profile.connection_intents=[self.intent]
        db.session.add(user); db.session.flush(); return user

    def login(self, name):
        with self.client.session_transaction() as browser_session: browser_session["user_id"] = self.ids[name]

    def data(self, **changes):
        value={"title":"Spider-Man at the cinema","category":"cinema-entertainment","description":"Let us watch a film together and have coffee afterwards.","country_code":"IT","city":" Milan ","starts_at":(utc_now()+timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),"timezone":"UTC","meeting_place_text":"Cinema entrance near Duomo","capacity":"4"}
        value.update(changes); return value

    def direct_plan(self, creator="Alice", **changes):
        user=db.session.get(User,self.ids[creator]); values=self.data(); values["starts_at"]=utc_now()+timedelta(days=3); values["capacity"]=4; values.update(changes)
        return create_plan(db.session,user,values)

    def create_via_route(self, **changes):
        return self.client.post("/plans/create",data=self.data(**changes),follow_redirects=True)

    def test_authentication_and_profile_completion_guards(self):
        with self.client.session_transaction() as browser_session: browser_session.clear()
        self.assertIn("/login",self.client.get("/plans").headers["Location"])
        self.login("Incomplete")
        for url in ("/plans","/plans/create"):
            self.assertIn("/profile/edit",self.client.get(url).headers["Location"])

    def test_create_defaults_to_discovery_location_and_auto_adds_host(self):
        form=self.client.get("/plans/create").data
        self.assertIn(b'selected value="IT"',form); self.assertIn(b'value="Milan"',form)
        response=self.create_via_route(); self.assertIn(b"Spider-Man at the cinema",response.data)
        with app.app_context():
            plan=db.session.scalar(db.select(CommunityPlan)); participants=list(db.session.scalars(db.select(PlanParticipant)))
            self.assertEqual(plan.city,"Milan"); self.assertEqual(plan.city_normalized,"milan"); self.assertEqual(plan.creator_id,self.ids["Alice"])
            self.assertEqual([(row.user_id,row.plan_id) for row in participants],[(self.ids["Alice"],plan.id)])

    def test_capacity_start_and_category_validation(self):
        for changes,expected in (({"capacity":"1"},b"between 2 and 20"),({"capacity":"21"},b"between 2 and 20"),({"starts_at":(utc_now()-timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")},b"future date"),({"category":"invented"},b"valid choice")):
            page=self.create_via_route(**changes); self.assertIn(expected,page.data)
        with app.app_context(): self.assertEqual(db.session.scalar(db.select(db.func.count(CommunityPlan.id))),0)

    def test_create_converts_local_wall_time_to_utc_and_displays_timezone(self):
        response=self.create_via_route(starts_at="2027-07-15T18:00",timezone="Europe/Dublin")
        self.assertIn(b"Europe/Dublin",response.data)
        self.assertIn(b"18:00",response.data)
        with app.app_context():
            plan=db.session.scalar(db.select(CommunityPlan))
            self.assertEqual(plan.timezone,"Europe/Dublin")
            self.assertEqual(plan.starts_at.replace(tzinfo=None),datetime(2027,7,15,17,0))
        self.assertIn(b"Europe/Dublin",self.client.get("/plans").data)
        self.assertIn(b"Europe/Dublin",self.client.get("/plans/mine").data)

    def test_invalid_and_dst_transition_times_are_normal_form_errors(self):
        invalid=self.create_via_route(starts_at="2027-07-15T18:00",timezone="GMT+1")
        self.assertIn(b"Choose a valid timezone",invalid.data)
        xss=self.create_via_route(starts_at="2027-07-15T18:00",timezone="<script>alert(1)</script>")
        self.assertNotIn(b"<script>alert(1)</script>",xss.data)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;",xss.data)
        gap=self.create_via_route(starts_at="2027-03-28T01:30",timezone="Europe/Dublin")
        self.assertIn(b"does not exist",gap.data)
        fold=self.create_via_route(starts_at="2027-10-31T01:30",timezone="Europe/Dublin")
        self.assertIn(b"occurs twice",fold.data)
        with app.app_context(): self.assertEqual(db.session.scalar(db.select(db.func.count(CommunityPlan.id))),0)

    def test_edit_shows_local_wall_time_and_recalculates_when_zone_changes(self):
        self.create_via_route(starts_at="2027-07-15T18:00",timezone="Europe/Dublin")
        with app.app_context(): plan_id=db.session.scalar(db.select(CommunityPlan.id))
        edit_page=self.client.get(f"/plans/{plan_id}/edit").data
        self.assertIn(b'value="2027-07-15T18:00"',edit_page)
        self.client.post(f"/plans/{plan_id}/edit",data=self.data(starts_at="2027-07-15T18:00",timezone="America/New_York"))
        with app.app_context():
            plan=db.session.get(CommunityPlan,plan_id)
            self.assertEqual(plan.timezone,"America/New_York")
            self.assertEqual(plan.starts_at.replace(tzinfo=None),datetime(2027,7,15,22,0))

    def test_future_validation_and_ordering_use_actual_utc_instants(self):
        values=self.data(starts_at=datetime(2027,7,15,18,0),timezone="Asia/Tokyo",capacity=4)
        with self.assertRaisesRegex(PlanError,"future"):
            validate_plan_values(values,now=datetime(2027,7,15,17,30,tzinfo=timezone.utc))
        with app.app_context():
            self.direct_plan(title="Dublin first",starts_at=datetime(2035,7,15,18),timezone="Europe/Dublin")
            self.direct_plan(title="New York later",starts_at=datetime(2035,7,15,18),timezone="America/New_York")
            db.session.commit()
        page=self.client.get("/plans").data
        self.assertLess(page.index(b"Dublin first"),page.index(b"New York later"))

    def test_browse_uses_discovery_not_home_normalizes_city_and_orders(self):
        with app.app_context():
            early=self.direct_plan(title="Early plan",starts_at=utc_now()+timedelta(days=1))
            self.direct_plan(title="Later plan",starts_at=utc_now()+timedelta(days=2),city="mILAn")
            self.direct_plan(title="Wrong city",city="Cork")
            past=self.direct_plan(title="Past plan"); past.starts_at=utc_now()-timedelta(days=1)
            cancelled=self.direct_plan(title="Cancelled plan"); cancelled.status="cancelled"
            db.session.commit(); early_id=early.id
        page=self.client.get("/plans").data
        self.assertIn(b"Early plan",page); self.assertIn(b"Later plan",page); self.assertLess(page.index(b"Early plan"),page.index(b"Later plan"))
        self.assertNotIn(b"Wrong city",page); self.assertNotIn(b"Past plan",page); self.assertNotIn(b"Cancelled plan",page)
        self.assertIn(str(early_id).encode(),page)

    def test_join_requires_no_connection_and_duplicate_is_prevented(self):
        with app.app_context(): plan=self.direct_plan(); db.session.commit(); plan_id=plan.id
        self.login("Bob"); self.client.post(f"/plans/{plan_id}/join"); self.client.post(f"/plans/{plan_id}/join")
        with app.app_context(): self.assertEqual(db.session.scalar(db.select(db.func.count(PlanParticipant.user_id)).where(PlanParticipant.plan_id==plan_id)),2)

    def test_full_plan_rejects_final_extra_join_and_displays_full(self):
        with app.app_context():
            plan=self.direct_plan(capacity=2); db.session.commit(); plan_id=plan.id
        self.login("Bob"); self.client.post(f"/plans/{plan_id}/join")
        self.login("Cara"); page=self.client.post(f"/plans/{plan_id}/join",follow_redirects=True)
        self.assertIn(b"plan is full",page.data.lower()); self.assertIn(b"Full",page.data)
        with app.app_context(): self.assertEqual(db.session.scalar(db.select(db.func.count(PlanParticipant.user_id)).where(PlanParticipant.plan_id==plan_id)),2)

    def test_leave_frees_capacity_and_host_cannot_leave(self):
        with app.app_context(): plan=self.direct_plan(capacity=2); db.session.commit(); plan_id=plan.id
        self.login("Bob"); self.client.post(f"/plans/{plan_id}/join"); self.client.post(f"/plans/{plan_id}/leave")
        self.login("Alice"); response=self.client.post(f"/plans/{plan_id}/leave",follow_redirects=True); self.assertIn(b"Hosts cannot leave",response.data)
        self.login("Cara"); self.client.post(f"/plans/{plan_id}/join")
        with app.app_context(): self.assertEqual(db.session.scalar(db.select(db.func.count(PlanParticipant.user_id)).where(PlanParticipant.plan_id==plan_id)),2)

    def test_host_remove_permissions_self_protection_and_rejoin(self):
        with app.app_context(): plan=self.direct_plan(); db.session.add(PlanParticipant(plan_id=plan.id,user_id=self.ids["Bob"])); db.session.commit(); plan_id=plan.id
        self.login("Cara"); self.assertEqual(self.client.post(f"/plans/{plan_id}/participants/{self.ids['Bob']}/remove").status_code,404)
        self.login("Alice"); self.client.post(f"/plans/{plan_id}/participants/{self.ids['Alice']}/remove"); self.client.post(f"/plans/{plan_id}/participants/{self.ids['Bob']}/remove")
        self.login("Bob"); self.client.post(f"/plans/{plan_id}/join")
        with app.app_context(): self.assertIsNotNone(db.session.get(PlanParticipant,(plan_id,self.ids["Bob"])))

    def test_edit_authorization_and_capacity_floor(self):
        with app.app_context(): plan=self.direct_plan(); db.session.add(PlanParticipant(plan_id=plan.id,user_id=self.ids["Bob"])); db.session.commit(); plan_id=plan.id
        self.login("Bob"); self.assertEqual(self.client.get(f"/plans/{plan_id}/edit").status_code,404)
        self.login("Alice"); response=self.client.post(f"/plans/{plan_id}/edit",data=self.data(title="Updated plan",capacity="1"),follow_redirects=True); self.assertIn(b"between 2 and 20",response.data)
        response=self.client.post(f"/plans/{plan_id}/edit",data=self.data(title="Updated plan",capacity="2"),follow_redirects=True); self.assertIn(b"Updated plan",response.data)

    def test_cancel_permissions_history_and_read_only_controls(self):
        with app.app_context(): plan=self.direct_plan(); db.session.commit(); plan_id=plan.id
        self.login("Bob"); self.assertEqual(self.client.post(f"/plans/{plan_id}/cancel").status_code,404)
        self.login("Alice"); page=self.client.post(f"/plans/{plan_id}/cancel",follow_redirects=True); self.assertIn(b"Cancelled",page.data); self.assertNotIn(b"Edit plan",page.data)
        self.assertNotIn(b"Spider-Man",self.client.get("/plans").data); self.assertIn(b"Spider-Man",self.client.get("/plans/mine").data)

    def test_past_plan_is_read_only(self):
        with app.app_context(): plan=self.direct_plan(); plan.starts_at=utc_now()-timedelta(minutes=1); db.session.commit(); plan_id=plan.id
        page=self.client.get(f"/plans/{plan_id}").data; self.assertIn(b"Past",page); self.assertNotIn(b"Edit plan",page); self.assertNotIn(b"Join plan",page)
        self.assertIn(b"no longer open",self.client.post(f"/plans/{plan_id}/join",follow_redirects=True).data.lower())

    def test_my_plans_created_joined_and_privacy_safe_detail(self):
        with app.app_context():
            own=self.direct_plan(); other=self.direct_plan(creator="Bob",title="Bob plan"); db.session.add(PlanParticipant(plan_id=other.id,user_id=self.ids["Alice"])); db.session.commit(); own_id=own.id
        page=self.client.get("/plans/mine").data; self.assertIn(b"Spider-Man",page); self.assertIn(b"Bob plan",page)
        detail=self.client.get(f"/plans/{own_id}").data
        for private in (b"PrivateSurname",b"alice@example.com",b"Cork",b"1990-01-01"): self.assertNotIn(private,detail)
        self.assertIn(b"Use a public meeting place",self.client.get("/plans/create").data)

    def test_empty_state_and_category_filter(self):
        self.assertIn(b"No upcoming plans",self.client.get("/plans").data)
        with app.app_context(): self.direct_plan(category="coffee-food",title="Coffee plan"); self.direct_plan(category="games-social",title="Games plan"); db.session.commit()
        page=self.client.get("/plans?category=coffee-food&category=invalid").data; self.assertIn(b"Coffee plan",page); self.assertNotIn(b"Games plan",page)

    def test_csrf_on_all_mutations(self):
        with app.app_context(): plan=self.direct_plan(); db.session.commit(); plan_id=plan.id
        app.config["WTF_CSRF_ENABLED"]=True
        try:
            urls=(f"/plans/{plan_id}/join",f"/plans/{plan_id}/leave",f"/plans/{plan_id}/cancel",f"/plans/{plan_id}/participants/{self.ids['Bob']}/remove")
            for url in urls: self.assertEqual(self.client.post(url).status_code,400,url)
        finally: app.config["WTF_CSRF_ENABLED"]=False

    def test_database_constraints_mysql_ddl_and_locking_statement(self):
        for table in (CommunityPlan.__table__,PlanParticipant.__table__):
            compiled=str(CreateTable(table).compile(dialect=mysql.dialect())); self.assertIn("CREATE TABLE",compiled)
            for index in table.indexes: self.assertLessEqual(len(index.name),64); str(CreateIndex(index).compile(dialect=mysql.dialect()))
        with app.app_context():
            plan=self.direct_plan(capacity=2); db.session.commit(); join_plan(db.session,plan.id,self.ids["Bob"])
            with self.assertRaises(PlanError): join_plan(db.session,plan.id,self.ids["Cara"])


if __name__ == "__main__": unittest.main()
