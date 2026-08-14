"""Sprint 5 profile-photo security and completion integration checks."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from app import app, db
from models import ConnectionIntent, Interest, Language, Profile
from profile_photo_storage import LocalProfilePhotoStorage, ProfilePhotoStorage


register_heif_opener()


class ProfilePhotoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    def setUp(self):
        self.upload_folder = Path(tempfile.mkdtemp(prefix="friendly-photo-tests-"))
        app.config["PROFILE_UPLOAD_FOLDER"] = self.upload_folder
        with app.app_context():
            db.drop_all()
            db.create_all()
            app.test_cli_runner().invoke(args=["seed-profile-data"])
        self.client = app.test_client()
        self.register_and_login()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
        shutil.rmtree(self.upload_folder, ignore_errors=True)

    def register_and_login(self):
        self.client.post("/register", data={
            "first_name": "Sofia", "last_name": "Private", "email": "photo@example.com",
            "date_of_birth": "1996-08-12", "password": "SecurePass1", "confirm_password": "SecurePass1",
        })
        self.client.post("/login", data={"email": "photo@example.com", "password": "SecurePass1"})

    def profile_data(self, photo=None, filename="portrait.jpg", bio=""):
        with app.app_context():
            languages = [item.id for item in db.session.scalars(db.select(Language).limit(2))]
            interests = [item.id for item in db.session.scalars(db.select(Interest).limit(3))]
            intent = db.session.scalar(db.select(ConnectionIntent)).id
        data = {
            "date_of_birth": "1996-08-12", "gender": "woman", "gender_description": "",
            "bio": bio, "home_country_code": "IE", "home_city": "Cork",
            "discovery_country_code": "IT", "discovery_city": "Milan", "languages": languages,
            "interests": interests, "connection_intents": [intent], "open_to_connections": "y",
            "photo_crop_x": "0.5", "photo_crop_y": "0.5", "photo_crop_zoom": "1",
        }
        if photo is not None:
            data["profile_photo"] = (photo, filename)
        return data

    @staticmethod
    def image_file(image_format="JPEG", size=(80, 60)):
        stream = io.BytesIO()
        mode = "RGBA" if image_format in {"PNG", "GIF"} else "RGB"
        color = (83, 143, 116, 180) if mode == "RGBA" else (83, 143, 116)
        Image.new(mode, size, color).save(stream, format=image_format)
        stream.seek(0)
        return stream

    def upload(self, image_format="JPEG", extension="jpg"):
        response = self.client.post(
            "/profile/edit",
            data=self.profile_data(self.image_file(image_format), f"my-original-name.{extension}"),
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        response.get_data()
        response.close()
        return response

    def stored_photo(self):
        with app.app_context():
            profile = db.session.scalar(db.select(Profile))
            return profile.profile_photo_key if profile else None

    def stored_path(self, key):
        return self.upload_folder.joinpath(*key.split("/"))

    def test_unauthenticated_users_cannot_modify_photos(self):
        anonymous = app.test_client()
        self.assertEqual(anonymous.post("/profile/edit").status_code, 302)
        self.assertEqual(anonymous.post("/profile/photo/remove").status_code, 302)

    def test_common_photo_formats_are_normalized_to_webp(self):
        formats = (
            ("JPEG", "jpg"), ("JPEG", "JPEG"), ("JPEG", "JPG"), ("PNG", "png"),
            ("WEBP", "webp"), ("GIF", "gif"), ("BMP", "bmp"), ("TIFF", "tiff"),
            ("HEIF", "heic"),
        )
        for image_format, extension in formats:
            with self.subTest(image_format=image_format):
                response = self.upload(image_format, extension)
                self.assertEqual(response.status_code, 200)
                key = self.stored_photo()
                self.assertRegex(key, r"^profiles/[0-9a-f]{32}\.webp$")
                self.assertNotIn("my-original-name", key)
                self.assertTrue(self.stored_path(key).is_file())
                with Image.open(self.stored_path(key)) as stored:
                    self.assertEqual(stored.format, "WEBP")
                    self.assertEqual(stored.width, stored.height)
                    self.assertLessEqual(stored.width, 800)

    def test_crop_coordinates_are_applied_and_validated(self):
        source = Image.new("RGB", (1200, 800), "red")
        source.paste("blue", (600, 0, 1200, 800))
        stream = io.BytesIO()
        source.save(stream, "JPEG", quality=100)
        stream.seek(0)
        data = self.profile_data(stream, "wide.jpg")
        data.update({"photo_crop_x": "0.75", "photo_crop_y": "0.5", "photo_crop_zoom": "1"})
        self.client.post("/profile/edit", data=data, content_type="multipart/form-data", follow_redirects=True)
        with Image.open(self.stored_path(self.stored_photo())) as stored:
            self.assertEqual(stored.size, (800, 800))
            red, _green, blue = stored.getpixel((400, 400))
            self.assertGreater(blue, red)

        existing = self.stored_photo()
        invalid = self.profile_data(self.image_file(), "invalid-crop.jpg")
        invalid["photo_crop_zoom"] = "99"
        response = self.client.post("/profile/edit", data=invalid, content_type="multipart/form-data")
        self.assertIn(b"crop settings are invalid", response.data)
        self.assertEqual(self.stored_photo(), existing)
        self.assertTrue(self.stored_path(existing).exists())

    def test_invalid_extension_fake_and_corrupted_images_are_rejected(self):
        fake = self.client.post("/profile/edit", data=self.profile_data(io.BytesIO(b"MZ executable"), "photo.jpg"), content_type="multipart/form-data")
        self.assertIn(b"invalid or corrupted", fake.data)
        corrupted = self.client.post("/profile/edit", data=self.profile_data(io.BytesIO(b"\x89PNG\r\n\x1a\ncorrupt"), "photo.png"), content_type="multipart/form-data")
        self.assertIn(b"invalid or corrupted", corrupted.data)
        self.assertIsNone(self.stored_photo())

    def test_file_over_five_mb_is_rejected(self):
        with io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)) as oversized:
            response = self.client.post(
                "/profile/edit",
                data=self.profile_data(oversized, "large.jpg"),
                content_type="multipart/form-data",
            )
            request_stream = response.request.environ["wsgi.input"]
            try:
                self.assertIn(b"5 MB or smaller", response.data)
            finally:
                # Werkzeug spools this multipart body to a temporary file above 500 KB.
                request_stream.close()
                response.close()

    def test_photo_displays_and_controlled_route_rejects_arbitrary_paths(self):
        self.upload()
        filename = self.stored_photo()
        page = self.client.get("/profile")
        self.assertIn(f"/profile/photo/{filename}".encode(), page.data)
        image = self.client.get(f"/profile/photo/{filename}")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.mimetype, "image/webp")
        image.close()
        self.assertEqual(self.client.get("/profile/photo/app.py").status_code, 404)
        self.assertEqual(self.client.get("/profile/photo/../config.py").status_code, 404)

    def test_local_storage_implements_storage_abstraction(self):
        storage = LocalProfilePhotoStorage(self.upload_folder)
        self.assertIsInstance(storage, ProfilePhotoStorage)
        key = "profiles/" + "a" * 32 + ".webp"
        storage.save(key, b"processed-photo")
        self.assertTrue(storage.exists(key))
        with storage.open(key) as stored:
            self.assertEqual(stored.read(), b"processed-photo")
        self.assertTrue(storage.delete(key))
        self.assertFalse(storage.exists(key))
        with self.assertRaises(ValueError):
            storage.save("../secret.webp", b"unsafe")

    def test_replacement_deletes_old_only_after_success(self):
        self.upload()
        original = self.stored_photo()
        self.assertTrue(self.stored_path(original).exists())
        self.upload("PNG", "png")
        replacement = self.stored_photo()
        self.assertNotEqual(original, replacement)
        self.assertFalse(self.stored_path(original).exists())
        self.assertTrue(self.stored_path(replacement).exists())

        failed = self.client.post("/profile/edit", data=self.profile_data(io.BytesIO(b"not an image"), "bad.jpg"), content_type="multipart/form-data")
        self.assertIn(b"invalid or corrupted", failed.data)
        self.assertEqual(self.stored_photo(), replacement)
        self.assertTrue(self.stored_path(replacement).exists())

    def test_remove_photo_deletes_file_and_restores_initials(self):
        self.upload()
        filename = self.stored_photo()
        response = self.client.post("/profile/photo/remove", follow_redirects=True)
        self.assertIn(b"has been removed", response.data)
        self.assertIsNone(self.stored_photo())
        self.assertFalse(self.stored_path(filename).exists())
        page = self.client.get("/profile")
        self.assertNotIn(b"profile-avatar-image", page.data)
        self.assertIn(b">S</div>", page.data)

    def test_immediate_preview_javascript_is_wired(self):
        page = self.client.get("/profile/edit")
        self.assertIn(b'accept="image/*"', page.data)
        self.assertIn(b"data-photo-preview", page.data)
        javascript = Path("static/js/profile.js").read_text(encoding="utf-8")
        self.assertIn("URL.createObjectURL", javascript)
        self.assertIn("URL.revokeObjectURL", javascript)
        self.assertIn('addEventListener("change", updatePhotoPreview)', javascript)
        self.assertIn('addEventListener("pointermove"', javascript)
        self.assertIn('addEventListener("keydown"', javascript)
        self.assertIn('addEventListener("input", renderCrop)', javascript)
        self.assertIn("resetCrop", javascript)
        self.assertIn("const renderedWidth = naturalWidth * scale", javascript)
        self.assertIn("const renderedHeight = naturalHeight * scale", javascript)
        self.assertIn("const maxOffsetX = Math.max(0, (renderedWidth - viewportWidth) / 2)", javascript)
        self.assertIn("const maxOffsetY = Math.max(0, (renderedHeight - viewportHeight) / 2)", javascript)
        self.assertIn("event.clientX - dragStart.x", javascript)
        self.assertIn("event.clientY - dragStart.y", javascript)
        self.assertIn("translate3d", javascript)
        self.assertIn("cropXInput.value", javascript)
        self.assertIn("cropYInput.value", javascript)

    def test_completion_percentage_photo_and_optional_bio(self):
        self.client.post("/profile/edit", data=self.profile_data(), follow_redirects=True)
        with app.app_context():
            profile = db.session.scalar(db.select(Profile))
            self.assertFalse(profile.is_complete)
            self.assertEqual(profile.completion_percentage, 88)
            self.assertEqual(profile.missing_completion_items, ["a profile photo"])
        dashboard = self.client.get("/dashboard")
        self.assertIn(b"Profile 88% complete", dashboard.data)
        self.assertIn(b"Add profile photo", dashboard.data)

        self.upload()
        with app.app_context():
            profile = db.session.scalar(db.select(Profile))
            self.assertTrue(profile.is_complete)
            self.assertEqual(profile.completion_percentage, 100)
            self.assertFalse(bool(profile.bio))
        self.assertIn(b"Profile complete", self.client.get("/dashboard").data)


if __name__ == "__main__":
    unittest.main()
