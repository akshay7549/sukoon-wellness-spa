from datetime import timedelta
import logging
import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from spa.models import Notification, RateLimitBucket, Booking

logger = logging.getLogger("spa.notifications")

class Command(BaseCommand):
    help = "Deliver queued notifications; run once per minute. Disabled channels stay unsent."
    def add_arguments(self, parser):
        parser.add_argument("--limit",type=int,default=100)
    def handle(self,*args,**options):
        if not settings.EMAIL_ENABLED and not settings.WHATSAPP_ENABLED:
            self.stdout.write("Notification providers disabled; nothing sent.")
            return
        channels = []
        if settings.EMAIL_ENABLED: channels.append("email")
        if settings.WHATSAPP_ENABLED:
            if not all([settings.WHATSAPP_API_URL.startswith("https://"),settings.WHATSAPP_ACCESS_TOKEN,settings.WHATSAPP_TEMPLATE_NAME]):
                raise CommandError("Configure HTTPS WhatsApp API URL, access token, and approved template.")
            channels.append("whatsapp")
        RateLimitBucket.objects.filter(expires_at__lt=timezone.now()).delete()
        ids = list(Notification.objects.filter(status="pending",channel__in=channels,due_at__lte=timezone.now()).order_by("due_at").values_list("pk",flat=True)[:options["limit"]])
        sent=0
        for pk in ids:
            with transaction.atomic():
                job=Notification.objects.select_for_update().get(pk=pk)
                if job.status!="pending":continue
                if job.booking_id and job.subject in ("reminder", "Your Sukoon appointment is tomorrow") and job.booking.status!="confirmed":
                    job.status="cancelled";job.save(update_fields=["status"]);continue
                job.status="processing";job.attempts+=1;job.save(update_fields=["status","attempts"])
            try:
                if job.channel=="email":
                    count=EmailMessage(subject=job.subject,body=job.message,from_email=settings.DEFAULT_FROM_EMAIL,to=[job.recipient]).send()
                    if count!=1:raise RuntimeError("Mail provider did not accept the message.")
                else:
                    b=job.booking
                    values=[b.name,b.service_name_snapshot or "Wellness treatment",b.appointment_date.strftime("%d %b %Y"),b.appointment_time.strftime("%I:%M %p"),job.subject]
                    payload={"messaging_product":"whatsapp","to":job.recipient,"type":"template","template":{"name":settings.WHATSAPP_TEMPLATE_NAME,"language":{"code":settings.WHATSAPP_TEMPLATE_LANGUAGE},"components":[{"type":"body","parameters":[{"type":"text","text":v} for v in values]}]}}
                    response=requests.post(settings.WHATSAPP_API_URL,headers={"Authorization":"Bearer "+settings.WHATSAPP_ACCESS_TOKEN},json=payload,timeout=15)
                    if not response.ok:raise RuntimeError("WhatsApp provider rejected the request.")
                job.status="sent";job.sent_at=timezone.now();job.last_error="";sent+=1
                if job.channel=="whatsapp" and job.booking_id:
                    Booking.objects.filter(pk=job.booking_id).update(whatsapp_sent=True,whatsapp_last_status="provider_accepted")
            except Exception as exc:
                # Never store exception text: it could contain provider credentials.
                job.last_error=type(exc).__name__
                job.status="pending" if job.attempts<3 else "failed"
                job.due_at=timezone.now()+timedelta(minutes=5*job.attempts)
                logger.warning("Notification %s failed (%s)",job.pk,type(exc).__name__)
            job.save(update_fields=["status","sent_at","last_error","due_at"])
        self.stdout.write(f"Sent {sent} notifications.")
