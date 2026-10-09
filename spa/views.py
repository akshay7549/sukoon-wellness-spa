
from datetime import datetime

import logging
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BookingForm
from .account_views import booking_initial, remember_guest_booking
from .services.presentation import add_service_covers
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

    The homepage also supports booking POST requests.

    Booking rules:
        - No payment required
        - No admin approval required
        - Booking is immediately confirmed
        - Staff and room are automatically assigned
    """

    if request.method == "POST":

        booking_form = BookingForm(
            request.POST
        )

        if booking_form.is_valid():

            try:

                booking_obj = create_booking_with_resources(
                    booking_form,
                    customer=request.user if request.user.is_authenticated else None,
                )

                remember_guest_booking(request, booking_obj)

            except BookingUnavailableError as exc:

                booking_form.add_error(
                    None,
                    str(exc),
                )

            except Exception:
                logging.getLogger(__name__).exception("Booking creation failed")

                booking_form.add_error(
                    None,
                    (
                        "Something went wrong while creating "
                        "your booking. Please try again."
                    ),
                )

        else:

            # Form validation errors are already attached
            # to the form.

            pass

        if (
            booking_form.is_valid()
            and "booking_obj" in locals()
        ):

            return redirect(
                "booking_success",
                booking_id=booking_obj.id,
            )

    else:

        booking_form = BookingForm(initial=booking_initial(request))

    # =====================================================
    # ACTIVE SERVICES
    # =====================================================

    services = (
        Service.objects
        .filter(
            is_active=True, options__is_active=True,
        ).distinct()
        .select_related(
            "category",
        )
        .prefetch_related(
            "options",
        )
    )

    featured_services = add_service_covers(list(services.filter(
        is_featured=True,
    )))

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
    treatments = add_service_covers(list(Service.objects.filter(is_active=True).select_related("category").prefetch_related("options")))
    for service in treatments:
        service.bookable = any(o.is_active for o in service.options.all())
    return render(request,"spa/services.html",{"services":treatments})


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
# FRANCHISE PAGE
# =========================================================

def franchise(request):
    return enquiry_page(request, "franchise")


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
        - Automatic staff assignment
        - Automatic room assignment
    """

    if request.method == "POST":

        booking_form = BookingForm(
            request.POST
        )

        if booking_form.is_valid():

            try:

                booking_obj = create_booking_with_resources(
                    booking_form,
                    customer=request.user if request.user.is_authenticated else None,
                )

                remember_guest_booking(request, booking_obj)

            except BookingUnavailableError as exc:

                booking_form.add_error(
                    None,
                    str(exc),
                )

            except Exception:
                logging.getLogger(__name__).exception("Booking creation failed")

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

        booking_form = BookingForm(initial=booking_initial(request))

    # =====================================================
    # ACTIVE SERVICES
    # =====================================================

    services = (
        Service.objects
        .filter(
            is_active=True, options__is_active=True,
        ).distinct()
        .select_related(
            "category",
        )
        .prefetch_related(
            "options",
        )
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

    bookings = Booking.objects.select_related(
            "service",
            "staff",
            "room",
        )
    if not (request.user.is_authenticated and request.user.is_staff and request.user.has_perm("spa.view_booking")):
        owned = Q(pk__in=request.session.get("guest_booking_ids", []), customer__isnull=True)
        if request.user.is_authenticated:
            owned |= Q(customer=request.user)
        bookings = bookings.filter(owned)

    booking_obj = get_object_or_404(
        bookings,
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

def create_booking_with_resources(form, customer=None):
    from django.core.exceptions import ValidationError
    from .services.bookings import save_booking
    try:
        return save_booking(form, customer)
    except ValidationError as exc:
        raise BookingUnavailableError(" ".join(exc.messages)) from exc


# =========================================================
# CONTACT PAGE
# =========================================================

def enquiry_page(request, kind):
    from .enquiry_forms import EnquiryForm
    form = EnquiryForm(request.POST if request.method == "POST" else None, kind=kind)
    if request.method == "POST" and form.is_valid():
        enquiry = form.save(commit=False)
        enquiry.kind = kind
        enquiry.save()
        from .notifications import queue_enquiry_notification
        queue_enquiry_notification(enquiry)
        messages.success(request, "Thank you! Your enquiry has been saved. Our reception team will follow up.")
        return redirect(kind)
    return render(request, f"spa/{kind}.html", {"enquiry_form": form})

def contact(request):
    return enquiry_page(request, "contact")


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

    The API validates that the duration belongs to the
    selected service.

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

    except (
        TypeError,
        ValueError,
    ):

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
                "message": (
                    "Selected service is not available."
                ),
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

    except (
        TypeError,
        ValueError,
    ):

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
                "message": (
                    "Past dates are not available."
                ),
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # DURATION IS REQUIRED
    #
    # There is NO fallback to Service.duration.
    # =====================================================

    if not duration_value:

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Duration is required."
                ),
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # DURATION PARSING
    # =====================================================

    try:

        duration = int(
            duration_value
        )

    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "success": False,
                "message": "Invalid duration.",
                "slots": [],
            },
            status=400,
        )

    # =====================================================
    # BASIC DURATION VALIDATION
    # =====================================================

    if duration <= 0:

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
    # VALIDATE SERVICE OPTION
    #
    # ServiceOption is the single source of truth.
    # =====================================================

    selected_option = (
        ServiceOption.objects
        .filter(
            service=service,
            duration=duration,
            is_active=True,
        )
        .first()
    )

    if not selected_option:

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

    # =====================================================
    # GET AVAILABLE SLOTS
    # =====================================================

    try:

        exclude_id = None
        if request.GET.get("booking_id"):
            if not request.GET["booking_id"].isdigit() or len(request.GET["booking_id"]) > 18:
                return JsonResponse({"success":False,"message":"Invalid booking.","slots":[]},status=400)
            if not request.user.is_authenticated:
                return JsonResponse({"success":False,"message":"Sign in required.","slots":[]},status=403)
            owned = get_object_or_404(Booking,pk=request.GET["booking_id"],customer=request.user)
            exclude_id = owned.pk
        slots = get_available_slots(appointment_date, duration, exclude_id)

    except Http404:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Availability calculation failed")

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

        start_time = slot.get(
            "start_time"
        )

        end_time = slot.get(
            "end_time"
        )

        if not start_time or not end_time:

            continue

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

                # -----------------------------------------
                # ONLY COUNTS ARE RETURNED.
                # -----------------------------------------

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

    # =====================================================
    # API RESPONSE
    # =====================================================

    return JsonResponse(
        {
            "success": True,

            "service": service.name,

            "duration": selected_option.duration,

            "price": str(
                selected_option.price
            ),

            "date": date_value,

            "business_hours": {
                "start": "10:00",
                "end": "22:00",
            },

            "slot_interval": 15,

            "slots": response_slots,
        }
    )


def service_options(request):
    value = request.GET.get("service", "")
    if not value.isdigit() or len(value)>18:
        return JsonResponse({"options": [], "message": "Select a treatment."}, status=400)
    service = get_object_or_404(Service, pk=value, is_active=True)
    options = service.options.filter(is_active=True).order_by("duration").values("duration", "price")
    return JsonResponse({"options":[{"duration":o["duration"],"price":str(o["price"])} for o in options]})
