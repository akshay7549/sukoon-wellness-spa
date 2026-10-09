from django.core.exceptions import ValidationError
from django.db import transaction
from ..models import Booking, Service, ServiceOption, Staff, Room
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
    if not service.is_active and not same_option:
        raise ValidationError("This treatment is unavailable.")
    option = ServiceOption.objects.select_for_update().filter(service=service, duration=duration, is_active=True).first()
    if not same_option and not option:
        raise ValidationError("This duration is no longer available.")
    day, start = data["appointment_date"], data["appointment_time"]
    unchanged_time = original and original.appointment_date == day and original.appointment_time == start and original.status == data.get("status", "confirmed")
    if not unchanged_time and appointment_is_past(day, start):
        raise ValidationError("Please choose a future appointment time.")
    end = calculate_end_time(start, duration)
    if not is_within_business_hours(start, end):
        raise ValidationError("Appointment must fit between 10 AM and 10 PM.")
    status = data.get("status", "confirmed")
    staff, rooms = free_resources(day_resources(day, original.pk if original else None), start, end)
    selected_staff, selected_room = data.get("staff"), data.get("room")
    if status == "confirmed":
        if selected_staff and selected_staff.pk not in {s.pk for s in staff}:
            raise ValidationError("Selected therapist is unavailable or on leave.")
        if selected_room and selected_room.pk not in {r.pk for r in rooms}:
            raise ValidationError("Selected room is unavailable.")
        if not staff or not rooms:
            raise ValidationError("No therapist or room is available at this time.")
        selected_staff, selected_room = selected_staff or staff[0], selected_room or rooms[0]
    booking = form.save(commit=False)
    booking.customer = data.get("customer", customer if not original else original.customer)
    booking.service = service
    booking.service_name_snapshot = original.service_name_snapshot if same_option and original.service_name_snapshot else service.name
    booking.selected_duration = duration
    booking.selected_price = original.selected_price if same_option else option.price
    booking.appointment_date, booking.appointment_time, booking.end_time = day, start, end
    booking.staff, booking.room, booking.status = selected_staff, selected_room, status
    booking.full_clean(exclude=["service"], validate_unique=False)
    booking.save()
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
