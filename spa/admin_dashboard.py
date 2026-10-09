from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum, F
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .models import Booking, Room, Service, Staff, Enquiry


def month_start(offset, today):
    year, month = divmod(today.year * 12 + today.month - 1 + offset, 12)
    return date(year, month + 1, 1)


@never_cache
@staff_member_required(login_url="sukoon_admin:login")
@permission_required("spa.view_booking", raise_exception=True)
def admin_dashboard(request):
    today = timezone.localdate()
    period = request.GET.get("period", "month")
    if period not in ("today", "week", "month", "all"):
        period = "month"
    bounds = {
        "today": (today, today + timedelta(days=1)),
        "week": (today - timedelta(days=today.weekday()), today - timedelta(days=today.weekday()) + timedelta(days=7)),
        "month": (month_start(0, today), month_start(1, today)),
    }
    labels = {"today": "Today", "week": "This week", "month": "This month", "all": "All time"}
    bookings = Booking.objects.select_related("service", "staff", "room", "customer")
    selected = bookings
    if period in bounds:
        start, end = bounds[period]
        selected = selected.filter(appointment_date__gte=start, appointment_date__lt=end)

    stats = selected.aggregate(
        total=Count("pk"),
        confirmed=Count("pk", filter=Q(status="confirmed")),
        completed=Count("pk", filter=Q(status="completed")),
        cancelled=Count("pk", filter=Q(status="cancelled")),
        completed_value=Sum(F("selected_price") - F("discount_amount"), filter=Q(status="completed"), default=Decimal("0.00")),
        missing_prices=Count("pk", filter=Q(status="completed", selected_price__isnull=True)),
    )
    total = stats["total"]
    status_rows = [
        {"label": label, "status": status, "count": stats[status],
         "percent": round(stats[status] * 100 / total, 1) if total else 0}
        for status, label in Booking.STATUS_CHOICES
    ]
    today_bookings = bookings.filter(appointment_date=today)
    today_counts = today_bookings.aggregate(
        total=Count("pk"), confirmed=Count("pk", filter=Q(status="confirmed")),
        completed=Count("pk", filter=Q(status="completed")),
        cancelled=Count("pk", filter=Q(status="cancelled")),
    )
    performance = list(selected.values("service_id", "service__name").annotate(
        total=Count("pk"), completed=Count("pk", filter=Q(status="completed")),
        value=Sum(F("selected_price") - F("discount_amount"), filter=Q(status="completed"), default=Decimal("0.00")),
    ).order_by("-total", "service__name")[:6])
    for item in performance:
        item["name"] = item["service__name"] or "Archived treatment"
        item["completion_rate"] = round(item["completed"] * 100 / item["total"], 1)

    trend_query = bookings.filter(
        appointment_date__gte=month_start(-5, today),
        appointment_date__lt=month_start(1, today),
    ).annotate(month=TruncMonth("appointment_date")).values("month").annotate(total=Count("pk"))
    trend_counts = {(row["month"].year, row["month"].month): row["total"] for row in trend_query}
    trend = []
    for offset in range(-5, 1):
        month = month_start(offset, today)
        trend.append({"label": month.strftime("%b"), "full_label": month.strftime("%B %Y"),
                      "count": trend_counts.get((month.year, month.month), 0)})
    maximum = max((row["count"] for row in trend), default=0)
    for row in trend:
        row["height"] = round(row["count"] * 100 / maximum, 2) if maximum else 0

    search = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    if status not in dict(Booking.STATUS_CHOICES):
        status = ""
    table = selected
    if search:
        table = table.filter(Q(name__icontains=search) | Q(phone__icontains=search) |
                             Q(email__icontains=search) | Q(service__name__icontains=search))
    if status:
        table = table.filter(status=status)
    page = Paginator(table.order_by("-appointment_date", "-appointment_time", "-pk"), 12).get_page(request.GET.get("page"))
    page_params = request.GET.copy()
    page_params.pop("page", None)
    page_params["period"] = period

    active_staff = Staff.objects.filter(is_active=True).count()
    active_rooms = Room.objects.filter(is_active=True).count()
    staff_activity = list(selected.exclude(staff__isnull=True).values("staff__name").annotate(
        total=Count("pk"), completed=Count("pk", filter=Q(status="completed")),
    ).order_by("-total", "staff__name")[:5])
    recent_customers = get_user_model().objects.filter(is_staff=False, is_superuser=False, is_active=True)
    whatsapp_counts = selected.aggregate(
        sent=Count("pk", filter=Q(whatsapp_sent=True)),
        pending=Count("pk", filter=Q(whatsapp_sent=False)),
    )
    context = {
        "new_enquiries": Enquiry.objects.filter(status="new").count(),
        "today": today, "period": period, "period_label": labels[period],
        "total_bookings": total, "confirmed_bookings": stats["confirmed"],
        "completed_bookings": stats["completed"], "cancelled_bookings": stats["cancelled"],
        "completed_value": stats["completed_value"], "missing_prices": stats["missing_prices"],
        "completion_rate": round(stats["completed"] * 100 / total, 1) if total else 0,
        "today_bookings": today_counts["total"], "today_confirmed": today_counts["confirmed"],
        "today_completed": today_counts["completed"], "today_cancelled": today_counts["cancelled"],
        "today_appointments": today_bookings.order_by("appointment_time")[:6],
        "upcoming_appointments": bookings.filter(
            appointment_date__gte=today, status="confirmed",
        ).order_by("appointment_date", "appointment_time")[:5],
        "performance": performance, "trend": trend, "status_rows": status_rows,
        "booking_page": page, "search": search, "status_filter": status,
        "page_query": page_params.urlencode(),
        "active_services": Service.objects.filter(is_active=True).count(),
        "active_staff": active_staff, "active_rooms": active_rooms,
        "rooms_scheduled": today_bookings.filter(status="confirmed").exclude(room__isnull=True).values("room_id").distinct().count(),
        "staff_activity": staff_activity, "customer_accounts": recent_customers.count(),
        "recent_customers": recent_customers.order_by("-date_joined")[:5],
        "whatsapp_sent": whatsapp_counts["sent"], "whatsapp_pending": whatsapp_counts["pending"],
    }
    context["can_view_analytics"] = request.user.has_perm("spa.view_business_analytics")
    if not context["can_view_analytics"]:
        context["completed_value"] = None
        for item in context["performance"]:
            item["value"] = None
    return render(request, "admin/crm_dashboard.html", context)
