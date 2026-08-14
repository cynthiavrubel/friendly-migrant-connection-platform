"""Sprint 4 profile integration and validation checks."""

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-only-secret"

from app import app, db  # noqa: E402
from models import ConnectionIntent, Interest, Language, Profile, User  # noqa: E402


class ProfileFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()
            runner = app.test_cli_runner()
            self.assertEqual(runner.invoke(args=["seed-profile-data"]).exit_code, 0)
        self.client = app.test_client()

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    def register(self, email="sofia@example.com", birth_date="1996-08-12"):
        return self.client.post("/register", data={
            "first_name": "Sofia", "last_name": "Private", "email": email,
            "date_of_birth": birth_date, "password": "SecurePass1", "confirm_password": "SecurePass1",
        }, follow_redirects=True)

    def login(self, email="sofia@example.com"):
        return self.client.post("/login", data={"email": email, "password": "SecurePass1"}, follow_redirects=True)

    def valid_profile_data(self):
        with app.app_context():
            languages = [item.id for item in db.session.scalars(db.select(Language).limit(2))]
            interests = [item.id for item in db.session.scalars(db.select(Interest).limit(3))]
            intent = db.session.scalar(db.select(ConnectionIntent)).id
        return {
            "date_of_birth": "1996-08-12", "gender": "woman", "gender_description": "",
            "bio": "Recently moved and ready to explore.", "home_country_code": "IE", "home_city": "Cork",
            "discovery_country_code": "IT", "discovery_city": "Milan", "languages": languages,
            "interests": interests, "connection_intents": [intent], "open_to_connections": "y",
        }

    def authenticated_user(self):
        self.register()
        self.login()

    def test_home_registration_login_and_logout_remain_working(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        response = self.register()
        self.assertIn(b"account has been created", response.data)
        response = self.login()
        self.assertIn(b"Welcome to Friendly", response.data)
        response = self.client.post("/logout", follow_redirects=True)
        self.assertIn(b"logged out", response.data)

    def test_registration_rejects_underage_and_future_dates(self):
        underage = date.today().replace(year=date.today().year - 17).isoformat()
        self.assertIn(b"at least 18", self.register("young@example.com", underage).data)
        future = date.today().replace(year=date.today().year + 1).isoformat()
        self.assertIn(b"cannot be in the future", self.register("future@example.com", future).data)

    def test_profile_requires_authentication(self):
        response = self.client.get("/profile/edit")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_create_view_edit_and_no_duplicate_profile(self):
        self.authenticated_user()
        response = self.client.post("/profile/edit", data=self.valid_profile_data(), follow_redirects=True)
        self.assertIn(b"Sofia,", response.data)
        self.assertIn(b"Milan", response.data)
        self.assertNotIn(b"Private", response.data)
        self.assertNotIn(b"1996-08-12", response.data)
        self.assertNotIn(b"sofia@example.com", response.data)
        with app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count(Profile.id))), 1)
        changed = self.valid_profile_data()
        changed.update({"discovery_city": "Rome", "open_to_connections": ""})
        response = self.client.post("/profile/edit", data=changed, follow_redirects=True)
        self.assertIn(b"Rome", response.data)
        self.assertIn(b"Not currently open", response.data)
        with app.app_context():
            profile = db.session.scalar(db.select(Profile))
            self.assertEqual(profile.home_city, "Cork")
            self.assertEqual(profile.discovery_city, "Rome")
            self.assertEqual(db.session.scalar(db.select(db.func.count(Profile.id))), 1)

    def test_profile_selection_and_age_validation(self):
        self.authenticated_user()
        data = self.valid_profile_data()
        data["languages"] = []
        data["interests"] = data["interests"][:2]
        data["connection_intents"] = []
        response = self.client.post("/profile/edit", data=data)
        self.assertIn(b"Choose at least one language", response.data)
        self.assertIn(b"Choose between 3 and 12 interests", response.data)
        self.assertIn(b"Choose at least one connection intention", response.data)
        data = self.valid_profile_data()
        data["date_of_birth"] = date.today().replace(year=date.today().year - 16).isoformat()
        self.assertIn(b"at least 18", self.client.post("/profile/edit", data=data).data)

    def test_exact_age_before_and_after_birthday(self):
        today = date.today()
        with app.app_context():
            user = User(first_name="A", last_name="B", email="age@example.com", password_hash="x")
            birthday_passed = date(today.year - 30, today.month, today.day)
            user.date_of_birth = birthday_passed
            self.assertEqual(user.age, 30)
            if (today.month, today.day) != (12, 31):
                future_month = today.month + 1 if today.month < 12 else today.month
                future_day = 1 if today.month < 12 else today.day + 1
                user.date_of_birth = date(today.year - 30, future_month, future_day)
                self.assertEqual(user.age, 29)

    def test_seed_command_is_idempotent(self):
        with app.app_context():
            runner = app.test_cli_runner()
            first_counts = (
                db.session.scalar(db.select(db.func.count(Language.id))),
                db.session.scalar(db.select(db.func.count(Interest.id))),
                db.session.scalar(db.select(db.func.count(ConnectionIntent.id))),
            )
            self.assertEqual(runner.invoke(args=["seed-profile-data"]).exit_code, 0)
            second_counts = (
                db.session.scalar(db.select(db.func.count(Language.id))),
                db.session.scalar(db.select(db.func.count(Interest.id))),
                db.session.scalar(db.select(db.func.count(ConnectionIntent.id))),
            )
            self.assertEqual(first_counts, second_counts)
            self.assertGreaterEqual(first_counts[0], 170)
            self.assertEqual(first_counts[1:], (28, 7))

    def test_global_language_catalogue_and_unique_codes(self):
        expected = {
            "Mandarin Chinese": "cmn", "Cantonese": "yue", "Japanese": "ja",
            "Korean": "ko", "Hindi": "hi", "Arabic": "ar", "Yoruba": "yo",
            "Igbo": "ig", "Swahili": "sw",
        }
        with app.app_context():
            languages = {item.name: item.code for item in db.session.scalars(db.select(Language))}
            for name, code in expected.items():
                self.assertEqual(languages.get(name), code)
            total = db.session.scalar(db.select(db.func.count(Language.id)))
            distinct_codes = db.session.scalar(db.select(db.func.count(db.distinct(Language.code))))
            self.assertEqual(total, distinct_codes)

    def test_reseed_preserves_profile_language_associations(self):
        self.authenticated_user()
        self.client.post("/profile/edit", data=self.valid_profile_data())
        with app.app_context():
            profile = db.session.scalar(db.select(Profile))
            language_ids = {language.id for language in profile.languages}
            self.assertTrue(language_ids)
            result = app.test_cli_runner().invoke(args=["seed-profile-data"])
            self.assertEqual(result.exit_code, 0)
            db.session.expire_all()
            profile = db.session.get(Profile, profile.id)
            self.assertEqual({language.id for language in profile.languages}, language_ids)

    def test_language_search_ui_is_wired_and_edit_selection_is_prepopulated(self):
        self.authenticated_user()
        profile_data = self.valid_profile_data()
        self.client.post("/profile/edit", data=profile_data)
        response = self.client.get("/profile/edit")
        self.assertIn(b'id="language-search"', response.data)
        self.assertIn(b'data-language-options', response.data)
        self.assertIn(b'data-language-status', response.data)
        self.assertIn(b'Here...', response.data)
        for language_id in profile_data["languages"]:
            self.assertIn(f'value="{language_id}" checked'.encode(), response.data)
        script = (ROOT / "static" / "js" / "profile.js").read_text(encoding="utf-8")
        self.assertIn('languageSearch?.addEventListener("input", updateLanguageSelector)', script)
        self.assertIn('option.hidden = !matches', script)


if __name__ == "__main__":
    unittest.main()
