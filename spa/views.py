from datetime import datetime, date

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BookingForm
from .models import Service, ServiceOption, Staff, Room
from .services.availability import (
    calculate_end_time,
    get_available_slots,
    is_staff_on_leave,
    is_staff_booked,
    is_room_booked,
)


# =========================================================
# HOME PAGE
# =========================================================

def home(request):

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
                    "Sorry, the selected time slot is no longer "
                    "available. Please select another time."
                )

            except Exception:

                booking_form.add_error(
                    None,
                    "Something went wrong while creating your booking. "
                    "Please try again."
                )

            else:

                # -------------------------------------------------
                # PAYMENT FLOW
                # -------------------------------------------------
                # Booking is created as PENDING.
                # Customer is redirected to payment page.
                # Booking becomes CONFIRMED only after
                # successful Razorpay signature verification.

                return redirect(
                    "payments:payment_page",
                    booking_id=booking_obj.id
                )

    else:

        booking_form = BookingForm()

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
        context
    )


# =========================================================
# ABOUT PAGE
# =========================================================

def about(request):

    return render(
        request,
        "spa/about.html"
    )


# =========================================================
# SERVICES PAGE
# =========================================================

def services(request):

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
        context
    )


# =========================================================
# GALLERY PAGE
# =========================================================

def gallery(request):

    return render(
        request,
        "spa/gallery.html"
    )


# =========================================================
# BOOKING PAGE
# =========================================================

def booking(request):

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
                    "Sorry, this time slot was just booked. "
                    "Please select another available time."
                )

            except Exception:

                booking_form.add_error(
                    None,
                    "Something went wrong while creating your booking. "
                    "Please try again."
                )

            else:

                # -------------------------------------------------
                # PAYMENT FLOW
                # -------------------------------------------------
                # Booking is currently PENDING.
                # Send customer to payment page.
                # Do NOT mark booking confirmed here.

                return redirect(
                    "payments:payment_page",
                    booking_id=booking_obj.id
                )

    else:

        booking_form = BookingForm()

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
        context
    )


# =========================================================
# CREATE BOOKING WITH STAFF + ROOM
# =========================================================

class BookingUnavailableError(Exception):
    """
    Raised when the selected booking slot is no longer available.
    """
    pass


@transaction.atomic
def create_booking_with_resources(form):
    """
    Final server-side booking validation.

    Customer provides:
        service
        duration
        date
        time

    Server automatically chooses:
        staff
        room

    The customer can never control staff or room assignment.

    Booking is created with:
        status = pending

    It will become:
        status = confirmed

    only after successful Razorpay payment verification.
    """

    cleaned_data = form.cleaned_data

    service = cleaned_data.get("service")
    appointment_date = cleaned_data.get("appointment_date")
    appointment_time = cleaned_data.get("appointment_time")
    duration = cleaned_data.get("duration")

    # -----------------------------------------------------
    # BASIC VALIDATION
    # -----------------------------------------------------

    if not service:
        raise BookingUnavailableError()

    if not appointment_date:
        raise BookingUnavailableError()

    if not appointment_time:
        raise BookingUnavailableError()

    if not duration or duration <= 0:
        raise BookingUnavailableError()

    # -----------------------------------------------------
    # PREVENT PAST DATES
    # -----------------------------------------------------

    if appointment_date < date.today():
        raise BookingUnavailableError()

    # -----------------------------------------------------
    # VALIDATE SERVICE IS STILL ACTIVE
    # -----------------------------------------------------

    service = (
        Service.objects
        .select_for_update()
        .filter(
            id=service.id,
            is_active=True
        )
        .first()
    )

    if not service:
        raise BookingUnavailableError()

    # -----------------------------------------------------
    # VALIDATE DURATION AGAINST SERVICE OPTIONS
    # -----------------------------------------------------

    active_options = list(
        ServiceOption.objects.filter(
            service=service,
            is_active=True
        ).order_by("duration")
    )

    if active_options:

        valid_durations = {
            option.duration
            for option in active_options
        }

        if duration not in valid_durations:
            raise BookingUnavailableError()

        selected_option = next(
            option
            for option in active_options
            if option.duration == duration
        )

        selected_price = selected_option.price

    else:

        # If service has no ServiceOption records,
        # use the main service duration and price.

        if duration != service.duration:
            raise BookingUnavailableError()

        selected_price = service.price

    # -----------------------------------------------------
    # CALCULATE END TIME
    # -----------------------------------------------------

    end_time = calculate_end_time(
        appointment_time,
        duration
    )

    # -----------------------------------------------------
    # FIND AVAILABLE STAFF
    # -----------------------------------------------------

    staff_members = (
        Staff.objects
        .select_for_update()
        .filter(is_active=True)
        .order_by("id")
    )

    selected_staff = None

    for staff in staff_members:

        if is_staff_on_leave(
            staff,
            appointment_date
        ):
            continue

        if is_staff_booked(
            staff,
            appointment_date,
            appointment_time,
            end_time
        ):
            continue

        selected_staff = staff
        break

    # -----------------------------------------------------
    # NO STAFF AVAILABLE
    # -----------------------------------------------------

    if not selected_staff:

        raise BookingUnavailableError()

    # -----------------------------------------------------
    # FIND AVAILABLE ROOM
    # -----------------------------------------------------

    rooms = (
        Room.objects
        .select_for_update()
        .filter(is_active=True)
        .order_by("id")
    )

    selected_room = None

    for room in rooms:

        if is_room_booked(
            room,
            appointment_date,
            appointment_time,
            end_time
        ):
            continue

        selected_room = room
        break

    # -----------------------------------------------------
    # NO ROOM AVAILABLE
    # -----------------------------------------------------

    if not selected_room:

        raise BookingUnavailableError()

    # -----------------------------------------------------
    # FINAL AVAILABILITY CHECK
    # -----------------------------------------------------

    # Staff can theoretically become unavailable during
    # concurrent requests, so perform one final check.

    if is_staff_booked(
        selected_staff,
        appointment_date,
        appointment_time,
        end_time
    ):
        raise BookingUnavailableError()

    if is_room_booked(
        selected_room,
        appointment_date,
        appointment_time,
        end_time
    ):
        raise BookingUnavailableError()

    # -----------------------------------------------------
    # CREATE BOOKING
    # -----------------------------------------------------

    booking = form.save(commit=False)

    booking.service = service

    booking.selected_duration = duration

    booking.selected_price = selected_price

    booking.appointment_date = appointment_date

    booking.appointment_time = appointment_time

    booking.end_time = end_time

    booking.staff = selected_staff

    booking.room = selected_room

    # -----------------------------------------------------
    # IMPORTANT:
    # Booking is NOT confirmed yet.
    # Payment must be completed first.
    # -----------------------------------------------------

    booking.status = "pending"

    booking.whatsapp_sent = False

    booking.whatsapp_last_status = None

    booking.save()

    return booking


# =========================================================
# CONTACT PAGE
# =========================================================

def contact(request):

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        phone = request.POST.get(
            "phone",
            ""
        ).strip()

        email = request.POST.get(
            "email",
            ""
        ).strip()

        subject = request.POST.get(
            "subject",
            ""
        ).strip()

        message = request.POST.get(
            "message",
            ""
        ).strip()

        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not name or not phone or not subject or not message:

            messages.error(
                request,
                "Please fill in all required fields."
            )

            return redirect("contact")

        # -------------------------------------------------
        # SUCCESS
        # -------------------------------------------------

        messages.success(
            request,
            f"Thank you {name}! Your message has been received. "
            "Our team will contact you shortly."
        )

        return redirect("contact")

    return render(
        request,
        "spa/contact.html"
    )


# =========================================================
# AVAILABLE BOOKING SLOTS API
# =========================================================

def available_slots(request):
    """
    API endpoint:

    /api/available-slots/

    Parameters:

        service
        date
        duration

    Example:

        /api/available-slots/?service=1&date=2026-09-10&duration=60
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
            status=400
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
            status=400
        )

    # =====================================================
    # GET ACTIVE SERVICE
    # =====================================================

    service = get_object_or_404(
        Service,
        id=service_id,
        is_active=True,
    )

    # =====================================================
    # DATE VALIDATION
    # =====================================================

    if not date_value:

        return JsonResponse(
            {
                "success": False,
                "message": "Date is required.",
                "slots": [],
            },
            status=400
        )

    try:

        appointment_date = datetime.strptime(
            date_value,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        return JsonResponse(
            {
                "success": False,
                "message": "Invalid date format. "
                           "Use YYYY-MM-DD.",
                "slots": [],
            },
            status=400
        )

    # =====================================================
    # PREVENT PAST DATE
    # =====================================================

    if appointment_date < date.today():

        return JsonResponse(
            {
                "success": False,
                "message": "Past dates are not available.",
                "slots": [],
            },
            status=400
        )

    # =====================================================
    # DURATION
    # =====================================================

    try:

        if duration_value:

            duration = int(
                duration_value
            )

        else:

            duration = service.duration

    except (TypeError, ValueError):

        return JsonResponse(
            {
                "success": False,
                "message": "Invalid duration.",
                "slots": [],
            },
            status=400
        )

    # =====================================================
    # DURATION VALIDATION
    # =====================================================

    if duration <= 0:

        return JsonResponse(
            {
                "success": False,
                "message": "Duration must be greater than zero.",
                "slots": [],
            },
            status=400
        )

    # =====================================================
    # VALIDATE DURATION AGAINST SERVICE
    # =====================================================

    active_options = list(
        ServiceOption.objects.filter(
            service=service,
            is_active=True
        ).values_list(
            "duration",
            flat=True
        )
    )

    if active_options:

        if duration not in active_options:

            return JsonResponse(
                {
                    "success": False,
                    "message": "Selected duration is not "
                               "available for this service.",
                    "slots": [],
                },
                status=400
            )

    else:

        if duration != service.duration:

            return JsonResponse(
                {
                    "success": False,
                    "message": "Invalid service duration.",
                    "slots": [],
                },
                status=400
            )

    # =====================================================
    # GET AVAILABLE SLOTS
    # =====================================================

    slots = get_available_slots(
        appointment_date,
        duration
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

                # Only counts are exposed.
                # Staff/room names remain private.

                "available_staff": len(
                    slot["staff"]
                ),

                "available_rooms": len(
                    slot["rooms"]
                ),
            }
        )

    # =====================================================
    # RESPONSE
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