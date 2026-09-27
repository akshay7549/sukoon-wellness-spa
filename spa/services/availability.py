from datetime import datetime, timedelta

from django.db.models import Q

from ..models import (
    Booking,
    Staff,
    StaffLeave,
    Room,
)


# =========================================================
# BUSINESS HOURS
# =========================================================

BUSINESS_START = 10 * 60       # 10:00 AM
BUSINESS_END = 22 * 60         # 10:00 PM

# Slot checking interval
# 15 means system checks:
# 10:00, 10:15, 10:30, 10:45...
SLOT_INTERVAL = 15


# =========================================================
# TIME → MINUTES
# =========================================================

def time_to_minutes(value):
    """
    Convert Python time object into minutes from midnight.
    """

    return value.hour * 60 + value.minute


# =========================================================
# MINUTES → TIME
# =========================================================

def minutes_to_time(minutes):
    """
    Convert minutes from midnight into a Python time object.
    """

    hours = minutes // 60
    mins = minutes % 60

    return datetime.strptime(
        f"{hours:02d}:{mins:02d}",
        "%H:%M"
    ).time()


# =========================================================
# CALCULATE END TIME
# =========================================================

def calculate_end_time(
    start_time,
    duration
):
    """
    Calculate booking end time from start time
    and service duration.
    """

    start_minutes = time_to_minutes(
        start_time
    )

    end_minutes = (
        start_minutes + duration
    )

    return minutes_to_time(
        end_minutes
    )


# =========================================================
# CHECK BUSINESS HOURS
# =========================================================

def is_within_business_hours(
    start_time,
    end_time
):
    """
    Check whether the complete booking
    fits inside spa business hours.
    """

    start_minutes = time_to_minutes(
        start_time
    )

    end_minutes = time_to_minutes(
        end_time
    )

    return (
        start_minutes >= BUSINESS_START
        and
        end_minutes <= BUSINESS_END
    )


# =========================================================
# STAFF LEAVE CHECK
# =========================================================

def is_staff_on_leave(
    staff,
    appointment_date
):
    """
    Check whether staff member is on leave
    on the selected date.
    """

    return StaffLeave.objects.filter(
        staff=staff,
        leave_date=appointment_date
    ).exists()


# =========================================================
# STAFF BOOKING OVERLAP
# =========================================================

def is_staff_booked(
    staff,
    appointment_date,
    start_time,
    end_time,
    exclude_booking_id=None
):
    """
    Check whether staff already has a booking
    overlapping the requested time.
    """

    bookings = Booking.objects.filter(
        staff=staff,
        appointment_date=appointment_date,
        status__in=[
            "pending",
            "confirmed",
        ]
    )

    if exclude_booking_id:
        bookings = bookings.exclude(
            id=exclude_booking_id
        )

    # Existing booking:
    #
    # existing_start < requested_end
    # AND
    # existing_end > requested_start

    return bookings.filter(
        Q(
            appointment_time__lt=end_time
        ),
        Q(
            end_time__gt=start_time
        )
    ).exists()


# =========================================================
# ROOM BOOKING OVERLAP
# =========================================================

def is_room_booked(
    room,
    appointment_date,
    start_time,
    end_time,
    exclude_booking_id=None
):
    """
    Check whether room already has a booking
    overlapping the requested time.
    """

    bookings = Booking.objects.filter(
        room=room,
        appointment_date=appointment_date,
        status__in=[
            "pending",
            "confirmed",
        ]
    )

    if exclude_booking_id:
        bookings = bookings.exclude(
            id=exclude_booking_id
        )

    return bookings.filter(
        Q(
            appointment_time__lt=end_time
        ),
        Q(
            end_time__gt=start_time
        )
    ).exists()


# =========================================================
# AVAILABLE STAFF
# =========================================================

def get_available_staff(
    appointment_date,
    start_time,
    end_time,
    exclude_booking_id=None
):
    """
    Return all staff members who are available
    for the complete booking duration.
    """

    staff_members = Staff.objects.filter(
        is_active=True
    ).order_by("name")

    available_staff = []

    for staff in staff_members:

        # Staff leave check
        if is_staff_on_leave(
            staff,
            appointment_date
        ):
            continue

        # Existing booking check
        if is_staff_booked(
            staff,
            appointment_date,
            start_time,
            end_time,
            exclude_booking_id
        ):
            continue

        available_staff.append(
            staff
        )

    return available_staff


# =========================================================
# AVAILABLE ROOMS
# =========================================================

def get_available_rooms(
    appointment_date,
    start_time,
    end_time,
    exclude_booking_id=None
):
    """
    Return all rooms available for
    the complete booking duration.
    """

    rooms = Room.objects.filter(
        is_active=True
    ).order_by("name")

    available_rooms = []

    for room in rooms:

        if is_room_booked(
            room,
            appointment_date,
            start_time,
            end_time,
            exclude_booking_id
        ):
            continue

        available_rooms.append(
            room
        )

    return available_rooms


# =========================================================
# CHECK COMPLETE SLOT
# =========================================================

def check_slot_availability(
    appointment_date,
    start_time,
    duration,
    exclude_booking_id=None
):
    """
    Check whether a complete slot is available.

    Returns:
        {
            "available": True/False,
            "start_time": ...,
            "end_time": ...,
            "staff": [...],
            "rooms": [...]
        }
    """

    # Calculate end time
    end_time = calculate_end_time(
        start_time,
        duration
    )

    # Business hour check
    if not is_within_business_hours(
        start_time,
        end_time
    ):
        return {
            "available": False,
            "reason": "Outside business hours",
            "start_time": start_time,
            "end_time": end_time,
            "staff": [],
            "rooms": [],
        }

    # Get available staff
    available_staff = get_available_staff(
        appointment_date,
        start_time,
        end_time,
        exclude_booking_id
    )

    # Get available rooms
    available_rooms = get_available_rooms(
        appointment_date,
        start_time,
        end_time,
        exclude_booking_id
    )

    # Both resources required
    available = (
        len(available_staff) > 0
        and
        len(available_rooms) > 0
    )

    return {
        "available": available,
        "reason": (
            None
            if available
            else "No staff or room available"
        ),
        "start_time": start_time,
        "end_time": end_time,
        "staff": available_staff,
        "rooms": available_rooms,
    }


# =========================================================
# GENERATE AVAILABLE SLOTS
# =========================================================

def get_available_slots(
    appointment_date,
    duration
):
    """
    Generate all available booking slots
    for a particular date and service duration.
    """

    slots = []

    current_minutes = BUSINESS_START

    while current_minutes < BUSINESS_END:

        start_time = minutes_to_time(
            current_minutes
        )

        end_minutes = (
            current_minutes + duration
        )

        # Service cannot finish after closing
        if end_minutes > BUSINESS_END:
            break

        end_time = minutes_to_time(
            end_minutes
        )

        availability = check_slot_availability(
            appointment_date,
            start_time,
            duration
        )

        if availability["available"]:

            slots.append({
                "start_time": start_time,
                "end_time": end_time,
                "staff": availability["staff"],
                "rooms": availability["rooms"],
            })

        current_minutes += SLOT_INTERVAL

    return slots


# =========================================================
# NEXT AVAILABLE SLOT
# =========================================================

def get_next_available_slot(
    appointment_date,
    duration,
    from_time=None
):
    """
    Find the first available slot after
    the specified time.
    """

    if from_time:
        current_minutes = time_to_minutes(
            from_time
        )

        # Round to next 15-minute interval
        remainder = (
            current_minutes % SLOT_INTERVAL
        )

        if remainder:
            current_minutes += (
                SLOT_INTERVAL - remainder
            )
    else:
        current_minutes = BUSINESS_START

    while current_minutes < BUSINESS_END:

        start_time = minutes_to_time(
            current_minutes
        )

        end_minutes = (
            current_minutes + duration
        )

        if end_minutes > BUSINESS_END:
            break

        availability = check_slot_availability(
            appointment_date,
            start_time,
            duration
        )

        if availability["available"]:

            return {
                "start_time": start_time,
                "end_time": availability["end_time"],
                "staff": availability["staff"],
                "rooms": availability["rooms"],
            }

        current_minutes += SLOT_INTERVAL

    return None