from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import datetime
from django.utils import timezone
from ..models import Booking, Service, ServiceOption, Staff, Room, PackageCredit, PackageRedemption
from .availability import calculate_end_time, is_within_business_hours, appointment_is_past, day_resources, free_resources

@transaction.atomic
def save_booking(form, customer=None):
    # Every booking writer takes the same locks in the same order.
    list(Staff.objects.select_for_update().order_by("pk"))
    list(Room.objects.select_for_update().order_by("pk"))
    original = Booking.objects.select_for_update().filter(pk=form.instance.pk).first() if form.instance.pk else None
    data = form.cleaned_data
    service = Service.objects.select_for_update().filter(pk=data["service"].pk).first()
    duration = data["duration"]
    same_option = original and original.service_id == service.pk and original.selected_duration == duration
    if original and hasattr(original,"package_redemption"):
        if not same_option or data.get("status") != "completed" or data.get("package_credit") != original.package_credit or data["appointment_date"]!=original.appointment_date or data["appointment_time"]!=original.appointment_time:
            raise ValidationError("A redeemed package visit cannot be rescheduled, cancelled or moved to another package.")
    if not service.is_active and not same_option:
        raise ValidationError("This treatment is unavailable.")
    option = ServiceOption.objects.select_for_update().filter(service=service, duration=duration, is_active=True).first()
    if not same_option and not option:
        raise ValidationError("This duration is no longer available.")
    day, start = data["appointment_date"], data["appointment_time"]
    status = data.get("status", "confirmed")
    unchanged_time = original and original.appointment_date == day and original.appointment_time == start and same_option and (status != "confirmed" or original.status == "confirmed")
    if not unchanged_time and appointment_is_past(day, start):
        raise ValidationError("Please choose a future appointment time.")
    end = calculate_end_time(start, duration)
    if not is_within_business_hours(start, end):
        raise ValidationError("Appointment must fit between 10 AM and 10 PM.")
    if status == "completed" and timezone.make_aware(datetime.combine(day, end)) > timezone.now():
        raise ValidationError("An appointment can only be completed after its end time.")
    staff, rooms = free_resources(day_resources(day, original.pk if original else None), start, end)
    selected_staff, selected_room = data.get("staff"), data.get("room")
    secondary_staff = data.get("secondary_staff")
    if service.requires_couple_room:
        rooms = [r for r in rooms if r.is_couple_room]
    if status == "confirmed":
        if selected_staff and selected_staff.pk not in {s.pk for s in staff}:
            raise ValidationError("Selected therapist is unavailable or on leave.")
        if selected_room and selected_room.pk not in {r.pk for r in rooms}:
            raise ValidationError("Selected room is unavailable.")
        if len(staff) < service.staff_required or not rooms:
            raise ValidationError("No therapist or room is available at this time.")
        selected_staff, selected_room = selected_staff or staff[0], selected_room or rooms[0]
        if service.staff_required == 2:
            others = [s for s in staff if s.pk != selected_staff.pk]
            if secondary_staff and secondary_staff.pk not in {s.pk for s in others}:
                raise ValidationError("The second therapist must be different and available.")
            secondary_staff = secondary_staff or others[0]
        else:
            secondary_staff = None
    credit = data.get("package_credit")
    if credit:
        credit = PackageCredit.objects.select_for_update().select_related("enrollment").get(pk=credit.pk)
        owner = data.get("customer", customer if not original else original.customer)
        if credit.enrollment.customer_id:
            if not owner or owner.pk != credit.enrollment.customer_id:
                raise ValidationError("This package belongs to another customer.")
        elif credit.enrollment.phone != data.get("phone"):
            raise ValidationError("The package phone must match the booking phone.")
        if service.pk not in (credit.treatment_id, credit.alternative_id):
            raise ValidationError("This package does not include the selected treatment.")
        if credit.max_duration and duration>credit.max_duration:
            raise ValidationError(f"This package covers sessions up to {credit.max_duration} minutes.")
        used = credit.redemptions.exclude(booking_id=original.pk if original else None).count() + credit.bookings.exclude(pk=original.pk if original else None).filter(status="confirmed").count()
        if status in ("confirmed", "completed") and used >= credit.total_sessions:
            raise ValidationError("All sessions in this package have been used or reserved.")
    booking = form.save(commit=False)
    booking.customer = data.get("customer", customer if not original else original.customer)
    booking.service = service
    booking.service_name_snapshot = original.service_name_snapshot if same_option and original.service_name_snapshot else service.name
    booking.selected_duration = duration
    same_credit = original and original.package_credit_id == (credit.pk if credit else None)
    if not credit and not (same_option and same_credit) and not option:
        raise ValidationError("This duration is no longer available. Choose an active duration before removing package coverage.")
    booking.selected_price = original.selected_price if same_option and same_credit else 0 if credit else option.price
    booking.package_credit = credit
    booking.appointment_date, booking.appointment_time, booking.end_time = day, start, end
    booking.staff, booking.room, booking.status = selected_staff, selected_room, status
    booking.secondary_staff = secondary_staff if service.staff_required == 2 else None
    booking.full_clean(exclude=["service"], validate_unique=False)
    booking.save()
    if booking.package_credit_id and booking.status=="completed":
        PackageRedemption.objects.get_or_create(booking=booking,defaults={"credit_id":booking.package_credit_id})
    form.instance = booking
    from ..notifications import queue_booking_notifications
    if not original:
        queue_booking_notifications(booking, booking.status)
    elif original.status != booking.status:
        queue_booking_notifications(booking, booking.status)
    elif (original.appointment_date, original.appointment_time) != (booking.appointment_date, booking.appointment_time):
        queue_booking_notifications(booking, "rescheduled")
    elif original.email != booking.email or original.phone != booking.phone:
        queue_booking_notifications(booking, "updated")
    return booking


@transaction.atomic
def transition_booking(booking_id, status):
    """One status path for bulk actions, customer cancellation and notifications."""
    list(Staff.objects.select_for_update().order_by("pk"))
    list(Room.objects.select_for_update().order_by("pk"))
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if status not in ("completed", "cancelled") or booking.status != "confirmed":
        return False
    end = booking.end_time or (calculate_end_time(booking.appointment_time, booking.selected_duration) if booking.selected_duration else booking.appointment_time)
    if status == "completed" and timezone.make_aware(datetime.combine(booking.appointment_date, end)) > timezone.now():
        raise ValidationError("Future appointments cannot be marked completed.")
    booking.status = status
    booking.save(update_fields=["status", "updated_at"])
    if booking.package_credit_id and status=="completed":
        PackageRedemption.objects.get_or_create(booking=booking,defaults={"credit_id":booking.package_credit_id})
    from ..notifications import queue_booking_notifications
    queue_booking_notifications(booking, status)
    return True
