from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class AdminLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="staff", password="test-password", is_staff=True
        )
        cls.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="spa"))
        cls.customer = get_user_model().objects.create_user(
            username="customer", password="test-password"
        )
        cls.inactive = get_user_model().objects.create_user(
            username="inactive", password="test-password",
            is_staff=True, is_active=False,
        )

    def setUp(self):
        self.login_url = reverse("sukoon_admin:login")
        self.dashboard_url = reverse("sukoon_admin:index")

    def test_website_remains_public_and_links_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertContains(response, "Sign In")

    def test_anonymous_admin_routes_redirect_to_login(self):
        for url in (
            self.dashboard_url,
            reverse("sukoon_admin:spa_booking_changelist"),
            reverse("booking_bill", args=[1]),
        ):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), f"{self.login_url}?next={url}"
                )

    def test_login_page_has_branded_form_and_csrf_token(self):
        response = self.client.get(self.login_url)
        self.assertTemplateUsed(response, "spa/sign_in.html")
        self.assertNotContains(response, "Admin")
        for text in ("Sign In", "Create an account", "Username", "Password", "csrfmiddlewaretoken", "Back to website"):
            self.assertContains(response, text)

    def test_staff_can_login_and_view_dashboard(self):
        response = self.client.post(self.login_url, {
            "username": "staff", "password": "test-password",
        })
        self.assertRedirects(response, self.dashboard_url)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.staff.pk))

    def test_invalid_and_inactive_logins_are_rejected(self):
        for username, password in (
            ("staff", "wrong-password"),
            ("inactive", "test-password"),
        ):
            with self.subTest(username=username):
                response = self.client.post(self.login_url, {
                    "username": username, "password": password,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].non_field_errors())
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_nonstaff_cannot_access_admin(self):
        self.client.force_login(self.customer)
        self.assertRedirects(
            self.client.get(self.dashboard_url),
            f"{self.login_url}?next={self.dashboard_url}",
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(f"{self.login_url}?next={self.dashboard_url}"),
            reverse("my_bookings"),
        )

    def test_successful_login_preserves_requested_admin_page(self):
        target = reverse("sukoon_admin:spa_booking_changelist")
        response = self.client.post(self.login_url, {
            "username": "staff", "password": "test-password", "next": target,
        })
        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_external_redirect_is_rejected(self):
        response = self.client.post(self.login_url, {
            "username": "staff", "password": "test-password",
            "next": "https://example.com/",
        })
        self.assertRedirects(response, self.dashboard_url)

    def test_logout_clears_session_and_protects_dashboard_again(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, 'method="post"')
        self.assertContains(response, f'action="{reverse("sukoon_admin:logout")}"')
        self.assertRedirects(
            self.client.post(reverse("sukoon_admin:logout")), reverse("login"),
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(
            self.client.get(self.dashboard_url),
            f"{self.login_url}?next={self.dashboard_url}",
        )

    def test_login_and_logout_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.login_url, {
            "username": "staff", "password": "test-password",
        }).status_code, 403)
        client.force_login(self.staff)
        self.assertEqual(client.post(reverse("sukoon_admin:logout")).status_code, 403)
