from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render

from .models import Booking


# =========================================================
# BOOKING BILL / RECEIPT
# =========================================================

@staff_member_required
def booking_bill(request, booking_id):
    """
    Display a printable booking bill/receipt.

    This is only a booking document.
    No payment gateway or payment transaction is used.
    """

    # =====================================================
    # GET BOOKING
    # =====================================================

    booking = get_object_or_404(
        Booking.objects.select_related(
            "service",
            "staff",
            "room",
        ),
        pk=booking_id,
    )

    # =====================================================
    # SERVICE
    # =====================================================

    service_name = "Service"

    if booking.service:
        service_name = booking.service.name

    # =====================================================
    # DURATION
    # =====================================================

    duration = booking.selected_duration

    if duration is None and booking.service:
        duration = booking.service.duration

    # =====================================================
    # PRICE
    # =====================================================
    #
    # This is the service price only.
    # It is NOT a payment transaction amount.
    #

    price = booking.selected_price

    if price is None and booking.service:
        price = booking.service.price

    # =====================================================
    # BOOKING STATUS
    # =====================================================

    booking_status = booking.status or "confirmed"

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {
        "booking": booking,

        "service_name": service_name,

        "duration": duration,

        "price": price,

        "booking_status": booking_status,
    }

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "admin/bill.html",
        context,
    )