from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from ..models import Booking, Staff, Room, ReceptionEvent, WaitlistEntry
from .bookings import transition_booking, save_booking


def finish_room(booking):
    if booking.room_id and (booking.status == "completed" or booking.reception_stage == "in_service"):
        room = Room.objects.select_for_update().get(pk=booking.room_id)
        until = timezone.now() + timedelta(minutes=room.cleanup_minutes)
        if room.cleanup_minutes and (not room.cleaning_until or room.cleaning_until < until):
            room.cleaning_until = until
            room.save(update_fields=["cleaning_until"])


@transaction.atomic
def move_visit(booking_id, stage, version, note, actor):
    list(Staff.objects.select_for_update().order_by("pk"))
    list(Room.objects.select_for_update().order_by("pk"))
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.updated_at.isoformat() != version:
        raise ValidationError("This visit changed. Reload the Day Board before updating it.")
    if booking.status != "confirmed":
        raise ValidationError("This visit is already closed.")
    if booking.appointment_date != timezone.localdate():
        raise ValidationError("Reception stages can be updated only on the appointment day.")
    current = booking.reception_stage
    now = timezone.now()
    if stage == "checked_in" and current == "expected":
        booking.checked_in_at = now
    elif stage == "in_service" and current == "checked_in":
        start = timezone.make_aware(datetime.combine(booking.appointment_date, booking.appointment_time))
        if now < start:
            raise ValidationError("Service can start at its reserved appointment time. Reschedule before checking in to start earlier.")
        if not booking.room_id or not booking.staff_id:
            raise ValidationError("Assign the therapist and room before starting service.")
        room = Room.objects.get(pk=booking.room_id)
        if room.cleaning_until and room.cleaning_until > now:
            raise ValidationError("The room is still being cleaned.")
        # An earlier visit running late blocks the next one, even after its scheduled end.
        overlaps = Booking.objects.filter(status="confirmed", reception_stage="in_service").exclude(pk=booking.pk)
        from django.db.models import Q
        staff_ids = [i for i in (booking.staff_id, booking.secondary_staff_id) if i]
        if overlaps.filter(Q(room_id=booking.room_id) | Q(staff_id__in=staff_ids) | Q(secondary_staff_id__in=staff_ids)).exists():
            raise ValidationError("The therapist or room is still serving another customer.")
        booking.service_started_at = now
    elif stage in ("completed", "cancelled", "no_show"):
        if stage == "completed" and current != "in_service":
            raise ValidationError("Start service before marking this visit completed.")
        if stage == "no_show":
            start = timezone.make_aware(datetime.combine(booking.appointment_date, booking.appointment_time))
            if current != "expected" or start > now:
                raise ValidationError("No-show is available after the appointment time for customers who have not checked in.")
            if not note.strip():
                raise ValidationError("Record a reason for the no-show.")
            booking.reception_stage = "no_show"
            booking.save(update_fields=["reception_stage"])
        transition_booking(booking.pk, "completed" if stage == "completed" else "cancelled")
        ReceptionEvent.objects.create(booking=booking, stage=stage, note=note, actor=actor)
        return
    else:
        raise ValidationError("Use the next reception stage; backward changes are not allowed.")
    booking.reception_stage = stage
    booking.save(update_fields=["reception_stage", "checked_in_at", "service_started_at", "updated_at"])
    ReceptionEvent.objects.create(booking=booking, stage=stage, note=note, actor=actor)


@transaction.atomic
def promote_waitlist(entry_id, form, version):
    list(Staff.objects.select_for_update().order_by("pk"))
    list(Room.objects.select_for_update().order_by("pk"))
    entry = WaitlistEntry.objects.select_for_update().select_related("contact").get(pk=entry_id)
    if entry.status not in ("waiting", "contacted") or entry.updated_at.isoformat() != version:
        raise ValidationError("This waitlist entry changed or was already booked. Reload it.")
    data = form.cleaned_data
    if data["phone"] != entry.contact.phone or data["service"].pk != entry.service_id or data["duration"] != entry.duration or data["appointment_date"] != entry.preferred_date or not entry.earliest_time <= data["appointment_time"] <= entry.latest_time:
        raise ValidationError("Choose this customer's requested treatment, duration, day and time window.")
    booking = save_booking(form, customer=entry.contact.account)
    entry.booking = booking
    entry.status = "booked"
    entry.save(update_fields=["booking", "status", "updated_at"])
    return booking
