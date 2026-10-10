import re
from django.core.management.base import BaseCommand
from django.db import transaction
from spa.models import CustomerRecord, Booking, Invoice, Enquiry


class Command(BaseCommand):
    help = "Create CRM phone contacts from existing records without assigning customer accounts or changing history."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for model, name_field in [(Booking, "name"), (Invoice, "customer_name"), (Enquiry, "name")]:
            for pk, phone, name in model.objects.order_by("pk").values_list("pk", "phone", name_field).iterator():
                if not re.fullmatch(r"[6-9]\d{9}", phone or ""):
                    continue
                record, is_new = CustomerRecord.objects.get_or_create(phone=phone, defaults={"name": name})
                created += is_new
                if not record.name:
                    CustomerRecord.objects.filter(pk=record.pk, name="").update(name=name)
                if model is Enquiry:
                    Enquiry.objects.filter(pk=pk, contact__isnull=True).update(contact=record)
        self.stdout.write(self.style.SUCCESS(f"CRM contacts ready: {created} new contacts. Accounts and purchase ownership unchanged."))
