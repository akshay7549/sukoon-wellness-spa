from django.contrib.auth.decorators import permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .models import Booking
from .connect_views import ADDRESS, connect_qr_data_uri, connect_url


# =========================================================
# BOOKING BILL / RECEIPT
# =========================================================

@never_cache
@staff_member_required(login_url="sukoon_admin:login")
@permission_required("spa.view_booking", raise_exception=True)
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

    service_name = booking.service_name_snapshot or "Service"

    if not booking.service_name_snapshot and booking.service:
        service_name = booking.service.name

    # =====================================================
    # DURATION
    # =====================================================

    duration = booking.selected_duration

    # =====================================================
    # PRICE
    # =====================================================
    #
    # This is the service price only.
    # It is NOT a payment transaction amount.
    #

    price = booking.selected_price

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
        "generated_at": timezone.now(),
        "business_address": ADDRESS,
        "connect_url": connect_url(),
        "qr_code": connect_qr_data_uri(),
    }

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        request,
        "admin/bill.html",
        context,
    )
