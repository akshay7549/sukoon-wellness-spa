from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Booking, Room, Service, Staff


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = get_user_model().objects.create_user(username="manager", is_staff=True)
        cls.staff_user.user_permissions.set(Permission.objects.filter(content_type__app_label="spa"))
        cls.customer = get_user_model().objects.create_user(username="visitor", email="visitor@example.com")
        get_user_model().objects.create_user(username="inactivevisitor", is_active=False)
        cls.service = Service.objects.create(name="Swedish Massage")
        cls.other_service = Service.objects.create(name="Aroma Therapy")
        cls.therapist = Staff.objects.create(name="Therapist One")
        cls.room = Room.objects.create(name="Room One")
        cls.completed = cls.make_booking("Completed Guest", date(2026, 10, 9), "completed", "1500.00")
        cls.cancelled = cls.make_booking("Cancelled Guest", date(2026, 10, 9), "cancelled", "800.00")
        cls.confirmed = cls.make_booking("Future Guest", date(2026, 10, 10), "confirmed", "2500.00", cls.other_service)
        cls.make_booking("Earlier Guest", date(2026, 10, 2), "confirmed", "1000.00")
        cls.make_booking("Previous Month", date(2026, 9, 18), "completed", "3000.00")
        cls.make_booking("Next Month", date(2026, 11, 1), "confirmed", "1800.00")

    @classmethod
    def make_booking(cls, name, appointment_date, status, price, service=None):
        return Booking.objects.create(
            name=name, phone="9031640551", customer=cls.customer,
            service=service or cls.service, staff=cls.therapist, room=cls.room,
            appointment_date=appointment_date, appointment_time=time(14),
            selected_duration=60, selected_price=price, status=status,
        )

    def setUp(self):
        self.client.force_login(self.staff_user)
        self.url = reverse("sukoon_admin:index")
        self.date_patch = patch("spa.admin_dashboard.timezone.localdate", return_value=date(2026, 10, 9))
        self.date_patch.start()
        self.addCleanup(self.date_patch.stop)

    def test_month_overview_uses_appointment_dates_and_completed_prices(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/crm_dashboard.html")
        self.assertEqual(response.context["total_bookings"], 4)
        self.assertEqual(response.context["today_bookings"], 2)
        self.assertEqual(response.context["confirmed_bookings"], 2)
        self.assertEqual(response.context["completed_value"], Decimal("1500.00"))
        self.assertEqual(response.context["completion_rate"], 25)
        self.assertEqual(response.context["customer_accounts"], 1)
        self.assertContains(response, "Generate Bill")
        self.assertContains(response, "Reception QR")

    def test_period_filters_change_counts(self):
        for period, total in (("today", 2), ("week", 3), ("all", 6)):
            with self.subTest(period=period):
                response = self.client.get(self.url, {"period": period})
                self.assertEqual(response.context["total_bookings"], total)

    def test_unknown_period_defaults_to_this_month(self):
        response = self.client.get(self.url, {"period": "invalid"})
        self.assertEqual(response.context["period"], "month")
        self.assertEqual(response.context["total_bookings"], 4)

    def test_search_and_status_filters_only_affect_booking_list(self):
        response = self.client.get(self.url, {"q": "Future Guest", "status": "confirmed"})
        self.assertEqual(list(response.context["booking_page"]), [self.confirmed])
        self.assertEqual(response.context["total_bookings"], 4)
        self.assertEqual(response.context["booking_page"].paginator.count, 1)

    def test_booking_search_can_find_treatment(self):
        response = self.client.get(self.url, {"q": "Aroma"})
        self.assertEqual(list(response.context["booking_page"]), [self.confirmed])

    def test_treatment_performance_and_six_month_trend_are_real(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["performance"][0]["total"], 3)
        self.assertEqual(response.context["performance"][0]["completed"], 1)
        self.assertEqual(response.context["performance"][0]["value"], Decimal("1500.00"))
        trend = response.context["trend"]
        self.assertEqual(len(trend), 6)
        self.assertEqual([row["count"] for row in trend], [0, 0, 0, 0, 1, 4])

    def test_empty_period_does_not_divide_by_zero(self):
        Booking.objects.all().delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["completion_rate"], 0)
        self.assertEqual(response.context["completed_value"], 0)
        self.assertTrue(all(row["height"] == 0 for row in response.context["trend"]))
        self.assertContains(response, "No bookings in this appointment period")

    def test_pagination_is_bounded_and_keeps_filters(self):
        for index in range(16):
            self.make_booking(f"Search Guest {index}", date(2026, 10, 12), "confirmed", "100.00")
        response = self.client.get(self.url, {"q": "Search Guest", "status": "confirmed", "page": 2})
        self.assertEqual(response.context["booking_page"].number, 2)
        self.assertEqual(len(response.context["booking_page"]), 4)
        self.assertIn("q=Search+Guest", response.context["page_query"])
        self.assertIn("status=confirmed", response.context["page_query"])

    def test_missing_completed_price_is_reported(self):
        self.completed.selected_price = None
        self.completed.save()
        response = self.client.get(self.url)
        self.assertEqual(response.context["completed_value"], 0)
        self.assertEqual(response.context["missing_prices"], 1)

    def test_customer_cannot_read_dashboard_data(self):
        self.client.force_login(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("Completed Guest", response.content.decode())
