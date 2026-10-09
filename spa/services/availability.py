from datetime import datetime, time, timedelta
from django.utils import timezone
from ..models import Booking, Staff, StaffLeave, Room

BUSINESS_START = 10 * 60
BUSINESS_END = 22 * 60
SLOT_INTERVAL = 15

def time_to_minutes(value):
    return value.hour * 60 + value.minute

def minutes_to_time(minutes):
    if not 0 <= minutes < 24 * 60:
        raise ValueError("Appointment must end on the same day.")
    return time(minutes // 60, minutes % 60)

def calculate_end_time(start_time, duration):
    if not duration or duration <= 0:
        raise ValueError("Duration must be positive.")
    return minutes_to_time(time_to_minutes(start_time) + duration)

def is_within_business_hours(start_time, end_time):
    return BUSINESS_START <= time_to_minutes(start_time) < time_to_minutes(end_time) <= BUSINESS_END

def appointment_is_past(appointment_date, start_time):
    appointment = timezone.make_aware(datetime.combine(appointment_date, start_time))
    return appointment <= timezone.now()

def is_staff_on_leave(staff, appointment_date):
    return StaffLeave.objects.filter(staff=staff, leave_date=appointment_date).exists()

def day_resources(appointment_date, exclude_booking_id=None):
    leaves = set(StaffLeave.objects.filter(leave_date=appointment_date).values_list("staff_id", flat=True))
    staff = [s for s in Staff.objects.filter(is_active=True).order_by("pk") if s.pk not in leaves]
    rooms = list(Room.objects.filter(is_active=True).order_by("pk"))
    bookings = Booking.objects.filter(appointment_date=appointment_date, status__in=["pending", "confirmed"])
    if exclude_booking_id:
        bookings = bookings.exclude(pk=exclude_booking_id)
    intervals = []
    for b in bookings:
        start = time_to_minutes(b.appointment_time)
        # Unknown legacy end times reserve the remainder of the day conservatively.
        end = time_to_minutes(b.end_time) if b.end_time else min(BUSINESS_END, start + b.selected_duration) if b.selected_duration else BUSINESS_END
        intervals.append((b.staff_id, b.room_id, start, end))
        if b.secondary_staff_id:
            intervals.append((b.secondary_staff_id, b.room_id, start, end))
    return staff, rooms, intervals

def free_resources(resources, start_time, end_time):
    staff, rooms, intervals = resources
    start, end = time_to_minutes(start_time), time_to_minutes(end_time)
    overlaps = [i for i in intervals if i[2] < end and i[3] > start]
    busy_staff = {i[0] for i in overlaps}
    busy_rooms = {i[1] for i in overlaps}
    return [s for s in staff if s.pk not in busy_staff], [r for r in rooms if r.pk not in busy_rooms]

def is_staff_booked(staff, appointment_date, start_time, end_time, exclude_booking_id=None):
    resources = day_resources(appointment_date, exclude_booking_id)
    start, end = time_to_minutes(start_time), time_to_minutes(end_time)
    return any(i[0] == staff.pk and i[2] < end and i[3] > start for i in resources[2])

def is_room_booked(room, appointment_date, start_time, end_time, exclude_booking_id=None):
    resources = day_resources(appointment_date, exclude_booking_id)
    start, end = time_to_minutes(start_time), time_to_minutes(end_time)
    return any(i[1] == room.pk and i[2] < end and i[3] > start for i in resources[2])

def get_available_staff(appointment_date, start_time, end_time, exclude_booking_id=None):
    return free_resources(day_resources(appointment_date, exclude_booking_id), start_time, end_time)[0]

def get_available_rooms(appointment_date, start_time, end_time, exclude_booking_id=None):
    return free_resources(day_resources(appointment_date, exclude_booking_id), start_time, end_time)[1]

def check_slot_availability(appointment_date, start_time, duration, exclude_booking_id=None):
    end_time = calculate_end_time(start_time, duration)
    valid = is_within_business_hours(start_time, end_time) and not appointment_is_past(appointment_date, start_time)
    staff, rooms = free_resources(day_resources(appointment_date, exclude_booking_id), start_time, end_time) if valid else ([], [])
    available = valid and bool(staff and rooms)
    return {"available": available, "reason": None if available else "Time is past, outside business hours, or unavailable.",
            "start_time": start_time, "end_time": end_time, "staff": staff, "rooms": rooms}

def get_available_slots(appointment_date, duration, exclude_booking_id=None, service=None):
    if not duration or duration <= 0 or appointment_date < timezone.localdate():
        return []
    resources = day_resources(appointment_date, exclude_booking_id)
    if service and service.requires_couple_room:
        resources = (resources[0], [r for r in resources[1] if r.is_couple_room], resources[2])
    now = timezone.localtime()
    minimum = BUSINESS_START
    if appointment_date == now.date():
        minimum = max(minimum, (time_to_minutes(now.time()) // SLOT_INTERVAL + 1) * SLOT_INTERVAL)
    slots = []
    for minute in range(minimum, BUSINESS_END - duration + 1, SLOT_INTERVAL):
        start, end = minutes_to_time(minute), minutes_to_time(minute + duration)
        staff, rooms = free_resources(resources, start, end)
        if len(staff) >= (service.staff_required if service else 1) and rooms:
            slots.append({"start_time": start, "end_time": end, "staff": staff, "rooms": rooms})
    return slots

def get_next_available_slot(appointment_date, duration, from_time=None):
    return next((s for s in get_available_slots(appointment_date, duration)
                 if from_time is None or s["start_time"] >= from_time), None)
