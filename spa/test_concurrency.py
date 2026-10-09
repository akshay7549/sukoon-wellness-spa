from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone
from .forms import BookingForm
from .models import Booking, Room, Service, ServiceOption, Staff
from .services.bookings import save_booking

@skipUnless(connection.vendor == "mysql", "Requires real MySQL row locks.")
class BookingConcurrencyTests(TransactionTestCase):
    def test_simultaneous_different_treatments_cannot_share_resources(self):
        Staff.objects.create(name="Only therapist")
        Room.objects.create(name="Only room")
        services = [Service.objects.create(name=f"Treatment {i}") for i in range(2)]
        for service in services:
            ServiceOption.objects.create(service=service, duration=60, price="1500")
        barrier = Barrier(2)
        def book(service_id):
            try:
                form = BookingForm({"name":"Concurrency Test","phone":"9031640551","service":service_id,
                    "duration":"60","appointment_date":str(timezone.localdate()+timedelta(days=3)),"appointment_time":"14:00"})
                if not form.is_valid():
                    raise AssertionError(str(form.errors))
                barrier.wait(timeout=10)
                try:
                    save_booking(form)
                    return True
                except ValidationError:
                    return False
            finally:
                connections["default"].close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(book,[s.pk for s in services]))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(Booking.objects.count(),1)
