from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from .models import (
    Booking,
    Service,
    Staff,
    Room,
)

from payments.models import Payment


# =========================================================
# CRM ADMIN DASHBOARD
# =========================================================

@staff_member_required
def admin_dashboard(request):

    today = timezone.localdate()

    # =====================================================
    # BOOKING QUERYSETS
    # =====================================================

    booking_queryset = (
        Booking.objects
        .select_related(
            "service",
            "staff",
            "room",
        )
        .order_by(
            "-appointment_date",
            "-appointment_time",
            "-created_at",
        )
    )

    # =====================================================
    # ALL BOOKINGS
    # =====================================================

    all_bookings = booking_queryset

    # =====================================================
    # TODAY'S BOOKINGS
    # =====================================================

    today_appointments = (
        booking_queryset
        .filter(
            appointment_date=today
        )
        .order_by(
            "appointment_time"
        )
    )

    # =====================================================
    # UPCOMING APPOINTMENTS
    # =====================================================

    upcoming_appointments = (
        booking_queryset
        .filter(
            appointment_date__gte=today,
            status__in=[
                "pending",
                "confirmed",
            ],
        )
        .order_by(
            "appointment_date",
            "appointment_time",
        )[:20]
    )

    # =====================================================
    # RECENT BOOKINGS
    # =====================================================

    recent_bookings = (
        booking_queryset
        .order_by(
            "-created_at"
        )[:15]
    )

    # =====================================================
    # BOOKING COUNTS
    # =====================================================

    total_bookings = Booking.objects.count()

    today_bookings = Booking.objects.filter(
        appointment_date=today
    ).count()

    pending_bookings = Booking.objects.filter(
        status="pending"
    ).count()

    confirmed_bookings = Booking.objects.filter(
        status="confirmed"
    ).count()

    completed_bookings = Booking.objects.filter(
        status="completed"
    ).count()

    cancelled_bookings = Booking.objects.filter(
        status="cancelled"
    ).count()

    # =====================================================
    # PAYMENT QUERYSET
    # =====================================================

    all_payments = (
        Payment.objects
        .select_related("booking")
        .order_by(
            "-created_at"
        )
    )

    # =====================================================
    # PAYMENT COUNTS
    # =====================================================

    paid_payments = Payment.objects.filter(
        status="paid"
    ).count()

    pending_payments = Payment.objects.filter(
        status__in=[
            "created",
            "pending",
        ]
    ).count()

    failed_payments = Payment.objects.filter(
        status="failed"
    ).count()

    refunded_payments = Payment.objects.filter(
        status="refunded"
    ).count()

    # =====================================================
    # REVENUE
    # =====================================================

    revenue = (
        Payment.objects
        .filter(
            status="paid"
        )
        .aggregate(
            total=Sum("amount")
        )
        .get("total")
        or Decimal("0.00")
    )

    # =====================================================
    # BUSINESS COUNTS
    # =====================================================

    active_services = Service.objects.filter(
        is_active=True
    ).count()

    active_staff = Staff.objects.filter(
        is_active=True
    ).count()

    active_rooms = Room.objects.filter(
        is_active=True
    ).count()

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        "today": today,

        # -------------------------------------------------
        # BOOKING STATISTICS
        # -------------------------------------------------

        "total_bookings": total_bookings,
        "today_bookings": today_bookings,
        "pending_bookings": pending_bookings,
        "confirmed_bookings": confirmed_bookings,
        "completed_bookings": completed_bookings,
        "cancelled_bookings": cancelled_bookings,

        # -------------------------------------------------
        # BOOKING DATA
        # -------------------------------------------------

        "all_bookings": all_bookings,
        "today_appointments": today_appointments,
        "upcoming_appointments": upcoming_appointments,
        "recent_bookings": recent_bookings,

        # -------------------------------------------------
        # PAYMENT STATISTICS
        # -------------------------------------------------

        "paid_payments": paid_payments,
        "pending_payments": pending_payments,
        "failed_payments": failed_payments,
        "refunded_payments": refunded_payments,

        # -------------------------------------------------
        # PAYMENT DATA
        # -------------------------------------------------

        "all_payments": all_payments,

        # -------------------------------------------------
        # REVENUE
        # -------------------------------------------------

        "revenue": revenue,

        # -------------------------------------------------
        # BUSINESS
        # -------------------------------------------------

        "active_services": active_services,
        "active_staff": active_staff,
        "active_rooms": active_rooms,
    }

    # =====================================================
    # RENDER DASHBOARD
    # =====================================================

    return render(
        request,
        "admin/spa_dashboard.html",
        context,
    )