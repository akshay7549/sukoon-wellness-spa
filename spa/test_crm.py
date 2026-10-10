from datetime import time, timedelta
from decimal import Decimal
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import Enquiry, FollowUpTask, CRMActivity, CustomerRecord, Booking, Service, Invoice, InvoiceLine, PackageEnrollment
from .services.invoicing import record_payment


class CRMTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('setup_roles', verbosity=0)
        cls.owner=get_user_model().objects.create_superuser('crm-owner','owner@example.com','TestPassword!123')
        cls.reception=get_user_model().objects.create_user('crm-reception',is_staff=True,password='TestPassword!123')
        cls.reception.groups.add(Group.objects.get(name='Receptionist'))
        cls.other_staff=get_user_model().objects.create_user('other-reception',is_staff=True,password='TestPassword!123')
        cls.other_staff.groups.add(Group.objects.get(name='Receptionist'))
        cls.customer=get_user_model().objects.create_user('crm-customer','customer@example.com','TestPassword!123')
        cls.stranger=get_user_model().objects.create_user('crm-stranger','stranger@example.com','TestPassword!123')
        cls.service=Service.objects.create(name='CRM Test Therapy')

    def setUp(self):
        self.client.force_login(self.reception)
        self.phone='9031640551'
        self.due=timezone.localtime(timezone.now()+timedelta(days=2)).replace(second=0,microsecond=0)

    def lead_data(self,stage='new',lead=None):
        data={'name':'CRM Test Guest','phone':self.phone,'email':'guest@example.com','kind':'contact','source':'phone','subject':'Therapy enquiry','message':'Please call about a treatment','status':stage,'assigned_to':self.reception.pk,'next_action':'Call to confirm treatment','next_follow_up':self.due.strftime('%Y-%m-%dT%H:%M'),'version':lead.updated_at.isoformat() if lead else ''}
        return data

    def create_lead(self):
        response=self.client.post(reverse('crm_lead_new'),self.lead_data())
        self.assertEqual(response.status_code,302,response.context and response.context['form'].errors)
        return Enquiry.objects.get()

    def booking(self,customer=None):
        return Booking.objects.create(name='CRM Test Guest',phone=self.phone,customer=customer,service=self.service,selected_duration=60,selected_price=1000,amount_paid=0,appointment_date=timezone.localdate()+timedelta(days=3),appointment_time=time(12),end_time=time(13))

    def test_lead_creates_contact_owner_next_task_and_pipeline_cards(self):
        lead=self.create_lead()
        self.assertEqual(lead.assigned_to,self.reception)
        self.assertEqual(lead.next_task.contact.phone,self.phone)
        self.assertEqual(lead.next_task.assigned_to,self.reception)
        self.assertContains(self.client.get(reverse('crm_pipeline')),'Call to confirm treatment')
        self.assertContains(self.client.get(reverse('crm_lead_edit',args=[lead.pk])),'Lead Activity')
        other=self.client.get(reverse('crm_lead_edit',args=[lead.pk]))
        self.assertEqual(other.context['form']['assigned_to'].value(),self.reception.pk)

    def test_open_lead_requires_deadline_owner_and_action(self):
        data=self.lead_data();data.update(next_action='',next_follow_up='',assigned_to='')
        response=self.client.post(reverse('crm_lead_new'),data)
        self.assertEqual(response.status_code,200)
        self.assertIn('next_action',response.context['form'].errors)
        self.assertIn('next_follow_up',response.context['form'].errors)
        self.assertIn('assigned_to',response.context['form'].errors)
        self.assertFalse(Enquiry.objects.exists())

    def test_lost_reason_closes_tasks_and_stale_updates_are_rejected(self):
        lead=self.create_lead();stale=self.lead_data('interested',lead)
        data=self.lead_data('lost',lead)
        response=self.client.post(reverse('crm_lead_edit',args=[lead.pk]),data)
        self.assertIn('lost_reason',response.context['form'].errors)
        data['lost_reason']='Customer chose a different date.'
        self.assertEqual(self.client.post(reverse('crm_lead_edit',args=[lead.pk]),data).status_code,302)
        lead.refresh_from_db();self.assertEqual(lead.status,'lost');self.assertIsNone(lead.next_task)
        self.assertEqual(FollowUpTask.objects.get().status,'cancelled')
        response=self.client.post(reverse('crm_lead_edit',args=[lead.pk]),stale)
        self.assertContains(response,'changed while you were editing')
        lead.refresh_from_db();self.assertEqual(lead.status,'lost')

    def test_conversion_requires_matching_completed_booking(self):
        lead=self.create_lead();booking=self.booking()
        data=self.lead_data('converted',lead);data['linked_booking']=booking.pk
        response=self.client.post(reverse('crm_lead_edit',args=[lead.pk]),data)
        self.assertIn('linked_booking',response.context['form'].errors)
        booking.status='completed';booking.save()
        self.assertEqual(self.client.post(reverse('crm_lead_edit',args=[lead.pk]),data).status_code,302)
        lead.refresh_from_db();self.assertEqual(lead.status,'converted')
        foreign=self.booking();foreign.phone='9876543210';foreign.save()
        data=self.lead_data('booked',lead);data['linked_booking']=foreign.pk
        response=self.client.post(reverse('crm_lead_edit',args=[lead.pk]),data)
        self.assertIn('linked_booking',response.context['form'].errors)

    def test_task_completion_logs_outcome_and_keeps_open_lead_next_action(self):
        lead=self.create_lead();task=lead.next_task
        data={'outcome':'Spoke with customer; waiting for preferred time.','version':task.updated_at.isoformat()}
        response=self.client.post(reverse('crm_task_complete',args=[task.pk]),data)
        self.assertIn('next_action',response.context['form'].errors)
        data.update(next_action='Confirm preferred time',next_follow_up=(self.due+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'))
        self.assertEqual(self.client.post(reverse('crm_task_complete',args=[task.pk]),data).status_code,302)
        task.refresh_from_db();lead.refresh_from_db()
        self.assertEqual(task.status,'completed');self.assertEqual(task.completed_by,self.reception)
        self.assertNotEqual(lead.next_task_id,task.pk)
        self.assertEqual(lead.next_task.title,'Confirm preferred time')
        before=CRMActivity.objects.count()
        self.client.post(reverse('crm_task_complete',args=[task.pk]),data)
        self.assertEqual(CRMActivity.objects.count(),before)
        self.assertEqual(FollowUpTask.objects.count(),2)

    def test_task_edit_owner_and_due_filters(self):
        lead=self.create_lead();task=lead.next_task
        task.due_at=timezone.now()-timedelta(hours=1);task.save()
        self.assertContains(self.client.get(reverse('crm_tasks')+'?tab=overdue'),'Call to confirm treatment')
        self.assertEqual(self.client.get(reverse('crm_tasks')+'?owner=mine').context['page'].paginator.count,1)
        self.assertEqual(self.client.get(reverse('crm_tasks')+f'?owner={self.other_staff.pk}').context['page'].paginator.count,0)
        self.client.force_login(self.other_staff)
        form=self.client.get(reverse('crm_task_edit',args=[task.pk])).context['form']
        self.assertEqual(form['assigned_to'].value(),self.reception.pk)
        self.assertEqual(self.client.get(reverse('crm_tasks')+'?owner=mine').context['page'].paginator.count,0)

    def test_guest_link_requires_verification_and_preserves_money_and_ownership(self):
        booking=self.booking()
        invoice=Invoice.objects.create(customer_name=booking.name,phone=self.phone,booking=booking,opening_paid=100)
        line=InvoiceLine.objects.create(invoice=invoice,description='Package',unit_price=1000)
        package=PackageEnrollment.objects.create(invoice_line=line,customer_name=booking.name,phone=self.phone,package_name='Test Package')
        record_payment(invoice.pk,{'amount':Decimal('100'),'mode':'cash','reference':'TEST','received_at':timezone.now(),'request_key':uuid.uuid4()},self.owner)
        data={'account':self.customer.pk,'verification_note':'Verified in person with guest purchase references.'}
        response=self.client.post(reverse('crm_account_link',args=[self.phone]),data)
        self.assertIn('verified',response.context['form'].errors)
        data['verified']='on'
        self.assertEqual(self.client.post(reverse('crm_account_link',args=[self.phone]),data).status_code,302)
        for obj in (booking,invoice,package):obj.refresh_from_db();self.assertEqual(obj.customer_id,self.customer.pk)
        self.assertEqual(invoice.net_amount,1000);self.assertEqual(invoice.amount_paid,200)
        data['account']=self.stranger.pk
        response=self.client.post(reverse('crm_account_link',args=[self.phone]),data)
        self.assertContains(response,'already linked to another account')
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse('my_bookings')),'Test Package')
        self.assertEqual(self.client.get(reverse('invoice_print',args=[invoice.pk])).status_code,200)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse('invoice_print',args=[invoice.pk])).status_code,404)

    def test_identity_conflict_rolls_back_all_guest_links(self):
        guest=self.booking();owned=self.booking(customer=self.stranger)
        data={'account':self.customer.pk,'verification_note':'Reception checked identity in person.','verified':'on'}
        response=self.client.post(reverse('crm_account_link',args=[self.phone]),data)
        self.assertContains(response,'identity conflict')
        guest.refresh_from_db();owned.refresh_from_db()
        self.assertIsNone(guest.customer_id);self.assertEqual(owned.customer,self.stranger)
        self.assertIsNone(CustomerRecord.objects.get(phone=self.phone).account_id)

    def test_customer_360_does_not_double_count_linked_invoice_and_bookings(self):
        booking=self.booking();booking.amount_paid=200;booking.save()
        invoice=Invoice.objects.create(customer_name=booking.name,phone=self.phone,booking=booking,opening_paid=200)
        InvoiceLine.objects.create(invoice=invoice,description='Treatment',unit_price=1000)
        record_payment(invoice.pk,{'amount':Decimal('100'),'mode':'upi','reference':'TEST','received_at':timezone.now(),'request_key':uuid.uuid4()},self.owner)
        response=self.client.get(reverse('crm_customer_detail',args=[self.phone]))
        self.assertEqual(response.context['received'],300)
        self.assertEqual(response.context['dated_received'],100)
        self.assertEqual(response.context['due'],700)
        self.client.post(reverse('crm_customer_detail',args=[self.phone]),{'action':'activity','kind':'call','body':'Customer prefers afternoon appointments.'})
        self.assertContains(self.client.get(reverse('crm_customer_detail',args=[self.phone])),'Customer prefers afternoon appointments.')

    def test_customers_cannot_access_crm_and_view_only_cannot_change_records(self):
        lead=self.create_lead()
        self.client.force_login(self.customer)
        for url in [reverse('crm_pipeline'),reverse('crm_tasks'),reverse('crm_customers'),reverse('crm_customer_detail',args=[self.phone])]:
            self.assertEqual(self.client.get(url).status_code,302)
        viewer=get_user_model().objects.create_user('crm-viewer',is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_enquiry',content_type__app_label='spa'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('crm_lead_edit',args=[lead.pk])).status_code,200)
        self.assertEqual(self.client.post(reverse('crm_lead_edit',args=[lead.pk]),self.lead_data('lost',lead)).status_code,403)
        self.assertEqual(self.client.get(reverse('crm_tasks')).status_code,403)

    def test_crm_post_requires_csrf_and_get_does_not_create_data(self):
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.reception)
        self.assertEqual(strict.post(reverse('crm_lead_new'),self.lead_data()).status_code,403)
        before=Enquiry.objects.count()
        self.client.get(reverse('crm_lead_new'));self.client.get(reverse('crm_pipeline'));self.client.get(reverse('crm_customers'))
        self.assertEqual(Enquiry.objects.count(),before)
        self.assertEqual(FollowUpTask.objects.count(),0)

    @override_settings(EMAIL_ENABLED=False,WHATSAPP_ENABLED=False)
    def test_public_enquiry_is_visible_and_contact_backfill_is_idempotent(self):
        self.client.logout()
        self.client.post(reverse('contact'),{'name':'Website Guest','phone':self.phone,'subject':'Treatment','message':'Please call me'})
        lead=Enquiry.objects.get();self.assertIsNotNone(lead.contact_id);self.assertEqual(lead.source,'website')
        self.assertIsNone(lead.assigned_to_id)
        call_command('sync_crm_contacts',verbosity=0);call_command('sync_crm_contacts',verbosity=0)
        self.assertEqual(CustomerRecord.objects.count(),1)
        self.client.force_login(self.reception)
        self.assertContains(self.client.get(reverse('crm_pipeline')),'Website Guest')


from django.test import TransactionTestCase
from django.db import close_old_connections, connection
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.core.exceptions import ValidationError
from .services.crm import complete_task, link_guest_records


class CRMConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != 'mysql': self.skipTest('Requires real MySQL row locks')
        self.actor=get_user_model().objects.create_superuser('crm-lock-owner','locks@example.com','TestPassword!123')

    def run_parallel(self,operation):
        barrier=Barrier(2)
        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation(index)
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,range(2)))

    def test_concurrent_completion_creates_one_next_action(self):
        lead=Enquiry.objects.create(name='Concurrent Guest',phone='9031640551',kind='contact',message='Test',assigned_to=self.actor)
        task=FollowUpTask.objects.create(lead=lead,contact=lead.contact,title='Call',assigned_to=self.actor,due_at=timezone.now()+timedelta(days=1))
        lead.next_task=task;lead.save()
        data={'version':task.updated_at.isoformat(),'outcome':'Customer requested another call.','next_action':'Call again','next_follow_up':timezone.now()+timedelta(days=2)}
        outcomes=self.run_parallel(lambda _:complete_task(task.pk,data,self.actor))
        self.assertEqual(sorted(outcomes),[False,True])
        self.assertEqual(FollowUpTask.objects.count(),2)
        self.assertEqual(CRMActivity.objects.filter(kind='task').count(),1)

    def test_concurrent_account_claims_cannot_split_guest_records(self):
        contact=CustomerRecord.objects.create(name='Guest',phone='9031640551')
        invoice=Invoice.objects.create(customer_name='Guest',phone=contact.phone)
        customers=[get_user_model().objects.create_user('claim-a'),get_user_model().objects.create_user('claim-b')]
        def claim(index):
            try:
                link_guest_records(contact.pk,{'account':customers[index],'verified':True,'verification_note':'Reception verified identity in person.'},self.actor)
                return 'saved'
            except ValidationError:return 'rejected'
        self.assertEqual(sorted(self.run_parallel(claim)),['rejected','saved'])
        contact.refresh_from_db();invoice.refresh_from_db()
        self.assertEqual(contact.account_id,invoice.customer_id)
        self.assertIn(contact.account_id,[u.pk for u in customers])
        self.assertEqual(CRMActivity.objects.filter(kind='account_link').count(),1)
