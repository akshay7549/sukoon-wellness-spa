from datetime import datetime, time, timedelta
from decimal import Decimal
from io import StringIO
import gzip, json, sqlite3, tempfile, zipfile
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from .models import Booking, Room, Staff, StaffLeave, Service, ServiceOption, Enquiry, Notification, CustomerProfile
from .forms import BookingForm
from .services.availability import get_available_slots
from .email_views import verification_token

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProjectRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=get_user_model().objects.create_superuser("owner","owner@example.com","Strong!Password129")
        cls.customer=get_user_model().objects.create_user("guest","guest@example.com","Strong!Password129")
        cls.other=get_user_model().objects.create_user("other","other@example.com","Strong!Password129")
        cls.staff_user=get_user_model().objects.create_user("barestaff",is_staff=True)
        cls.service=Service.objects.create(name="Swedish Massage",short_description="Relaxation treatment")
        cls.option=ServiceOption.objects.create(service=cls.service,duration=60,price="1500")
        cls.staff=Staff.objects.create(name="Therapist")
        cls.room=Room.objects.create(name="Treatment room")
        cls.day=timezone.localdate()+timedelta(days=2)
    def data(self,hour=14):
        return {"name":"Guest","phone":"9031640551","email":"guest@example.com","service":self.service.pk,"duration":"60","appointment_date":str(self.day),"appointment_time":f"{hour}:00","message":""}
    def booked(self,**kwargs):
        data={"customer":self.customer,"name":"Guest","phone":"9031640551","email":"guest@example.com","service":self.service,"selected_duration":60,"selected_price":Decimal("1500"),"appointment_date":self.day,"appointment_time":time(14),"end_time":time(15),"staff":self.staff,"room":self.room,"service_name_snapshot":"Swedish Massage"}
        data.update(kwargs)
        return Booking.objects.create(**data)
    def admin_data(self,**kwargs):
        data={**self.data(),"status":"confirmed","customer":self.customer.pk,"staff":self.staff.pk,"room":self.room.pk,"discount_amount":"0","amount_paid":"0","payment_mode":"","payment_reference":""}
        data.update(kwargs)
        return data
    def test_admin_add_records_duration_price_end_and_owner(self):
        self.client.force_login(self.owner)
        response=self.client.post(reverse("sukoon_admin:spa_booking_add"),self.admin_data())
        self.assertEqual(response.status_code,302)
        b=Booking.objects.get()
        self.assertEqual((b.selected_duration,b.selected_price,b.end_time),(60,Decimal("1500"),time(15)))
        self.assertEqual(b.customer,self.customer)
    def test_admin_rejects_overlapping_and_leave_bookings(self):
        self.booked()
        self.client.force_login(self.owner)
        response=self.client.post(reverse("sukoon_admin:spa_booking_add"),self.admin_data())
        self.assertEqual(response.status_code,200)
        self.assertEqual(Booking.objects.count(),1)
        Booking.objects.all().delete()
        StaffLeave.objects.create(staff=self.staff,leave_date=self.day)
        response=self.client.post(reverse("sukoon_admin:spa_booking_add"),self.admin_data())
        self.assertEqual(response.status_code,200)
        self.assertFalse(Booking.objects.exists())
    def test_admin_reschedule_preserves_charge_and_recalculates_end(self):
        b=self.booked()
        self.option.price=Decimal("2500");self.option.save()
        self.client.force_login(self.owner)
        r=self.client.post(reverse("sukoon_admin:spa_booking_change",args=[b.pk]),self.admin_data(appointment_time="16:00"))
        self.assertEqual(r.status_code,302)
        b.refresh_from_db()
        self.assertEqual((b.selected_price,b.end_time),(Decimal("1500"),time(17)))
    def test_admin_rejects_after_hours_and_past_time(self):
        self.client.force_login(self.owner)
        for updates in [{"appointment_time":"21:30"},{"appointment_date":"2020-01-01"}]:
            r=self.client.post(reverse("sukoon_admin:spa_booking_add"),self.admin_data(**updates))
            self.assertEqual(r.status_code,200)
        self.assertFalse(Booking.objects.exists())
    def test_public_booking_rejects_same_day_past_time(self):
        now=timezone.make_aware(datetime.combine(self.day,time(19)))
        with patch("django.utils.timezone.now",return_value=now):
            self.assertFalse(BookingForm(self.data(10)).is_valid())
            slots=get_available_slots(self.day,60)
            self.assertTrue(all(s["start_time"]>time(19) for s in slots))
    def test_public_creation_rejects_overlap_and_accepts_adjacent_slot(self):
        self.booked()
        r=self.client.post(reverse("booking"),self.data())
        self.assertEqual(r.status_code,200)
        self.assertEqual(Booking.objects.count(),1)
        r=self.client.post(reverse("booking"),self.data(15))
        self.assertEqual(r.status_code,302)
        self.assertEqual(Booking.objects.count(),2)
    def test_availability_query_count_stays_constant_with_many_resources(self):
        Staff.objects.bulk_create([Staff(name=f"T{i}") for i in range(7)])
        Room.objects.bulk_create([Room(name=f"R{i}") for i in range(6)])
        with self.assertNumQueries(4):
            slots=get_available_slots(self.day,60)
        self.assertEqual(len(slots),45)
    def test_only_own_booking_can_be_excluded_from_slots(self):
        b=self.booked()
        self.client.force_login(self.other)
        r=self.client.get(reverse("available_slots"),{"service":self.service.pk,"duration":60,"date":str(self.day),"booking_id":b.pk})
        self.assertEqual(r.status_code,404)
        self.client.force_login(self.customer)
        r=self.client.get(reverse("available_slots"),{"service":self.service.pk,"duration":60,"date":str(self.day),"booking_id":b.pk})
        self.assertEqual(r.status_code,200)
        self.assertIn("14:00",[s["start"] for s in r.json()["slots"]])
    def test_contact_and_franchise_enquiries_are_saved(self):
        r=self.client.post(reverse("contact"),{"name":"Enquiry Guest","phone":"9031640551","subject":"Appointment","message":"Please call me"})
        self.assertEqual(r.status_code,302)
        r=self.client.post(reverse("franchise"),{"name":"Partner","phone":"9031640551","email":"partner@example.com","city":"Patna","investment_range":"25-35","franchise_model":"FOFO","message":"Interested"})
        self.assertEqual(r.status_code,302)
        self.assertEqual(set(Enquiry.objects.values_list("kind",flat=True)),{"contact","franchise"})
    def test_invalid_enquiries_do_not_claim_success(self):
        for route in ["contact","franchise"]:
            r=self.client.post(reverse(route),{"name":"Guest","phone":"invalid","subject":"Hello","message":"Message"})
            self.assertEqual(r.status_code,200)
            self.assertTrue(r.context["enquiry_form"].errors)
        self.assertFalse(Enquiry.objects.exists())
    def test_services_are_database_driven_and_hide_inactive_treatments(self):
        self.service.name="New Treatment Name";self.service.save()
        Service.objects.create(name="Hidden Treatment",is_active=False)
        no_options=Service.objects.create(name="Reception-only Treatment")
        r=self.client.get(reverse("services"))
        self.assertContains(r,"New Treatment Name")
        self.assertNotContains(r,"Hidden Treatment")
        self.assertContains(r,"Ask Reception About Sessions")
        self.assertNotIn(no_options,BookingForm().fields["service"].queryset)
    def test_cancel_requires_owner_post_and_releases_resources(self):
        b=self.booked()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("cancel_booking",args=[b.pk])).status_code,404)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("cancel_booking",args=[b.pk])).status_code,405)
        self.client.post(reverse("cancel_booking",args=[b.pk]))
        b.refresh_from_db();self.assertEqual(b.status,"cancelled")
        self.assertIn(time(14),[s["start_time"] for s in get_available_slots(self.day,60)])
    def test_two_hour_cutoff_blocks_cancel_and_reschedule(self):
        b=self.booked()
        now=timezone.make_aware(datetime.combine(self.day,time(12)))
        self.client.force_login(self.customer)
        with patch("django.utils.timezone.now",return_value=now):
            self.client.post(reverse("cancel_booking",args=[b.pk]))
            r=self.client.get(reverse("reschedule_booking",args=[b.pk]))
            self.assertEqual(r.status_code,302)
        b.refresh_from_db();self.assertEqual(b.status,"confirmed")
    def test_reschedule_keeps_booking_id_price_and_customer(self):
        b=self.booked()
        self.option.price=Decimal("2500");self.option.save()
        self.client.force_login(self.customer)
        r=self.client.post(reverse("reschedule_booking",args=[b.pk]),self.data(16))
        self.assertEqual(r.status_code,302)
        b.refresh_from_db()
        self.assertEqual((b.pk,b.appointment_time,b.end_time,b.selected_price,b.customer_id),(b.pk,time(16),time(17),Decimal("1500"),self.customer.pk))
    def test_staff_flag_alone_cannot_read_dashboard_or_bill(self):
        b=self.booked()
        self.client.force_login(self.staff_user)
        self.assertEqual(self.client.get(reverse("sukoon_admin:index")).status_code,403)
        self.assertEqual(self.client.get(reverse("booking_bill",args=[b.pk])).status_code,403)
        self.assertEqual(self.client.get(reverse("booking_success",args=[b.pk])).status_code,404)
    def test_receptionist_can_manage_appointments_without_business_value(self):
        call_command("setup_roles",stdout=StringIO())
        self.staff_user.groups.add(Group.objects.get(name="Receptionist"))
        self.client.force_login(self.staff_user)
        self.booked()
        r=self.client.get(reverse("sukoon_admin:index"))
        self.assertEqual(r.status_code,200)
        self.assertNotContains(r,"Completed Service Value")
        self.assertEqual(self.client.get(reverse("sukoon_admin:auth_user_changelist")).status_code,403)
    def test_bill_records_discount_partial_payment_and_snapshot_name(self):
        b=self.booked(discount_amount=Decimal("100"),amount_paid=Decimal("500"),payment_mode="upi",payment_reference="TEST-PAYMENT")
        self.service.name="Renamed treatment";self.service.save()
        self.client.force_login(self.owner)
        r=self.client.get(reverse("booking_bill",args=[b.pk]))
        for value in ["₹1400.00","₹900.00","Part paid","UPI","TEST-PAYMENT","Swedish Massage"]:self.assertContains(r,value)
        self.assertNotContains(r,"Renamed treatment")
    def test_invalid_discount_overpayment_or_missing_payment_mode_rejected(self):
        for kwargs in [{"discount_amount":Decimal("1501")},{"amount_paid":Decimal("1501"),"payment_mode":"cash"},{"amount_paid":Decimal("100")}]:
            b=self.booked(**kwargs)
            with self.assertRaises(ValidationError):b.full_clean()
            b.delete()
    def test_signup_rejects_duplicate_email_case_insensitively(self):
        r=self.client.post(reverse("register"),{"first_name":"Duplicate","username":"newuser","email":"GUEST@example.com","password1":"Strong!Password129","password2":"Strong!Password129"})
        self.assertTrue(r.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(username="newuser").exists())
    def test_login_rate_limit_blocks_sixth_attempt(self):
        for i in range(5):
            self.assertEqual(self.client.post(reverse("login"),{"username":"guest","password":"wrong"}).status_code,200)
        r=self.client.post(reverse("login"),{"username":"guest","password":"wrong"})
        self.assertEqual(r.status_code,429)
        self.assertIn("Retry-After",r.headers)
    def test_verification_rejects_tampered_link_and_changed_email(self):
        token=verification_token(self.customer)
        self.assertEqual(self.client.get(reverse("verify_email",args=[token+"bad"])).status_code,400)
        self.customer.email="changed@example.com";self.customer.save()
        self.assertEqual(self.client.get(reverse("verify_email",args=[token])).status_code,400)
    def test_valid_verification_marks_only_token_owner(self):
        token=verification_token(self.customer)
        r=self.client.get(reverse("verify_email",args=[token]))
        self.assertEqual(r.status_code,200)
        self.assertTrue(CustomerProfile.objects.get(user=self.customer).email_verified)
        self.assertFalse(CustomerProfile.objects.filter(user=self.other).exists())
    def test_disabled_providers_send_nothing_and_reset_is_honest(self):
        self.booked()
        from .notifications import queue_booking_notifications
        queue_booking_notifications(Booking.objects.get(),"confirmed")
        self.assertFalse(Notification.objects.exists())
        r=self.client.post(reverse("password_reset"),{"email":"guest@example.com"})
        self.assertContains(r,"Email recovery is not connected yet")
        out=StringIO();call_command("process_notifications",stdout=out)
        self.assertIn("disabled",out.getvalue())
    @override_settings(EMAIL_ENABLED=True,MAILERS={"default":{"BACKEND":"django.core.mail.backends.locmem.EmailBackend"}})
    def test_reset_mail_uses_public_https_domain_and_expiring_token(self):
        r=self.client.post(reverse("password_reset"),{"email":"guest@example.com"})
        self.assertEqual(r.status_code,302)
        call_command("process_notifications",stdout=StringIO())
        self.assertEqual(len(mail.outbox),1)
        self.assertIn(settings.PUBLIC_SITE_URL+"/reset/",mail.outbox[0].body)
    @override_settings(EMAIL_ENABLED=True,MAILERS={"default":{"BACKEND":"django.core.mail.backends.locmem.EmailBackend"}})
    def test_queued_booking_and_reminder_are_sent_only_when_due(self):
        b=self.booked()
        from .notifications import queue_booking_notifications
        queue_booking_notifications(b,"confirmed")
        self.assertEqual(Notification.objects.filter(status="pending").count(),2)
        call_command("process_notifications",stdout=StringIO())
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(Notification.objects.filter(status="pending").count(),1)
    def test_sitemap_robots_and_policies_are_public(self):
        for route in ["privacy","cancellation_policy","sitemap","robots"]:
            self.assertEqual(self.client.get(reverse(route)).status_code,200)
        self.assertContains(self.client.get(reverse("sitemap")),settings.PUBLIC_SITE_URL+"/book/")
        self.assertContains(self.client.get(reverse("robots")),"Disallow: /my-bookings/")
    def test_backup_integrity_and_sqlite_restore_drill(self):
        self.booked()
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=Path(tmp)/"media"):
                settings.MEDIA_ROOT.mkdir()
                (settings.MEDIA_ROOT/"test.txt").write_text("backup-test")
                call_command("backup_project",directory=tmp,stdout=StringIO())
                path=next(Path(tmp).glob("sukoon-*.zip"))
                call_command("verify_backup",str(path),stdout=StringIO())
                with zipfile.ZipFile(path) as z:
                    sql=gzip.decompress(z.read("database.sql.gz")).decode()
                    self.assertEqual(z.read("media/test.txt"),b"backup-test")
                if connection.vendor != "sqlite":
                    self.assertIn("CREATE TABLE",sql)
                    return
                restored=sqlite3.connect(":memory:")
                restored.executescript(sql)
                self.assertEqual(restored.execute("select count(*) from spa_booking").fetchone()[0],1)
                restored.close()

    @override_settings(EMAIL_ENABLED=True,MAILERS={"default":{"BACKEND":"django.core.mail.backends.locmem.EmailBackend"}})
    def test_signup_verification_queue_supports_long_signed_tokens(self):
        r=self.client.post(reverse("register"),{"first_name":"Verified Guest","username":"verifiedguest","email":"verified@example.com","password1":"Strong!Password129","password2":"Strong!Password129"})
        self.assertEqual(r.status_code,302)
        job=Notification.objects.get()
        self.assertLessEqual(len(job.dedupe_key),200)
        call_command("process_notifications",stdout=StringIO())
        self.assertIn(settings.PUBLIC_SITE_URL+"/verify-email/",mail.outbox[0].body)

    def test_admin_session_options_api_only_exposes_active_durations(self):
        ServiceOption.objects.create(service=self.service,duration=90,price="2200",is_active=False)
        r=self.client.get(reverse("service_options"),{"service":self.service.pk})
        self.assertEqual(r.json()["options"],[{"duration":60,"price":"1500.00"}])
        self.assertEqual(self.client.get(reverse("service_options"),{"service":"bad"}).status_code,400)

    def test_unrecorded_payment_is_not_invented_as_unpaid(self):
        b=self.booked()
        self.assertEqual(b.payment_status,"Not recorded")
        self.assertIsNone(b.balance_due)
        self.client.force_login(self.owner)
        response=self.client.get(reverse("booking_bill",args=[b.pk]))
        self.assertContains(response,"Payment: Not recorded")
        self.assertNotContains(response,"Amount paid:")
