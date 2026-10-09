from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from spa.forms import BookingForm
from spa.models import Booking, Service, ServiceOption


class RateCardTests(TestCase):
    def sync(self, apply=True):
        call_command("sync_rate_card", apply=apply, stdout=StringIO())

    def test_sync_preserves_historical_bookings_and_is_idempotent(self):
        service = Service.objects.create(name="Swedish-Massage")
        ServiceOption.objects.create(service=service, duration=60, price=100)
        old = Booking.objects.create(name="Historical", phone="9031640551", service=service,
            service_name_snapshot="Swedish-Massage", selected_duration=60,
            selected_price=100, appointment_date=date(2025,1,1), appointment_time=time(12))
        self.sync()
        old.refresh_from_db()
        self.assertEqual(old.selected_price, Decimal("100"))
        self.assertEqual(old.service_name_snapshot, "Swedish-Massage")
        self.assertEqual(old.service_id, service.pk)
        self.assertEqual(ServiceOption.objects.get(service=service, duration=60).price, Decimal("1999"))
        self.assertEqual(Service.objects.count(), 27)
        self.assertEqual(ServiceOption.objects.filter(is_active=True).count(), 50)
        ids = list(Service.objects.values_list("pk",flat=True))
        self.sync()
        self.assertEqual(list(Service.objects.values_list("pk",flat=True)), ids)
        self.assertEqual(ServiceOption.objects.count(), 50)

    def test_duration_free_rates_show_without_fake_appointment_duration(self):
        self.sync()
        face = Service.objects.get(name="FACE SCRUB")
        self.assertEqual(face.menu_price, Decimal("499"))
        self.assertFalse(face.options.exists())
        self.assertNotIn(face, BookingForm().fields["service"].queryset)
        response = self.client.get("/services/")
        self.assertContains(response, "FACE SCRUB")
        self.assertContains(response, "₹499.00")
        self.assertContains(response, "₹10000.00")
        self.assertContains(response, "Thai Dry Therapy × 1")
        self.assertNotContains(response, f"/book/?service={face.pk}")

    def test_preview_does_not_write_and_ambiguous_names_fail_atomically(self):
        self.sync(apply=False)
        self.assertEqual(Service.objects.count(), 0)
        Service.objects.create(name="Aroma Therapy")
        Service.objects.create(name="AROMA-THERAPY")
        with self.assertRaises(CommandError):
            self.sync()
        self.assertEqual(Service.objects.count(), 2)
        self.assertEqual(ServiceOption.objects.count(), 0)
