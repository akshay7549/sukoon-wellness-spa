from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Booking, Room, Service, ServiceOption, Staff


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CustomerAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = get_user_model().objects.create_user(
            username="customer", password="test-password", email="shared@example.com",
            first_name="Customer Name",
        )
        cls.other = get_user_model().objects.create_user(
            username="other", password="test-password", email="shared@example.com",
        )
        cls.service = Service.objects.create(name="Relaxation Massage")
        ServiceOption.objects.create(service=cls.service, duration=60, price="1500.00")
        Staff.objects.create(name="Therapist")
        Room.objects.create(name="Wellness Room")
        cls.date = timezone.localdate() + timedelta(days=2)
        cls.owned = Booking.objects.create(
            customer=cls.customer, name="Customer Name", phone="9031640551",
            service=cls.service, appointment_date=cls.date, appointment_time=time(15),
            selected_duration=60, selected_price="1500.00",
        )
        cls.other_booking = Booking.objects.create(
            customer=cls.other, name="Private Guest", phone="9031640552",
            email="shared@example.com", service=cls.service,
            appointment_date=cls.date, appointment_time=time(16),
        )
        cls.guest_booking = Booking.objects.create(
            name="Guest", phone="9031640553", email="shared@example.com",
            service=cls.service, appointment_date=cls.date, appointment_time=time(17),
        )

    def booking_data(self, hour=10):
        return {
            "name": "Customer Name", "phone": "9031640551",
            "email": "shared@example.com", "service": self.service.pk,
            "duration": "60", "appointment_date": self.date.isoformat(),
            "appointment_time": f"{hour:02d}:00", "message": "",
            "customer": self.other.pk,
        }

    def registration_data(self):
        return {
            "first_name": "New Guest", "email": "new@example.com", "username": "newguest",
            "password1": "Relaxation!8237", "password2": "Relaxation!8237",
            "is_staff": "true", "is_superuser": "true",
        }

    def test_customer_login_goes_to_private_bookings(self):
        response = self.client.post(reverse("login"), {
            "username": "customer", "password": "test-password",
        })
        self.assertRedirects(response, reverse("my_bookings"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.customer.pk))

    def test_customer_can_use_existing_login_url_without_admin_redirect_loop(self):
        response = self.client.post(reverse("sukoon_admin:login"), {
            "username": "customer", "password": "test-password", "next": "/admin/",
        })
        self.assertRedirects(response, reverse("my_bookings"))

    def test_external_next_cannot_redirect_customer_away(self):
        response = self.client.post(reverse("login"), {
            "username": "customer", "password": "test-password",
            "next": "https://example.com/",
        })
        self.assertRedirects(response, reverse("my_bookings"))

    def test_booking_history_requires_sign_in(self):
        self.assertRedirects(
            self.client.get(reverse("my_bookings")),
            f'{reverse("login")}?next={reverse("my_bookings")}',
        )

    def test_customer_only_sees_owned_bookings_even_with_matching_email(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("my_bookings"))
        self.assertEqual(list(response.context["bookings"]), [self.owned])
        self.assertContains(response, "Relaxation Massage")
        self.assertContains(response, "1500.00")
        self.assertNotContains(response, "Private Guest")

    def test_customer_cannot_view_other_customer_or_unclaimed_guest_details(self):
        self.client.force_login(self.customer)
        for booking in (self.other_booking, self.guest_booking):
            with self.subTest(booking=booking.pk):
                self.assertEqual(self.client.get(
                    reverse("booking_success", args=[booking.pk]),
                ).status_code, 404)
        self.assertEqual(self.client.get(
            reverse("booking_success", args=[self.owned.pk]),
        ).status_code, 200)

    def test_anonymous_customer_cannot_guess_booking_details(self):
        self.assertEqual(self.client.get(
            reverse("booking_success", args=[self.owned.pk]),
        ).status_code, 404)

    def test_logged_in_booking_belongs_to_session_user_for_both_forms(self):
        self.client.force_login(self.customer)
        for hour, route in enumerate(("booking", "home"), start=10):
            with self.subTest(route=route):
                response = self.client.post(reverse(route), self.booking_data(hour))
                booking = Booking.objects.latest("pk")
                self.assertEqual(booking.customer, self.customer)
                self.assertRedirects(response, reverse("booking_success", args=[booking.pk]))
                self.assertEqual(booking.selected_price, 1500)

    def test_booking_form_prefills_account_details(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("booking"))
        self.assertEqual(response.context["booking_form"].initial["name"], "Customer Name")
        self.assertEqual(response.context["booking_form"].initial["email"], "shared@example.com")

    def test_registration_creates_customer_without_staff_privileges(self):
        response = self.client.post(reverse("register"), self.registration_data())
        self.assertRedirects(response, reverse("my_bookings"))
        user = get_user_model().objects.get(username="newguest")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("Relaxation!8237"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_registration_rejects_duplicate_username_and_password_mismatch(self):
        for changes in ({"username": "customer"}, {"password2": "different"}):
            with self.subTest(changes=changes):
                data = self.registration_data()
                data.update(changes)
                response = self.client.post(reverse("register"), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_registration_rejects_weak_password(self):
        data = self.registration_data()
        data.update(password1="123", password2="123")
        response = self.client.post(reverse("register"), data)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(username="newguest").exists())

    def test_guest_booking_is_claimed_only_from_original_session(self):
        response = self.client.post(reverse("booking"), self.booking_data())
        booking = Booking.objects.latest("pk")
        self.assertIsNone(booking.customer)
        self.assertRedirects(response, reverse("booking_success", args=[booking.pk]))
        self.assertEqual(Client().get(reverse("booking_success", args=[booking.pk])).status_code, 404)
        response = self.client.post(reverse("register"), self.registration_data())
        self.assertRedirects(response, reverse("my_bookings"))
        booking.refresh_from_db()
        self.assertEqual(booking.customer.username, "newguest")
        self.assertNotIn("guest_booking_ids", self.client.session)
        self.guest_booking.refresh_from_db()
        self.assertIsNone(self.guest_booking.customer)

    def test_guest_booking_is_saved_when_customer_signs_in(self):
        self.client.post(reverse("home"), self.booking_data())
        booking = Booking.objects.latest("pk")
        self.client.post(reverse("login"), {"username": "customer", "password": "test-password"})
        booking.refresh_from_db()
        self.assertEqual(booking.customer, self.customer)

    def test_customer_sign_out_clears_session_and_requires_post(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(self.client.get(reverse("my_bookings")), "/login/?next=/my-bookings/")

    def test_customer_registration_and_logout_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("register"), self.registration_data()).status_code, 403)
        client.force_login(self.customer)
        self.assertEqual(client.post(reverse("logout")).status_code, 403)

    def test_customer_can_register_and_sign_out_with_real_csrf_tokens(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("register"))
        data = self.registration_data()
        data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertRedirects(client.post(reverse("register"), data), reverse("my_bookings"))
        self.assertRedirects(client.post(reverse("logout"), {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        }), reverse("login"))
        self.assertNotIn("_auth_user_id", client.session)

    def test_signed_in_navigation_shows_my_bookings(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("my_bookings")}"')
        self.assertContains(response, "My Bookings")
