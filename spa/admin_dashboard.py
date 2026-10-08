from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone

from .models import (
    Booking,
    Service,
    Staff,
    Room,
)


# =========================================================
# SUKOON CRM ADMIN DASHBOARD
# =========================================================

@staff_member_required
def admin_dashboard(request):

    # =====================================================
    # CURRENT DATE
    # =====================================================

    today = timezone.localdate()

    # =====================================================
    # BASE BOOKING QUERYSET
    # =====================================================

    booking_queryset = (
        Booking.objects
        .select_related(
            "service",
            "staff",
            "room",
        )
    )

    # =====================================================
    # ALL BOOKINGS
    # Used by the main dashboard booking table
    # =====================================================

    all_bookings = (
        booking_queryset
        .order_by(
            "-appointment_date",
            "-appointment_time",
        )
    )

    # =====================================================
    # TODAY'S APPOINTMENTS
    # =====================================================

    today_appointments = (
        booking_queryset
        .filter(
            appointment_date=today,
        )
        .order_by(
            "appointment_time",
        )
    )

    # =====================================================
    # TODAY'S BOOKING COUNTS
    # =====================================================

    today_confirmed = (
        Booking.objects
        .filter(
            appointment_date=today,
            status="confirmed",
        )
        .count()
    )

    today_completed = (
        Booking.objects
        .filter(
            appointment_date=today,
            status="completed",
        )
        .count()
    )

    today_cancelled = (
        Booking.objects
        .filter(
            appointment_date=today,
            status="cancelled",
        )
        .count()
    )

    # =====================================================
    # UPCOMING APPOINTMENTS
    # =====================================================

    upcoming_appointments = (
        booking_queryset
        .filter(
            appointment_date__gte=today,
            status="confirmed",
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
            "-created_at",
        )[:15]
    )

    # =====================================================
    # BOOKING STATISTICS
    # =====================================================

    total_bookings = (
        Booking.objects.count()
    )

    today_bookings = (
        Booking.objects
        .filter(
            appointment_date=today,
        )
        .count()
    )

    confirmed_bookings = (
        Booking.objects
        .filter(
            status="confirmed",
        )
        .count()
    )

    completed_bookings = (
        Booking.objects
        .filter(
            status="completed",
        )
        .count()
    )

    cancelled_bookings = (
        Booking.objects
        .filter(
            status="cancelled",
        )
        .count()
    )

    # =====================================================
    # BUSINESS STATISTICS
    # =====================================================

    active_services = (
        Service.objects
        .filter(
            is_active=True,
        )
        .count()
    )

    active_staff = (
        Staff.objects
        .filter(
            is_active=True,
        )
        .count()
    )

    active_rooms = (
        Room.objects
        .filter(
            is_active=True,
        )
        .count()
    )

    # =====================================================
    # WHATSAPP STATISTICS
    # =====================================================
    # Payment system has been completely removed.
    # WhatsApp statistics are kept because they belong
    # to booking notifications, not payments.

    whatsapp_sent = (
        Booking.objects
        .filter(
            whatsapp_sent=True,
        )
        .count()
    )

    whatsapp_pending = (
        Booking.objects
        .filter(
            whatsapp_sent=False,
        )
        .count()
    )

    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        "today": today,

        # -------------------------------------------------
        # OVERALL BOOKING STATISTICS
        # -------------------------------------------------

        "total_bookings": total_bookings,
        "today_bookings": today_bookings,
        "confirmed_bookings": confirmed_bookings,
        "completed_bookings": completed_bookings,
        "cancelled_bookings": cancelled_bookings,

        # -------------------------------------------------
        # TODAY'S STATISTICS
        # -------------------------------------------------

        "today_confirmed": today_confirmed,
        "today_completed": today_completed,
        "today_cancelled": today_cancelled,

        # -------------------------------------------------
        # BOOKING DATA
        # -------------------------------------------------

        "all_bookings": all_bookings,
        "today_appointments": today_appointments,
        "upcoming_appointments": upcoming_appointments,
        "recent_bookings": recent_bookings,

        # -------------------------------------------------
        # BUSINESS STATISTICS
        # -------------------------------------------------

        "active_services": active_services,
        "active_staff": active_staff,
        "active_rooms": active_rooms,

        # -------------------------------------------------
        # WHATSAPP
        # -------------------------------------------------

        "whatsapp_sent": whatsapp_sent,
        "whatsapp_pending": whatsapp_pending,
    }

    # =====================================================
    # RENDER DASHBOARD
    # =====================================================

    return render(
        request,
        "admin/spa_dashboard.html",
        context,
    )