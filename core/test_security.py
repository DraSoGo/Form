from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model


@override_settings(
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        }
    },
)
class BoundaryTests(TestCase):
    def test_sensitive_pages_no_store_and_csp(self):
        user = get_user_model().objects.create_user(
            "boundary", password="Boundary test password 2026!"
        )
        self.client.force_login(user)
        result = self.client.get("/")
        self.assertEqual(result.status_code, 200)
        self.assertIn("no-store", result["Cache-Control"])
        self.assertIn("frame-ancestors 'none'", result["Content-Security-Policy"])

    def test_oversize_body_rejected_before_parsing(self):
        result = self.client.post(
            "/login/",
            data=b"",
            content_type="application/octet-stream",
            CONTENT_LENGTH=str(13 * 1024 * 1024),
        )
        self.assertEqual(result.status_code, 413)
