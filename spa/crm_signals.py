"""Create a phone contact without claiming records for any account."""
import re
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Booking, Invoice, Enquiry, CustomerRecord


@receiver(post_save, sender=Booking)
@receiver(post_save, sender=Invoice)
@receiver(post_save, sender=Enquiry)
def capture_contact(sender, instance, raw=False, **kwargs):
    if raw or not re.fullmatch(r"[6-9]\d{9}", instance.phone or ""):
        return
    contact, _ = CustomerRecord.objects.get_or_create(phone=instance.phone, defaults={"name": getattr(instance, "customer_name", None) or instance.name})
    if not contact.name:
        CustomerRecord.objects.filter(pk=contact.pk, name="").update(name=getattr(instance, "customer_name", None) or instance.name)
    if sender is Enquiry and instance.contact_id != contact.pk:
        Enquiry.objects.filter(pk=instance.pk).update(contact=contact)
        instance.contact = contact
