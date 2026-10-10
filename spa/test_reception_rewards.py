from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import (Booking, Room, Staff, Service, ServiceOption, CustomerRecord, ReceptionEvent, WaitlistEntry,
                     LoyaltyPolicy, LoyaltyWallet, LoyaltyAward, LoyaltySpend, Referral, Invoice, InvoiceLine, InvoicePayment, Enquiry)
from .services.availability import day_resources, free_resources
from .services.reception import move_visit, promote_waitlist
from .services.loyalty import activate_wallet, purchase_points, redeem_points, record_referral, review_referral
from .forms import BookingForm
from .crm_forms import LeadForm
from .services.crm import save_lead


class ReceptionRewardsTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('owner-workflow', password='Test-safe-pass987')
        self.customer = get_user_model().objects.create_user('reward-customer', password='Test-safe-pass987')
        self.other = get_user_model().objects.create_user('reward-other', password='Test-safe-pass987')
        self.contact = CustomerRecord.objects.create(name='Customer A', phone='9876543210', account=self.customer)
        self.other_contact = CustomerRecord.objects.create(name='Customer B', phone='9876543211', account=self.other)
        self.staff = Staff.objects.create(name='Therapist A')
        self.room = Room.objects.create(name='Room A', cleanup_minutes=15)
        self.service = Service.objects.create(name='Test Massage')
        ServiceOption.objects.create(service=self.service, duration=60, price=1000)
        self.now = timezone.make_aware(datetime.combine(timezone.localdate(), time(15)))
        self.client.force_login(self.owner)

    def booking(self, **kwargs):
        values = dict(name=self.contact.name, phone=self.contact.phone, customer=self.customer, service=self.service,
                      service_name_snapshot=self.service.name, selected_duration=60, selected_price=1000,
                      appointment_date=self.now.date(), appointment_time=time(13), end_time=time(14), staff=self.staff, room=self.room)
        values.update(kwargs)
        return Booking.objects.create(**values)

    def policy(self, **kwargs):
        values = dict(enabled=True, rupees_per_point=100, expiry_days=30, referrer_points=20, referred_points=10, reward_terms='Reception reward: 10 points for a welcome gift.', starts_at=self.now-timedelta(days=2))
        values.update(kwargs)
        return LoyaltyPolicy.objects.create(**values)

    def paid_invoice(self, contact=None):
        contact = contact or self.contact
        booking = self.booking(customer=contact.account, phone=contact.phone, name=contact.name, status='completed')
        invoice = Invoice.objects.create(booking=booking, customer=contact.account, customer_name=contact.name, phone=contact.phone)
        InvoiceLine.objects.create(invoice=invoice, description='Massage', quantity=1, unit_price=1000)
        payment = InvoicePayment.objects.create(invoice=invoice, amount=1000, mode='cash', request_key=str(uuid.uuid4()), received_at=self.now)
        return invoice, payment

    def move(self, booking, stage, note=''):
        booking.refresh_from_db()
        move_visit(booking.pk, stage, booking.updated_at.isoformat(), note, self.owner)
        booking.refresh_from_db()

    def test_day_board_progression_audit_and_cleaning(self):
        visit = self.booking()
        with patch('django.utils.timezone.now', return_value=self.now):
            self.move(visit, 'checked_in'); self.move(visit, 'in_service'); self.move(visit, 'completed')
        self.assertEqual(visit.status, 'completed')
        self.assertEqual(visit.reception_events.count(), 3)
        self.assertIsNotNone(visit.checked_in_at)
        self.room.refresh_from_db()
        self.assertEqual(self.room.cleaning_until, self.now+timedelta(minutes=15))
        self.assertContains(self.client.get(reverse('reception_day_board')), 'Room Turnover')

    def test_invalid_backward_stale_and_future_stage_rejected(self):
        visit = self.booking(appointment_time=time(16), end_time=time(17))
        with patch('django.utils.timezone.now', return_value=self.now):
            with self.assertRaises(ValidationError): self.move(visit, 'no_show', 'Not arrived')
            self.move(visit, 'checked_in')
            with self.assertRaises(ValidationError): self.move(visit, 'in_service')
            with self.assertRaises(ValidationError): self.move(visit, 'completed')
            with self.assertRaises(ValidationError): move_visit(visit.pk, 'cancelled', 'stale', '', self.owner)
        self.assertEqual(visit.reception_events.count(), 1)

    def test_no_show_releases_capacity_but_preserves_finance(self):
        visit = self.booking(amount_paid=500)
        with patch('django.utils.timezone.now', return_value=self.now):
            with self.assertRaises(ValidationError): self.move(visit, 'no_show')
            self.move(visit, 'no_show', 'Customer did not arrive; called once.')
        self.assertEqual(visit.day_stage, 'no_show')
        self.assertEqual(visit.status, 'cancelled')
        self.assertEqual(visit.amount_paid, 500)
        staff, rooms = free_resources(day_resources(self.now.date()), time(13), time(14))
        self.assertIn(self.room, rooms)

    def test_room_cleaning_blocks_both_sides_and_not_therapist(self):
        self.booking(appointment_time=time(12), end_time=time(13))
        staff, rooms = free_resources(day_resources(self.now.date()), time(13), time(14))
        self.assertIn(self.staff, staff); self.assertNotIn(self.room, rooms)
        staff, rooms = free_resources(day_resources(self.now.date()), time(10, 55), time(11, 55))
        self.assertIn(self.staff, staff); self.assertNotIn(self.room, rooms)
        _, rooms = free_resources(day_resources(self.now.date()), time(13, 15), time(14, 15))
        self.assertIn(self.room, rooms)

    def test_running_late_blocks_capacity_and_next_service(self):
        early = self.booking(reception_stage='in_service')
        later = self.booking(appointment_time=time(15), end_time=time(16), reception_stage='checked_in')
        with patch('django.utils.timezone.now', return_value=self.now):
            staff, rooms = free_resources(day_resources(self.now.date(), later.pk), time(15), time(16))
            self.assertNotIn(self.staff, staff); self.assertNotIn(self.room, rooms)
            with self.assertRaises(ValidationError): self.move(later, 'in_service')

    def test_previous_day_unclosed_service_blocks_today(self):
        self.booking(appointment_date=self.now.date()-timedelta(days=1), reception_stage='in_service')
        with patch('django.utils.timezone.now', return_value=self.now):
            staff, rooms = free_resources(day_resources(self.now.date()), time(15), time(16))
        self.assertNotIn(self.staff, staff); self.assertNotIn(self.room, rooms)

    def test_completed_visit_without_buffer_does_not_reserve_room(self):
        self.room.cleanup_minutes = 0; self.room.save()
        self.booking(status='completed')
        _, rooms = free_resources(day_resources(self.now.date()), time(13, 30), time(14, 30))
        self.assertIn(self.room, rooms)

    def test_customer_cannot_reschedule_after_checkin(self):
        from .customer_views import can_change
        visit = self.booking(appointment_time=time(20), end_time=time(21), reception_stage='checked_in')
        with patch('django.utils.timezone.now', return_value=self.now): self.assertFalse(can_change(visit))

    def test_waitlist_promotes_once_and_reserves_resources(self):
        day = timezone.localdate()+timedelta(days=2)
        entry = WaitlistEntry.objects.create(contact=self.contact, service=self.service, duration=60, preferred_date=day, earliest_time=time(10), latest_time=time(17))
        data = {'name': self.contact.name, 'phone': self.contact.phone, 'service': self.service.pk, 'duration': 60, 'appointment_date': day.isoformat(), 'appointment_time': '11:00'}
        form = BookingForm(data, customer_user=self.customer)
        self.assertTrue(form.is_valid(), form.errors)
        booking = promote_waitlist(entry.pk, form, entry.updated_at.isoformat())
        self.assertEqual(booking.customer, self.customer)
        self.assertEqual(booking.room, self.room)
        with self.assertRaises(ValidationError): promote_waitlist(entry.pk, form, entry.updated_at.isoformat())
        self.assertEqual(Booking.objects.count(), 1)

    def test_waitlist_booking_view_and_validation(self):
        day = timezone.localdate()+timedelta(days=2)
        entry = WaitlistEntry.objects.create(contact=self.contact, service=self.service, duration=60, preferred_date=day, earliest_time=time(10), latest_time=time(17))
        self.assertContains(self.client.get(reverse('reception_waitlist_book', args=[entry.pk])), 'Available start times')
        response = self.client.post(reverse('reception_waitlist_book', args=[entry.pk]), {'action': 'book', 'version': entry.updated_at.isoformat(), 'name': self.contact.name, 'appointment_time': '11:00'})
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db(); self.assertEqual(entry.status, 'booked')

    def test_franchise_exact_stages_and_required_followup(self):
        self.assertContains(self.client.get(reverse('crm_pipeline')+'?kind=franchise'), 'Agreement')
        lead = None
        for stage in ('new', 'qualification', 'meeting', 'proposal', 'agreement', 'closed'):
            data = dict(name='Franchise partner', phone='9876543212', kind='franchise', source='phone', message='Interested in a new location', city='Patna', investment_range='20–30 lakh', franchise_model='Premium', status=stage, assigned_to=self.owner.pk,
                        next_action='Discuss franchise', next_follow_up=(timezone.localtime()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'))
            if lead: data['version'] = lead.updated_at.isoformat()
            form = LeadForm(data, instance=lead or Enquiry(), initial={'kind': 'franchise'})
            self.assertTrue(form.is_valid(), form.errors)
            lead = save_lead(form, self.owner)
        self.assertIsNone(lead.next_task)
        self.assertEqual(lead.tasks.filter(status='pending').count(), 0)
        self.assertEqual(lead.activities.count(), 6)
        self.assertEqual(lead.franchise_model, 'Premium')

    def test_customer_pipeline_cannot_use_franchise_stage(self):
        form = LeadForm(dict(name='Customer', phone=self.contact.phone, kind='contact', message='Hello', source='phone', status='proposal', assigned_to=self.owner.pk))
        self.assertFalse(form.is_valid()); self.assertIn('status', form.errors)

    def test_purchase_points_idempotent_with_expiry_and_ownership(self):
        self.policy()
        with patch('django.utils.timezone.now', return_value=self.now):
            invoice, payment = self.paid_invoice()
            item = purchase_points(self.contact.pk, payment.pk, self.owner)
            self.assertEqual(item.points, 10)
            self.assertEqual(item.expires_at, self.now+timedelta(days=30))
            self.assertEqual(purchase_points(self.contact.pk, payment.pk, self.owner).pk, item.pk)
            with self.assertRaises(ValidationError): purchase_points(self.other_contact.pk, payment.pk, self.owner)
        self.assertEqual(LoyaltyAward.objects.count(), 1)

    def test_rewards_disabled_and_guest_identity_protection(self):
        LoyaltyPolicy.objects.create(enabled=False)
        with self.assertRaises(ValidationError): activate_wallet(self.contact.pk)
        LoyaltyPolicy.objects.update(enabled=True)
        self.contact.account = None; self.contact.save()
        with self.assertRaises(ValidationError): activate_wallet(self.contact.pk)

    def test_expired_points_not_spendable_and_earliest_expiry_first(self):
        self.policy()
        wallet = activate_wallet(self.contact.pk)
        dead = LoyaltyAward.objects.create(wallet=wallet, points=50, expires_at=self.now, reason='Old', source_key='old')
        never = LoyaltyAward.objects.create(wallet=wallet, points=10, reason='No expiry', source_key='never')
        soon = LoyaltyAward.objects.create(wallet=wallet, points=10, expires_at=self.now+timedelta(days=1), reason='Soon', source_key='soon')
        key = uuid.uuid4()
        with patch('django.utils.timezone.now', return_value=self.now):
            self.assertEqual(wallet.balance, 20)
            spend = redeem_points(self.contact.pk, 12, 'Welcome gift', key, self.owner)
            self.assertEqual(spend.allocation, {str(soon.pk): 10, str(never.pk): 2})
            self.assertEqual(redeem_points(self.contact.pk, 12, 'Welcome gift', key, self.owner).pk, spend.pk)
            with self.assertRaises(ValidationError): redeem_points(self.contact.pk, 9, 'Another gift', uuid.uuid4(), self.owner)
            self.assertEqual(wallet.balance, 8)
        self.assertEqual(LoyaltySpend.objects.count(), 1)
        dead.refresh_from_db(); self.assertEqual(dead.spent, 0)

    def test_policy_changes_keep_award_expiry(self):
        policy = self.policy()
        with patch('django.utils.timezone.now', return_value=self.now):
            _, payment = self.paid_invoice(); item = purchase_points(self.contact.pk, payment.pk, self.owner)
        policy.expiry_days = None; policy.save()
        item.refresh_from_db(); self.assertEqual(item.expires_at, self.now+timedelta(days=30))

    def test_referral_qualifies_once_after_paid_completed_first_visit(self):
        self.policy()
        wallet = activate_wallet(self.contact.pk)
        with patch('django.utils.timezone.now', return_value=self.now-timedelta(minutes=1)):
            referral = record_referral(self.other_contact.pk, wallet.code)
        with patch('django.utils.timezone.now', return_value=self.now):
            invoice, _ = self.paid_invoice(self.other_contact)
            review_referral(referral.pk, invoice.pk, 'reward', 'Verified first paid visit', self.owner)
            with self.assertRaises(ValidationError): review_referral(referral.pk, invoice.pk, 'reward', 'Retry', self.owner)
        self.assertEqual(wallet.balance, 20)
        self.assertEqual(LoyaltyWallet.objects.get(contact=self.other_contact).balance, 10)
        self.assertEqual(LoyaltyAward.objects.count(), 2)

    def test_self_duplicate_existing_customer_referrals_rejected(self):
        self.policy(); wallet = activate_wallet(self.contact.pk)
        with self.assertRaises(ValidationError): record_referral(self.contact.pk, wallet.code)
        record_referral(self.other_contact.pk, wallet.code)
        with self.assertRaises(ValidationError): record_referral(self.other_contact.pk, wallet.code)
        Referral.objects.all().delete()
        self.paid_invoice(self.other_contact)
        with self.assertRaises(ValidationError): record_referral(self.other_contact.pk, wallet.code)

    def test_unpaid_or_future_referral_invoice_cannot_qualify(self):
        self.policy(); wallet = activate_wallet(self.contact.pk)
        referral = record_referral(self.other_contact.pk, wallet.code)
        invoice, payment = self.paid_invoice(self.other_contact)
        payment.amount = 500; payment.save()
        with self.assertRaises(ValidationError): review_referral(referral.pk, invoice.pk, 'reward', 'Checked', self.owner)
        self.assertEqual(LoyaltyAward.objects.count(), 0)

    def test_backdated_first_payment_cannot_qualify_referral(self):
        self.policy(); wallet = activate_wallet(self.contact.pk)
        with patch('django.utils.timezone.now', return_value=self.now):
            referral = record_referral(self.other_contact.pk, wallet.code)
        with patch('django.utils.timezone.now', return_value=self.now+timedelta(minutes=1)):
            invoice, payment = self.paid_invoice(self.other_contact)
            payment.received_at = self.now-timedelta(days=1); payment.save()
            with self.assertRaises(ValidationError): review_referral(referral.pk, invoice.pk, 'reward', 'Checked first receipt', self.owner)
        self.assertEqual(LoyaltyAward.objects.count(), 0)

    def test_staff_permissions_csrf_and_customer_rewards_privacy(self):
        self.policy(); activate_wallet(self.contact.pk); other_wallet = activate_wallet(self.other_contact.pk)
        self.client.force_login(self.customer)
        for route in ('reception_day_board', 'reception_waitlist', 'loyalty_rewards', 'loyalty_referrals'):
            self.assertEqual(self.client.get(reverse(route)).status_code, 302)
        response = self.client.get(reverse('my_rewards'))
        self.assertContains(response, 'My Rewards')
        self.assertNotContains(response, other_wallet.code)
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse('my_rewards'), {'code': other_wallet.code}).status_code, 403)
        self.client.force_login(self.owner)
        for route in ('reception_waitlist_new', 'loyalty_policy', 'loyalty_rewards', 'loyalty_referrals'):
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        self.assertEqual(self.client.get(reverse('loyalty_wallet', args=[self.contact.pk])).status_code, 200)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase


class RewardConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_superuser('concurrent-rewards', password='Test-safe-pass987')
        customer = get_user_model().objects.create_user('concurrent-reward-customer')
        self.contact = CustomerRecord.objects.create(name='Customer', phone='9876543299', account=customer)
        LoyaltyPolicy.objects.create(enabled=True, rupees_per_point=100, reward_terms='Welcome gift', starts_at=timezone.now()-timedelta(days=1))
        self.wallet = activate_wallet(self.contact.pk)
        LoyaltyAward.objects.create(wallet=self.wallet, points=10, reason='Test award', source_key='concurrency-test')

    def run_parallel(self, operation):
        barrier = Barrier(2)
        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation(index)
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_concurrent_redemptions_cannot_overspend(self):
        def spend(index):
            try:
                redeem_points(self.contact.pk, 8, 'Gift delivered', uuid.uuid4(), self.actor)
                return 'saved'
            except ValidationError: return 'rejected'
        self.assertEqual(sorted(self.run_parallel(spend)), ['rejected', 'saved'])
        self.assertEqual(self.wallet.balance, 2)
        self.assertEqual(LoyaltySpend.objects.count(), 1)

    def test_concurrent_retry_creates_one_redemption(self):
        key = uuid.uuid4()
        results = self.run_parallel(lambda _: redeem_points(self.contact.pk, 8, 'Gift delivered', key, self.actor).pk)
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.wallet.balance, 2)
        self.assertEqual(LoyaltySpend.objects.count(), 1)

    def test_concurrent_receipt_awards_only_once(self):
        booking = Booking.objects.create(name=self.contact.name, phone=self.contact.phone, customer=self.contact.account,
                                         appointment_date=timezone.localdate(), appointment_time=time(10), status='completed')
        invoice = Invoice.objects.create(booking=booking, customer=self.contact.account, customer_name=self.contact.name, phone=self.contact.phone)
        InvoiceLine.objects.create(invoice=invoice, description='Visit', unit_price=1000)
        payment = InvoicePayment.objects.create(invoice=invoice, amount=1000, mode='cash', request_key=str(uuid.uuid4()))
        results = self.run_parallel(lambda _: purchase_points(self.contact.pk, payment.pk, self.actor).pk)
        self.assertEqual(results[0], results[1])
        self.assertEqual(LoyaltyAward.objects.filter(payment=payment).count(), 1)
