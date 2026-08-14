"""Sprint 6 discovery eligibility, filtering, ranking and privacy checks."""

import os
import tempfile
import unittest
from datetime import date


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["SECRET_KEY"] = "test-only-secret"

from app import app, db  # noqa: E402
from discovery import PER_PAGE, years_ago  # noqa: E402
from models import ConnectionIntent, Interest, Language, Profile, User  # noqa: E402


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()
            self.assertEqual(app.test_cli_runner().invoke(args=["seed-profile-data"]).exit_code, 0)
            self.languages = list(db.session.scalars(db.select(Language).order_by(Language.name).limit(4)))
            self.interests = list(db.session.scalars(db.select(Interest).order_by(Interest.id).limit(6)))
            self.intentions = list(db.session.scalars(db.select(ConnectionIntent).order_by(ConnectionIntent.id).limit(3)))
            self.viewer = self.make_person("Viewer", "viewer@example.com")
            self.viewer_id = self.viewer.user_id
            db.session.commit()
        self.client = app.test_client()
        self.login_as(self.viewer_id)

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    def login_as(self, user_id):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id

    def make_person(
        self,
        first_name,
        email,
        *,
        age=30,
        city="Milan",
        country="IT",
        gender="woman",
        open_to_connections=True,
        complete=True,
        language_indexes=(0,),
        interest_indexes=(0, 1, 2),
        intention_indexes=(0,),
    ):
        user = User(
            first_name=first_name,
            last_name="PrivateSurname",
            email=email,
            password_hash="private-password-hash",
            date_of_birth=years_ago(age),
        )
        profile = Profile(
            user=user,
            gender=gender,
            bio=f"Public bio for {first_name}",
            profile_photo_key=f"profiles/{first_name.lower()}.webp" if complete else None,
            home_country_code="UA",
            home_city="Private Home",
            discovery_country_code=country,
            discovery_city=city,
            open_to_connections=open_to_connections,
        )
        profile.languages = [self.languages[index] for index in language_indexes]
        profile.interests = [self.interests[index] for index in interest_indexes]
        profile.connection_intents = [self.intentions[index] for index in intention_indexes]
        db.session.add(user)
        db.session.flush()
        return profile

    def discover(self, query=""):
        return self.client.get(f"/discover{query}", follow_redirects=False)

    def assert_visible(self, response, *names):
        for name in names:
            self.assertIn(name.encode(), response.data)

    def assert_hidden(self, response, *names):
        for name in names:
            self.assertNotIn(name.encode(), response.data)

    def test_authentication_and_completion_guards(self):
        anonymous = app.test_client().get("/discover")
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/login", anonymous.location)
        with app.app_context():
            viewer = db.session.get(User, self.viewer_id)
            viewer.profile.profile_photo_key = None
            db.session.commit()
        response = self.discover()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/profile/edit", response.location)

    def test_complete_user_can_access_and_current_user_is_excluded(self):
        with app.app_context():
            self.make_person("Local", "local@example.com")
            db.session.commit()
        response = self.discover()
        self.assertEqual(response.status_code, 200)
        self.assert_visible(response, "Local")
        self.assert_hidden(response, 'data-user-id="1"')

    def test_candidate_eligibility_rules(self):
        with app.app_context():
            self.make_person("Incomplete", "incomplete@example.com", complete=False)
            self.make_person("Closed", "closed@example.com", open_to_connections=False)
            self.make_person("OtherCountry", "country@example.com", country="IE")
            self.make_person("OtherCity", "city@example.com", city="Rome")
            self.make_person("Normalized", "normal@example.com", city="  mILAn  ")
            underage = self.make_person("Underage", "underage@example.com")
            underage.user.date_of_birth = years_ago(17)
            db.session.commit()
        response = self.discover()
        self.assert_visible(response, "Normalized")
        self.assert_hidden(response, "Incomplete", "Closed", "OtherCountry", "OtherCity", "Underage")

    def test_age_minimum_maximum_and_invalid_ranges(self):
        with app.app_context():
            self.make_person("Twenty", "20@example.com", age=20)
            self.make_person("Thirty", "30@example.com", age=30)
            self.make_person("Forty", "40@example.com", age=40)
            db.session.commit()
        minimum = self.discover("?age_min=30")
        self.assert_visible(minimum, "Thirty", "Forty")
        self.assert_hidden(minimum, "Twenty")
        maximum = self.discover("?age_max=30")
        self.assert_visible(maximum, "Twenty", "Thirty")
        self.assert_hidden(maximum, "Forty")
        invalid = self.discover("?age_min=60&age_max=20")
        self.assertIn(b"Minimum age cannot be greater", invalid.data)
        self.assert_visible(invalid, "Twenty", "Thirty", "Forty")

    def test_gender_is_explicit_and_no_filter_does_not_restrict(self):
        with app.app_context():
            self.make_person("WomanCandidate", "woman@example.com", gender="woman")
            self.make_person("ManCandidate", "man@example.com", gender="man")
            self.make_person("NonbinaryCandidate", "nb@example.com", gender="non_binary")
            db.session.commit()
        unfiltered = self.discover()
        self.assert_visible(unfiltered, "WomanCandidate", "ManCandidate", "NonbinaryCandidate")
        filtered = self.discover("?gender=man")
        self.assert_visible(filtered, "ManCandidate")
        self.assert_hidden(filtered, "WomanCandidate", "NonbinaryCandidate")

    def test_language_filters_use_or(self):
        with app.app_context():
            first = self.make_person("FirstLanguage", "l1@example.com", language_indexes=(0,))
            second = self.make_person("SecondLanguage", "l2@example.com", language_indexes=(1,))
            self.make_person("ThirdLanguage", "l3@example.com", language_indexes=(2,))
            first_id, second_id = first.languages[0].id, second.languages[0].id
            db.session.commit()
        single = self.discover(f"?languages={first_id}")
        self.assert_visible(single, "FirstLanguage")
        self.assert_hidden(single, "SecondLanguage", "ThirdLanguage")
        multiple = self.discover(f"?languages={first_id}&languages={second_id}")
        self.assert_visible(multiple, "FirstLanguage", "SecondLanguage")
        self.assert_hidden(multiple, "ThirdLanguage")

    def test_interest_filters_use_or(self):
        with app.app_context():
            first = self.make_person("FirstInterest", "i1@example.com", interest_indexes=(0, 2, 3))
            second = self.make_person("SecondInterest", "i2@example.com", interest_indexes=(1, 4, 5))
            first_id, second_id = self.interests[2].id, self.interests[4].id
            db.session.commit()
        self.assert_visible(self.discover(f"?interests={first_id}"), "FirstInterest")
        both = self.discover(f"?interests={first_id}&interests={second_id}")
        self.assert_visible(both, "FirstInterest", "SecondInterest")

    def test_intention_filters_use_or(self):
        with app.app_context():
            self.make_person("FirstIntent", "n1@example.com", intention_indexes=(0,))
            self.make_person("SecondIntent", "n2@example.com", intention_indexes=(1,))
            self.make_person("ThirdIntent", "n3@example.com", intention_indexes=(2,))
            first_id, second_id = self.intentions[0].id, self.intentions[1].id
            db.session.commit()
        single = self.discover(f"?intentions={first_id}")
        self.assert_visible(single, "FirstIntent")
        self.assert_hidden(single, "SecondIntent")
        multiple = self.discover(f"?intentions={first_id}&intentions={second_id}")
        self.assert_visible(multiple, "FirstIntent", "SecondIntent")
        self.assert_hidden(multiple, "ThirdIntent")

    def test_filter_categories_combine_with_and_and_invalid_ids_are_ignored(self):
        with app.app_context():
            matching = self.make_person("MatchesAll", "all@example.com", gender="man", language_indexes=(1,), interest_indexes=(1, 3, 4), intention_indexes=(1,))
            self.make_person("WrongGender", "wrong@example.com", gender="woman", language_indexes=(1,), interest_indexes=(1, 3, 4), intention_indexes=(1,))
            language_id, interest_id, intention_id = matching.languages[0].id, self.interests[3].id, matching.connection_intents[0].id
            db.session.commit()
        query = f"?gender=man&languages={language_id}&interests={interest_id}&intentions={intention_id}"
        response = self.discover(query)
        self.assert_visible(response, "MatchesAll")
        self.assert_hidden(response, "WrongGender")
        self.assertEqual(self.discover("?languages=999999&gender=invalid").status_code, 200)

    def test_ranking_weights_and_relevance_reasons(self):
        with app.app_context():
            self.make_person("FewSignals", "few@example.com", language_indexes=(3,), interest_indexes=(3, 4, 5), intention_indexes=(2,))
            self.make_person("SharedLanguage", "lang@example.com", language_indexes=(0,), interest_indexes=(3, 4, 5), intention_indexes=(2,))
            self.make_person("SharedIntent", "intent@example.com", language_indexes=(3,), interest_indexes=(3, 4, 5), intention_indexes=(0,))
            self.make_person("SharedInterests", "interest@example.com", language_indexes=(3,), interest_indexes=(0, 1, 2), intention_indexes=(2,))
            db.session.commit()
        response = self.discover()
        html = response.get_data(as_text=True)
        self.assertLess(html.index("SharedInterests"), html.index("SharedLanguage"))
        self.assertLess(html.index("SharedLanguage"), html.index("SharedIntent"))
        self.assertIn("3 interests in common", html)
        self.assertIn("You both speak", html)
        self.assertIn("Also looking for", html)
        self.assertNotIn("compatible", html.lower())
        self.assertNotIn("relevance_score", html)

    def test_cards_and_public_profile_do_not_expose_private_fields(self):
        with app.app_context():
            candidate = self.make_person("PublicPerson", "secret-address@example.com")
            candidate_id = candidate.user_id
            db.session.commit()
        cards = self.discover()
        profile = self.client.get(f"/people/{candidate_id}")
        for response in (cards, profile):
            self.assertEqual(response.status_code, 200)
            self.assert_visible(response, "PublicPerson", "Milan")
            self.assert_hidden(response, "PrivateSurname", "secret-address@example.com", "Private Home", "private-password-hash")

    def test_public_profile_security_and_owner_redirect(self):
        with app.app_context():
            available = self.make_person("Available", "available@example.com")
            unavailable = self.make_person("Unavailable", "unavailable@example.com", complete=False)
            available_id, unavailable_id = available.user_id, unavailable.user_id
            db.session.commit()
        self.assertEqual(self.client.get(f"/people/{available_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/people/{unavailable_id}").status_code, 404)
        self.assertEqual(self.client.get("/people/999999").status_code, 404)
        owner = self.client.get(f"/people/{self.viewer_id}")
        self.assertEqual(owner.status_code, 302)
        self.assertIn("/profile", owner.location)
        self.assertEqual(app.test_client().get(f"/people/{available_id}").status_code, 302)

    def test_pagination_and_filter_persistence(self):
        with app.app_context():
            for index in range(PER_PAGE + 2):
                self.make_person(f"Person{index:02}", f"p{index}@example.com", gender="woman")
            db.session.commit()
        first = self.discover("?gender=woman")
        self.assertEqual(first.get_data(as_text=True).count('class="person-card"'), PER_PAGE)
        self.assertIn(b"Page 1 of 2", first.data)
        self.assertIn(b"gender=woman&amp;page=2", first.data)
        second = self.discover("?gender=woman&page=2")
        self.assertEqual(second.get_data(as_text=True).count('class="person-card"'), 2)
        self.assertIn(b"Page 2 of 2", second.data)

    def test_clear_filters_and_both_empty_states(self):
        empty = self.discover()
        self.assertIn(b"No one is showing up in Milan yet", empty.data)
        with app.app_context():
            self.make_person("LocalPerson", "local2@example.com", gender="woman")
            db.session.commit()
        filtered = self.discover("?gender=man")
        self.assertIn(b"No profiles match these filters", filtered.data)
        self.assertIn(b"Clear filters", filtered.data)
        self.assert_visible(self.discover(), "LocalPerson")

    def test_discovery_language_search_wiring(self):
        response = self.discover()
        self.assertIn(b'id="discover-language-search"', response.data)
        self.assertIn(b'data-filter-options', response.data)
        self.assertIn(b"Mandarin Chinese", response.data)
        script = (app.static_folder + "/js/discover.js")
        with open(script, encoding="utf-8") as source:
            self.assertIn('search.addEventListener("input"', source.read())


if __name__ == "__main__":
    unittest.main()
