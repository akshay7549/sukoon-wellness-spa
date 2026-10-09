import logging
import hashlib
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from .models import Notification

logger = logging.getLogger(__name__)

def email_enabled():
    return settings.EMAIL_ENABLED

def queue_email(key, recipient, subject, message, due_at=None, booking=None):
    if not email_enabled() or not recipient:
        return
    if len(key)>200: key = hashlib.sha256(key.encode()).hexdigest()
    Notification.objects.get_or_create(dedupe_key=key, defaults={"channel":"email", "recipient":recipient, "subject":subject, "message":message, "due_at":due_at or timezone.now(), "booking":booking})

def queue_booking_notifications(booking, event):
    Notification.objects.filter(booking=booking, status="pending").update(status="cancelled")
    when = timezone.make_aware(datetime.combine(booking.appointment_date, booking.appointment_time))
    treatment = booking.service_name_snapshot or (booking.service.name if booking.service else "Wellness treatment")
    message = f"Hello {booking.name}, your Sukoon appointment is {event}.\nBooking #{booking.pk}\n{treatment}\n{when:%d %b %Y, %I:%M %p}\nManage your bookings: {settings.PUBLIC_SITE_URL}/my-bookings/\nReception: +91 90316 40551"
    revision = booking.updated_at.isoformat()
    queue_email(f"booking:{booking.pk}:{event}:{revision}:email", booking.email, f"Sukoon booking {event}", message, booking=booking)
    if booking.status == "confirmed" and when - timedelta(hours=24) > timezone.now():
        queue_email(f"booking:{booking.pk}:reminder:{revision}:email", booking.email, "Your Sukoon appointment is tomorrow", message, when-timedelta(hours=24), booking)
    # WhatsApp uses approved provider templates, never unsolicited free-form reminders.
    if settings.WHATSAPP_ENABLED and settings.WHATSAPP_TEMPLATE_NAME and booking.phone:
        phone = booking.phone.lstrip("+")
        if len(phone) == 10: phone = "91" + phone
        for kind, due in [(event, timezone.now()), ("reminder", when-timedelta(hours=24))]:
            if kind == "reminder" and (booking.status != "confirmed" or due <= timezone.now()): continue
            Notification.objects.get_or_create(dedupe_key=f"booking:{booking.pk}:{kind}:{revision}:wa", defaults={"booking":booking,"channel":"whatsapp","recipient":phone,"subject":kind,"message":message,"due_at":due})

def queue_enquiry_notification(enquiry):
    queue_email(f"enquiry:{enquiry.pk}", settings.BUSINESS_EMAIL, f"New {enquiry.kind} enquiry", f"{enquiry.name}\n{enquiry.phone}\n{enquiry.email}\n{enquiry.city}\n{enquiry.message}")
