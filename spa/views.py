from datetime import datetime

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BookingForm
from .models import (
    Booking,
    Room,
    Service,
    ServiceOption,
    Staff,
)
from .services.availability import (
    calculate_end_time,
    get_available_slots,
    is_room_booked,
    is_staff_booked,
    is_staff_on_leave,
)


# =========================================================
# CUSTOM BOOKING EXCEPTION
# =========================================================

class BookingUnavailableError(Exception):
    """
    Raised when a booking cannot be created.

    Possible reasons:
        - Invalid service
        - Invalid duration
        - Invalid date/time
        - Past date
        - No staff available
        - No room available
        - Selected slot already booked
    """

    pass


# =========================================================
# HOME PAGE
# =========================================================

def home(request):
    """
    Main Sukoon Wellness & Spa homepage.

    The homepage also supports booking POST requests if
    the home page booking form is submitted.

    Booking rules:
        - No payment required
        - No admin approval required
        - Booking is immediately confirmed when resources
          are successfully allocated
    """

    if request.method == "POST":

        booking_form = BookingForm(request.POST)

        if booking_form.is_valid():

            try:

                booking_obj = create_booking_with_resources(
                    booking_form
                )

            except BookingUnavailableError:

                booking_form.add_error(
                    None,
                    (
                        "Selected date and time is not available. "
                        "Please choose another slot."
                    ),
                )

            except Exception:

                booking_form.add_error(
                    None,
                    (
                        "Something went wrong while creating "
                        "your booking. Please try again."
                    ),
                )

            else:

                return redirect(
                    "booking_success",
                    booking_id=booking_obj.id,
                )

    else:

        booking_form = BookingForm()

    # =====================================================
    # ACTIVE SERVICES
    # =====================================================

    services = (
        Service.objects
        .filter(is_active=True)
        .select_related("category")
        .prefetch_related("options")
    )

    featured_services = services.filter(
        is_featured=True
    )

    context = {
        "services": services,
        "featured_services": featured_services,
        "booking_form": booking_form,
    }

    return render(
        request,
        "spa/home.html",
        context,
    )


# =========================================================
# ABOUT PAGE
# =========================================================

def about(request):
    """
    About Sukoon Wellness & Spa page.
    """

    return render(
        request,
        "spa/about.html",
    )


# =========================================================
# SERVICES PAGE
# =========================================================

def services(request):
    """
    Display all active spa services.
    """

    services_list = (
        Service.objects
        .filter(is_active=True)
        .select_related("category")
        .prefetch_related("options")
    )

    context = {
        "services": services_list,
    }

    return render(
        request,
        "spa/services.html",
        context,
    )


# =========================================================
# GALLERY PAGE
# =========================================================

def gallery(request):
    """
    Sukoon gallery page.
    """

    return render(
        request,
        "spa/gallery.html",
    )


# =========================================================
# BOOKING PAGE
# =========================================================

def booking(request):
    """
    Customer booking page.

    Successful booking:
        Booking -> CONFIRMED

    There is:
        - No payment
        - No admin approval
    """

    if request.method == "POST":

        booking_form = BookingForm(request.POST)

        if booking_form.is_valid():

            try:

                booking_obj = create_booking_with_resources(
                    booking_form
                )

            except BookingUnavailableError:

                booking_form.add_error(
                    None,
                    (
                        "Selected date and time is not available. "
                        "Please choose another slot."
                    ),
                )

            except Exception:

                booking_form.add_error(
                    None,
                    (
                        "Something went wrong while creating "
                        "your booking. Please try again."
                    ),
                )

            else:

                return redirect(
                    "booking_success",
                    booking_id=booking_obj.id,
                )

    else:

        booking_form = BookingForm()

    # =====================================================
    # ACTIVE SERVICES
    # =====================================================

    services = (
        Service.objects
        .filter(is_active=True)
        .select_related("category")
        .prefetch_related("options")
    )

    context = {
        "booking_form": booking_form,
        "services": services,
    }

    return render(
        request,
        "spa/booking.html",
        context,
    )


# =========================================================
# BOOKING SUCCESS PAGE
# =========================================================

def booking_success(request, booking_id):
    """
    Display confirmed booking details.
    """

    booking_obj = get_object_or_404(
        Booking.objects.select_related(
            "service",
            "staff",
            "room",
        ),
        id=booking_id,
    )

    context = {
        "booking": booking_obj,
    }

    return render(
        request,
        "spa/booking_success.html",
        context,
    )


# =========================================================
# CREATE BOOKING WITH STAFF + ROOM
# =========================================================

@transaction.atomic
def create_booking_with_resources(form):
    """
    Final server-side booking validation and creation.

    Customer selects:
        - Service
        - Duration
        - Date
        - Time

    System automatically assigns:
        - Staff
        - Room

    Booking flow:

        Customer
            ↓
        Form validation
            ↓
        Service validation
            ↓
        Duration validation
            ↓
        Date validation
            ↓
        Calculate end time
            ↓
        Find available staff
            ↓
        Find available room
            ↓
        Final availability check
            ↓
        Create booking
            ↓
        STATUS = CONFIRMED

    Payment is NOT involved.
    Admin approval is NOT involved.
    """

    cleaned_data = form.cleaned_data

    service = cleaned_data.get("service")
    appointment_date = cleaned_data.get("appointment_date")
    appointment_time = cleaned_data.get("appointment_time")
    duration = cleaned_data.get("duration")

    # =====================================================
    # BASIC VALIDATION
    # =====================================================

    if not service:
        raise BookingUnavailableError(
            "Service is required."
        )

    if not appointment_date:
        raise BookingUnavailableError(
            "Appointment date is required."
        )

    if not appointment_time:
        raise BookingUnavailableError(
            "Appointment time is required."
        )

    if not duration or duration <= 0:
        raise BookingUnavailableError(
            "Invalid duration."
        )

    # =====================================================
    # PREVENT PAST DATE
    # =====================================================

    today = timezone.localdate()

    if appointment_date < today:

        raise BookingUnavailableError(
            "Past dates are not available."
        )

    # =====================================================
    # VALIDATE SERVICE
    # =====================================================

    service = (
        Service.objects
        .select_for_update()
        .filter(
            id=service.id,
            is_active=True,
        )
        .first()
    )

    if not service:

        raise BookingUnavailableError(
            "Selected service is not available."
        )

    # =====================================================
    # VALIDATE SERVICE DURATION
    # =====================================================

    active_options = list(
        ServiceOption.objects
        .filter(
            service=service,
            is_active=True,
        )
        .order_by("duration")
    )

    if active_options:

        valid_durations = {
            option.duration
            for option in active_options
        }

        if duration not in valid_durations:

            raise BookingUnavailableError(
                "Selected duration is not available "
                "for this service."
            )

        selected_option = next(
            option
            for option in active_options
            if option.duration == duration
        )

        selected_price = selected_option.price

    else:

        # =================================================
        # SERVICE WITHOUT OPTIONS
        # =================================================

        if duration != service.duration:

            raise BookingUnavailableError(
                "Invalid service duration."
            )

        selected_price = service.price

    # =====================================================
    # CALCULATE END TIME
    # =====================================================

    try:

        end_time = calculate_end_time(
            appointment_time,
            duration,
        )

    except Exception:

        raise BookingUnavailableError(
            "Invalid appointment time or duration."
        )

    # =====================================================
    # FIND AVAILABLE STAFF
    # =====================================================

    staff_members = (
        Staff.objects
        .select_for_update()
        .filter(
            is_active=True,
        )
        .order_by("id")
    )

    selected_staff = None

    for staff in staff_members:

        # -------------------------------------------------
        # STAFF LEAVE
        # -------------------------------------------------

        if is_staff_on_leave(
            staff,
            appointment_date,
        ):
            continue

        # -------------------------------------------------
        # STAFF BOOKING
        # -------------------------------------------------

        if is_staff_booked(
            staff,
            appointment_date,
            appointment_time,
            end_time,
        ):
            continue

        selected_staff = staff

        break

    # =====================================================
    # NO STAFF AVAILABLE
    # =====================================================

    if not selected_staff:

        raise BookingUnavailableError(
            "No staff member is available for "
            "the selected time."
        )

    # =====================================================
    # FIND AVAILABLE ROOM
    # =====================================================

    rooms = (
        Room.objects
        .select_for_update()
        .filter(
            is_active=True,
        )
        .order_by("id")
    )

    selected_room = None

    for room in rooms:

        if is_room_booked(
            room,
            appointment_date,
            appointment_time,
            end_time,
        ):
            continue

        selected_room = room

        break

    # =====================================================
    # NO ROOM AVAILABLE
    # =====================================================

    if not selected_room:

        raise BookingUnavailableError(
            "No room is available for "
            "the selected time."
        )

    # =====================================================
    # FINAL STAFF CHECK
    # =====================================================
    # Protect against a slot becoming unavailable while
    # the booking transaction is being completed.

    if is_staff_booked(
        selected_staff,
        appointment_date,
        appointment_time,
        end_time,
    ):

        raise BookingUnavailableError(
            "Selected staff is no longer available."
        )

    # =====================================================
    # FINAL ROOM CHECK
    # =====================================================

    if is_room_booked(
        selected_room,
        appointment_date,
        appointment_time,
        end_time,
    ):

        raise BookingUnavailableError(
            "Selected room is no longer available."
        )

    # =====================================================
    # CREATE BOOKING
    # =====================================================

    booking = form.save(
        commit=False
    )

    booking.service = service

    booking.selected_duration = duration

    booking.selected_price = selected_price

    booking.appointment_date = appointment_date

    booking.appointment_time = appointment_time

    booking.end_time = end_time

    booking.staff = selected_staff

    booking.room = selected_room

    # =====================================================
    # IMMEDIATE CONFIRMATION
    # =====================================================
    #
    # No payment.
    # No admin approval.
    #
    # Staff + room availability has already been verified.

    booking.status = "confirmed"

    # =====================================================
    # SAVE
    # =====================================================

    booking.save()

    return booking


# =========================================================
# CONTACT PAGE
# =========================================================

def contact(request):
    """
    Contact form page.

    Currently stores no database record.
    It validates the submitted form and displays
    a success message.
    """

    if request.method == "POST":

        name = request.POST.get(
            "name",
            "",
        ).strip()

        phone = request.POST.get(
            "phone",
            "",
        ).strip()

        email = request.POST.get(
            "email",
            "",
        ).strip()

        subject = request.POST.get(
            "subject",
            "",
        ).strip()

        message = request.POST.get(
            "message",
            "",
        ).strip()

        # =================================================
        # REQUIRED FIELD VALIDATION
        # =================================================

        if not name or not phone or not subject or not message:

            messages.error(
                request,
                "Please fill in all required fields.",
            )

            return redirect(
                "contact"
            )

        # =================================================
        # SUCCESS
        # =================================================

        messages.success(
            request,
            (
                f"Thank you {name}! "
                "Your message has been received. "
                "Our team will contact you shortly."
            ),
        )

        return redirect(
            "contact"
        )

    return render(
        request,
        "spa/contact.html",
    )


# =========================================================
# AVAILABLE BOOKING SLOTS API
# =========================================================

def available_slots(request):
    """
    API endpoint:

        /api/available-slots/

    GET parameters:

        service
        date
        duration

    Example:

        /api/available-slots/
        ?service=1
        &date=2026-10-04
        &duration=60

    Customer receives only availability information.

    Staff names and room names are NEVER exposed.
    """

    # =====================================================
    # GET PARAMETERS
    # =====================================================

    service_id = request.GET.get(
        "service"
    )

    date_value = request.GET.get(
        "date"
    )

    duration_value = request.GET.get(
        "duration"
    )

    # =====================================================
    # SERVICE ID VALIDATION
    # =====================================================

    if not service_id:

        return JsonResponse(
            {
                "success": False,
                "message": "Service is required.",
                "slots": [],
            },
            status=400,
        )

    try:

        service_id = int(
            service_id
        )

    except (TypeError, ValueError):

        return JsonResponse(
            {
                "success": False,
                "message": "Invalid service.",
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # SERVICE LOOKUP
    # =====================================================

    service = (
        Service.objects
        .filter(
            id=service_id,
            is_active=True,
        )
        .first()
    )

    if not service:

        return JsonResponse(
            {
                "success": False,
                "message": "Selected service is not available.",
                "slots": [],
            },
            status=404,
        )

    # =====================================================
    # DATE REQUIRED
    # =====================================================

    if not date_value:

        return JsonResponse(
            {
                "success": False,
                "message": "Date is required.",
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # DATE PARSING
    # =====================================================

    try:

        appointment_date = datetime.strptime(
            date_value,
            "%Y-%m-%d",
        ).date()

    except (TypeError, ValueError):

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Invalid date format. "
                    "Use YYYY-MM-DD."
                ),
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # PREVENT PAST DATE
    # =====================================================

    today = timezone.localdate()

    if appointment_date < today:

        return JsonResponse(
            {
                "success": False,
                "message": "Past dates are not available.",
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # DURATION
    # =====================================================

    if duration_value:

        try:

            duration = int(
                duration_value
            )

        except (TypeError, ValueError):

            return JsonResponse(
                {
                    "success": False,
                    "message": "Invalid duration.",
                    "slots": [],
                },
                status=400,
            )

    else:

        duration = service.duration

    # =====================================================
    # BASIC DURATION VALIDATION
    # =====================================================

    if not duration or duration <= 0:

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Duration must be greater than zero."
                ),
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # VALIDATE SERVICE DURATION
    # =====================================================

    active_options = list(
        ServiceOption.objects
        .filter(
            service=service,
            is_active=True,
        )
        .values_list(
            "duration",
            flat=True,
        )
    )

    if active_options:

        if duration not in active_options:

            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Selected duration is not "
                        "available for this service."
                    ),
                    "slots": [],
                },
                status=400,
            )

    else:

        if duration != service.duration:

            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Invalid service duration."
                    ),
                    "slots": [],
                },
                status=400,
            )

    # =====================================================
    # GET AVAILABLE SLOTS
    # =====================================================

    try:

        slots = get_available_slots(
            appointment_date,
            duration,
        )

    except Exception:

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Unable to calculate available slots."
                ),
                "slots": [],
            },
            status=500,
        )

    # =====================================================
    # FORMAT RESPONSE
    # =====================================================

    response_slots = []

    for slot in slots:

        start_time = slot["start_time"]

        end_time = slot["end_time"]

        response_slots.append(
            {
                "start": start_time.strftime(
                    "%H:%M"
                ),

                "end": end_time.strftime(
                    "%H:%M"
                ),

                "display": (
                    f"{start_time.strftime('%I:%M %p')}"
                    f" - "
                    f"{end_time.strftime('%I:%M %p')}"
                ),

                # -------------------------------------------------
                # ONLY COUNTS ARE RETURNED.
                # -------------------------------------------------

                "available_staff": len(
                    slot.get(
                        "staff",
                        [],
                    )
                ),

                "available_rooms": len(
                    slot.get(
                        "rooms",
                        [],
                    )
                ),
            }
        )

def franchise(request):
    """
    Sukoon Wellness & Spa franchise page.
    """

    return render(
        request,
        "spa/franchise.html",
    )    



# =====================================================
    # API RESPONSE
    # =====================================================

    return JsonResponse(
        {
            "success": True,

            "service": service.name,

            "duration": duration,

            "date": date_value,

            "business_hours": {
                "start": "10:00",
                "end": "22:00",
            },

            "slot_interval": 15,

            "slots": response_slots,
        }
    )