from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Create Owner and Receptionist roles without changing any user's assigned permissions."
    def handle(self, *args, **options):
        owner, _ = Group.objects.get_or_create(name="Owner")
        owner.permissions.set(Permission.objects.filter(content_type__app_label="spa"))
        reception, _ = Group.objects.get_or_create(name="Receptionist")
        reception.permissions.set(Permission.objects.filter(content_type__app_label="spa", content_type__model__in=["booking","enquiry","service","serviceoption","servicecategory","staff","room","staffleave"], codename__in=["view_booking","add_booking","change_booking","view_enquiry","change_enquiry","view_service","view_serviceoption","view_servicecategory","view_staff","view_room","view_staffleave"]))
        self.stdout.write(self.style.SUCCESS("Owner and Receptionist roles ready. Assign staff roles in Users; users were not modified."))
        reception.permissions.add(*Permission.objects.filter(content_type__app_label="spa",codename__in=["view_invoice","add_invoice","change_invoice","view_invoicepayment","add_invoicepayment","view_packageenrollment","view_packagecredit","view_customerrecord","add_customerrecord","change_customerrecord"]))
        reception.permissions.add(*Permission.objects.filter(content_type__app_label="spa", codename__in=["add_enquiry", "view_followuptask", "add_followuptask", "change_followuptask", "view_crmactivity", "add_crmactivity", "link_customer_account"]))
