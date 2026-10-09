import uuid
from datetime import timedelta,time
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Service,ServiceOption,Staff,Room,Booking,Invoice,InvoiceLine,InvoicePayment,PackageComponent,PackageEnrollment,PackageCredit,Notification
from .forms import BookingForm
from .admin_forms import AdminBookingForm
from .services.bookings import save_booking,transition_booking
from .services.invoicing import record_payment
from .services.availability import get_available_slots


class OperationsTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('ops-owner','owner@example.com','TestPassword!123')
        self.customer=get_user_model().objects.create_user('ops-customer',email='customer@example.com',password='TestPassword!123')
        self.service=Service.objects.create(name='AROMA THERAPY')
        ServiceOption.objects.create(service=self.service,duration=60,price=1000)
        self.scrub=Service.objects.create(name='FACE SCRUB',menu_price=499)
        self.staff=Staff.objects.create(name='Therapist A')
        self.second=Staff.objects.create(name='Therapist B')
        self.room=Room.objects.create(name='Couple Room',is_couple_room=True)
        self.day=timezone.localdate()+timedelta(days=2)
        self.client.force_login(self.owner)

    def invoice_data(self,service=None,price='',quantity=1):
        return {'customer_name':'Test Customer','phone':'9031640551','email':'customer@example.com','customer':self.customer.pk,'issue_date':timezone.localdate().isoformat(),'discount_amount':'0','opening_paid':'0','items-TOTAL_FORMS':'1','items-INITIAL_FORMS':'0','items-MIN_NUM_FORMS':'0','items-MAX_NUM_FORMS':'20','items-0-service':(service or self.scrub).pk,'items-0-description':'','items-0-duration':'','items-0-quantity':str(quantity),'items-0-unit_price':price}

    def booking_form(self,service=None,credit=None,start='12:00',customer=None):
        data={'name':'Test Customer','phone':'9031640551','service':(service or self.service).pk,'duration':'60','appointment_date':self.day.isoformat(),'appointment_time':start,'package_credit':credit.pk if credit else ''}
        form=BookingForm(data,customer_user=customer or self.customer)
        self.assertTrue(form.is_valid(),form.errors)
        return form

    def payment(self,invoice,amount,key=None):
        return record_payment(invoice.pk,{'amount':Decimal(amount),'mode':'upi','reference':'TEST-ONLY','received_at':timezone.now(),'request_key':key or uuid.uuid4()},self.owner)

    def test_duration_free_multi_service_invoice_and_totals(self):
        data=self.invoice_data();data.update({'items-TOTAL_FORMS':'2','items-1-service':self.service.pk,'items-1-description':'','items-1-duration':'60','items-1-quantity':'1','items-1-unit_price':'','discount_amount':'99'})
        response=self.client.post(reverse('invoice_new'),data)
        self.assertEqual(response.status_code,302)
        invoice=Invoice.objects.get()
        self.assertEqual(invoice.lines.count(),2)
        self.assertIsNone(invoice.lines.get(service=self.scrub).duration)
        self.assertEqual(invoice.net_amount,Decimal('1400'))
        self.assertContains(self.client.get(reverse('invoice_print',args=[invoice.pk])),'₹1400.00')

    def test_receipts_idempotent_overpayment_rejected_and_invoice_locked(self):
        self.client.post(reverse('invoice_new'),self.invoice_data())
        invoice=Invoice.objects.get();key=uuid.uuid4()
        first=self.payment(invoice,'200',key)
        self.assertEqual(self.payment(invoice,'200',key).pk,first.pk)
        self.assertEqual(InvoicePayment.objects.count(),1)
        with self.assertRaises(ValidationError):self.payment(invoice,'300')
        self.assertEqual(invoice.balance_due,Decimal('299'))
        self.assertContains(self.client.get(reverse('invoice_edit',args=[invoice.pk])),'This invoice has recorded receipts')

    def test_receipt_form_replay_and_unknown_opening_balance(self):
        self.client.post(reverse('invoice_new'),self.invoice_data())
        invoice=Invoice.objects.get();key=uuid.uuid4()
        data={'amount':'100','mode':'cash','reference':'TEST','received_at':timezone.now().strftime('%Y-%m-%dT%H:%M'),'request_key':str(key)}
        self.client.post(reverse('invoice_payment',args=[invoice.pk]),data)
        self.client.post(reverse('invoice_payment',args=[invoice.pk]),data)
        self.assertEqual(InvoicePayment.objects.count(),1)
        other=Invoice.objects.create(customer_name='Unknown',phone='9031640551',opening_paid=None)
        InvoiceLine.objects.create(invoice=other,description='Treatment',unit_price=100)
        with self.assertRaises(ValidationError):self.payment(other,'50')

    def test_package_purchase_reservation_cancellation_and_exhaustion(self):
        package=Service.objects.create(name='SILVER PACKAGE',is_package=True,menu_price=5000)
        PackageComponent.objects.create(package=package,treatment=self.service,sessions=1)
        self.client.post(reverse('invoice_new'),self.invoice_data(service=package))
        invoice=Invoice.objects.get()
        self.payment(invoice,'4999');self.assertEqual(PackageEnrollment.objects.count(),0)
        self.payment(invoice,'1');credit=PackageCredit.objects.get()
        self.assertEqual(credit.available,1)
        booking=save_booking(self.booking_form(credit=credit),self.customer)
        self.assertEqual(booking.selected_price,0)
        self.assertEqual(credit.available,0)
        with self.assertRaises(ValidationError):save_booking(self.booking_form(credit=credit,start='14:00'),self.customer)
        transition_booking(booking.pk,'cancelled');self.assertEqual(credit.available,1)
        used_booking=save_booking(self.booking_form(credit=credit,start='14:00'),self.customer)
        used_booking.appointment_date=timezone.localdate()-timedelta(days=1);used_booking.save()
        transition_booking(used_booking.pk,'completed')
        self.assertEqual(credit.used,1)
        self.assertEqual(credit.reserved,0)
        self.assertEqual(credit.available,0)
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):used_booking.delete()
        other=get_user_model().objects.create_user('stranger',password='TestPassword!123')
        forged=BookingForm({'name':'Other','phone':'9031640551','service':self.service.pk,'duration':'60','appointment_date':self.day.isoformat(),'appointment_time':'14:00','package_credit':credit.pk},customer_user=other)
        self.assertFalse(forged.is_valid())

    def test_couple_booking_reserves_two_distinct_therapists_and_room(self):
        couple=Service.objects.create(name='COUPLE MASSAGE',staff_required=2,requires_couple_room=True)
        ServiceOption.objects.create(service=couple,duration=60,price=3999)
        booking=save_booking(self.booking_form(service=couple),self.customer)
        self.assertIsNotNone(booking.secondary_staff_id)
        self.assertNotEqual(booking.staff_id,booking.secondary_staff_id)
        self.assertEqual(booking.room_id,self.room.pk)
        self.assertFalse(any(s['start_time']==time(12) for s in get_available_slots(self.day,60,service=self.service)))
        self.second.is_active=False;self.second.save()
        self.assertEqual(get_available_slots(self.day,60,service=couple),[])

    def test_package_duration_limit_is_enforced(self):
        invoice=Invoice.objects.create(customer_name='Test',phone='9031640551',customer=self.customer)
        line=InvoiceLine.objects.create(invoice=invoice,description='Package',unit_price=100)
        enrollment=PackageEnrollment.objects.create(invoice_line=line,customer=self.customer,customer_name='Test',phone='9031640551',package_name='Limited')
        credit=PackageCredit.objects.create(enrollment=enrollment,treatment=self.service,label='Limited',total_sessions=1,max_duration=45)
        with self.assertRaises(ValidationError):save_booking(self.booking_form(credit=credit),self.customer)

    def test_removing_package_coverage_requires_an_active_rate(self):
        invoice=Invoice.objects.create(customer_name='Test',phone='9031640551',customer=self.customer)
        line=InvoiceLine.objects.create(invoice=invoice,description='Package',unit_price=100)
        enrollment=PackageEnrollment.objects.create(invoice_line=line,customer=self.customer,customer_name='Test',phone='9031640551',package_name='Package')
        credit=PackageCredit.objects.create(enrollment=enrollment,treatment=self.service,label='Therapy',total_sessions=1)
        booking=save_booking(self.booking_form(credit=credit),self.customer)
        ServiceOption.objects.filter(service=self.service).update(is_active=False)
        data={'name':booking.name,'phone':booking.phone,'customer':self.customer.pk,'service':self.service.pk,'duration':'60','appointment_date':self.day.isoformat(),'appointment_time':'12:00','status':'confirmed','discount_amount':'0','amount_paid':'','payment_mode':''}
        form=AdminBookingForm(data,instance=booking)
        self.assertTrue(form.is_valid(),form.errors)
        with self.assertRaisesMessage(ValidationError,'Choose an active duration'):
            save_booking(form)
        booking.refresh_from_db()
        self.assertEqual(booking.package_credit_id,credit.pk)
        self.assertEqual(booking.selected_price,0)

    @override_settings(EMAIL_ENABLED=True)
    def test_past_status_only_edit_and_bulk_notifications(self):
        b=Booking.objects.create(name='Past Customer',phone='9031640551',email='customer@example.com',service=self.service,selected_duration=60,selected_price=1000,appointment_date=timezone.localdate()-timedelta(days=1),appointment_time=time(12),end_time=time(13),staff=self.staff,room=self.room)
        data={'name':b.name,'phone':b.phone,'email':b.email,'service':self.service.pk,'duration':'60','appointment_date':b.appointment_date.isoformat(),'appointment_time':'12:00','status':'completed','discount_amount':'0','amount_paid':'','payment_mode':''}
        form=AdminBookingForm(data,instance=b);self.assertTrue(form.is_valid(),form.errors)
        saved=save_booking(form);self.assertEqual(saved.status,'completed')
        future=save_booking(self.booking_form(),self.customer);future.email='customer@example.com';future.save()
        Notification.objects.create(booking=future,dedupe_key='old-confirmation',channel='email',recipient=future.email,subject='old',message='old',due_at=timezone.now())
        transition_booking(future.pk,'cancelled')
        self.assertEqual(Notification.objects.get(dedupe_key='old-confirmation').status,'cancelled')
        self.assertTrue(Notification.objects.filter(booking=future,subject='Sukoon booking cancelled',status='pending').exists())

    def test_customer_privacy_and_reception_collection_permissions(self):
        self.client.post(reverse('invoice_new'),self.invoice_data());invoice=Invoice.objects.get()
        stranger=get_user_model().objects.create_user('other-customer',password='TestPassword!123')
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse('invoice_print',args=[invoice.pk])).status_code,404)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('invoice_print',args=[invoice.pk])).status_code,200)
        call_command('setup_roles',verbosity=0)
        from django.contrib.auth.models import Group
        reception=get_user_model().objects.create_user('reception',is_staff=True,password='TestPassword!123');reception.groups.add(Group.objects.get(name='Receptionist'))
        self.client.force_login(reception)
        self.assertEqual(self.client.get(reverse('collections')).status_code,403)
        self.assertEqual(self.client.get(reverse('invoice_list')).status_code,200)
        self.assertEqual(self.client.get(reverse('appointment_calendar')).status_code,200)

    def test_collection_uses_receipt_date_and_excludes_opening_paid(self):
        self.client.post(reverse('invoice_new'),self.invoice_data());invoice=Invoice.objects.get()
        invoice.opening_paid=100;invoice.save()
        self.payment(invoice,'50')
        response=self.client.get(reverse('collections'))
        self.assertEqual(response.context['collected'],Decimal('50'))
        self.assertEqual(response.context['outstanding'],Decimal('349'))
        self.assertEqual(self.client.get(reverse('services')+'?kind=body').context['services'][0].pk,self.scrub.pk)


from django.test import TransactionTestCase
from django.db import close_old_connections
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier


class ReceiptConcurrencyTests(TransactionTestCase):
    def test_concurrent_receipts_cannot_overpay_one_invoice(self):
        from django.db import connection
        if connection.vendor!='mysql':self.skipTest('Requires real MySQL row locks')
        owner=get_user_model().objects.create_superuser('receipt-owner','receipt@example.com','TestPassword!123')
        invoice=Invoice.objects.create(customer_name='Concurrent Test',phone='9031640551')
        InvoiceLine.objects.create(invoice=invoice,description='Test',unit_price=499)
        barrier=Barrier(2)
        def pay():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    record_payment(invoice.pk,{'amount':Decimal('499'),'mode':'cash','reference':'TEST','received_at':timezone.now(),'request_key':uuid.uuid4()},owner)
                    return 'saved'
                except ValidationError:return 'rejected'
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(lambda _:pay(),range(2)))
        self.assertEqual(sorted(outcomes),['rejected','saved'])
        self.assertEqual(InvoicePayment.objects.count(),1)
