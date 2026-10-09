from datetime import time, timedelta
from decimal import Decimal
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from .bill_views import booking_bill
from .models import Booking, Service, ServiceOption


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BookingBillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="billingstaff", password="test-password", is_staff=True,
        )
        cls.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="spa"))
        cls.customer = get_user_model().objects.create_user(
            username="billcustomer", password="test-password",
        )
        cls.service = Service.objects.create(name="Swedish Massage")
        cls.option = ServiceOption.objects.create(
            service=cls.service, duration=60, price="2400.00",
        )
        cls.booking = Booking.objects.create(
            customer=cls.customer, name="Bill Customer", phone="9031640551",
            email="bill@example.com", service=cls.service,
            appointment_date=timezone.localdate() + timedelta(days=1),
            appointment_time=time(10), end_time=time(11),
            selected_duration=60, selected_price="1500.00", status="confirmed",
        )

    def setUp(self):
        self.url = reverse("booking_bill", args=[self.booking.pk])

    def test_generate_bill_link_renders_the_selected_booking(self):
        self.client.force_login(self.staff)
        dashboard = self.client.get(reverse("sukoon_admin:index"))
        match = re.search(r'<a\b[^>]*href="([^"]+)"[^>]*>\s*Generate Bill\s*</a>', dashboard.content.decode())
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), self.url)
        self.assertIs(resolve(self.url).func, booking_bill)
        response = self.client.get(match.group(1))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/bill.html")
        for text in (
            "Booking Bill", "Bill Customer", "bill@example.com", "9031640551",
            "Swedish Massage", "60 min", "₹1500.00", "Confirmed", "Print / Save PDF",
            f"SW-{self.booking.pk:06d}",
        ):
            self.assertContains(response, text)
        self.assertNotContains(response, "from django.urls")
        self.assertNotContains(response, "urlpatterns")
        self.assertEqual(response.context["price"], Decimal("1500.00"))
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(response, 'href="https://sukoonwellnessandspa.in/connect/"')
        self.assertContains(response, 'src="data:image/png;base64,')
        self.assertContains(response, "Scan to stay connected")

    def test_recorded_charge_survives_changes_to_service_options(self):
        self.client.force_login(self.staff)
        self.option.price = Decimal("9999.00")
        self.option.save()
        response = self.client.get(self.url)
        self.assertContains(response, "₹1500.00")
        self.assertNotContains(response, "9999.00")

    def test_legacy_missing_snapshots_do_not_crash_or_invent_a_price(self):
        self.client.force_login(self.staff)
        self.booking.selected_duration = None
        self.booking.selected_price = None
        self.booking.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not recorded")
        self.assertContains(response, "Confirm the amount")
        self.assertNotContains(response, "2400.00")

    def test_zero_charge_is_rendered_as_zero(self):
        self.client.force_login(self.staff)
        self.booking.selected_price = Decimal("0.00")
        self.booking.save()
        response = self.client.get(self.url)
        self.assertContains(response, "₹0.00")
        self.assertContains(response, '<div class="total"><span>Total</span><span>₹0.00</span></div>', html=True)

    def test_deleted_service_does_not_break_existing_bill(self):
        self.client.force_login(self.staff)
        self.service.delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₹1500.00")

    def test_customer_details_are_escaped(self):
        self.client.force_login(self.staff)
        self.booking.name = '<script>alert("unsafe")</script>'
        self.booking.save()
        response = self.client.get(self.url)
        self.assertNotContains(response, self.booking.name)
        self.assertContains(response, "&lt;script&gt;")

    def test_bill_requires_staff_access(self):
        self.assertRedirects(
            self.client.get(self.url), f'{reverse("sukoon_admin:login")}?next={self.url}',
        )
        self.client.force_login(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("Bill Customer", response.content.decode())

    def test_missing_booking_returns_not_found(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("booking_bill", args=[999999])).status_code, 404)
