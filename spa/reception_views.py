from datetime import date
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import Booking, Room, WaitlistEntry
from .forms import BookingForm
from .reception_forms import StageForm, WaitlistForm
from .services.reception import move_visit, promote_waitlist
from .services.availability import get_available_slots


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_booking", raise_exception=True)
@require_http_methods(["GET", "POST"])
def day_board(request):
    try: day = date.fromisoformat(request.GET.get("date", ""))
    except ValueError: day = timezone.localdate()
    if request.method == "POST":
        if not request.user.has_perm("spa.change_booking"): raise PermissionDenied
        form = StageForm(request.POST)
        booking_id = request.POST.get("booking", "")
        if not booking_id.isdigit(): raise PermissionDenied
        get_object_or_404(Booking, pk=booking_id)
        if form.is_valid():
            try:
                move_visit(booking_id, actor=request.user, **form.cleaned_data)
                messages.success(request, "Reception stage updated.")
                return redirect(request.get_full_path())
            except ValidationError as exc: form.add_error(None, exc)
        messages.error(request, " ".join(str(e) for errors in form.errors.values() for e in errors))
    visits = list(Booking.objects.filter(appointment_date=day).select_related("service", "staff", "secondary_staff", "room").prefetch_related("reception_events__actor").order_by("appointment_time", "pk"))
    columns = []
    for key, label in [("expected", "Expected"), ("checked_in", "Checked-in"), ("in_service", "In Service"), ("completed", "Completed"), ("no_show", "No-show"), ("cancelled", "Cancelled")]:
        cards = [b for b in visits if b.day_stage == key]
        for booking in cards:
            booking.day_actions = [("checked_in", "Check in")] if key == "expected" else [("in_service", "Start service")] if key == "checked_in" else [("completed", "Complete visit")] if key == "in_service" else []
            if key == "expected": booking.day_actions.append(("no_show", "Mark no-show"))
            if key in ("expected", "checked_in", "in_service"): booking.day_actions.append(("cancelled", "Cancel visit"))
        columns.append({"key": key, "label": label, "visits": cards})
    now = timezone.now()
    rooms = list(Room.objects.filter(is_active=True))
    for room in rooms: room.cleaning = bool(room.cleaning_until and room.cleaning_until > now)
    return render(request, "admin/day_board.html", {"day": day, "today": timezone.localdate(), "columns": columns, "total": len(visits), "rooms": rooms})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_waitlistentry", raise_exception=True)
def waitlist(request):
    entries = WaitlistEntry.objects.select_related("contact", "service", "assigned_to", "booking")
    status = request.GET.get("status", "waiting")
    if status in ("waiting", "contacted", "booked", "cancelled"): entries = entries.filter(status=status)
    else: status = "all"
    page = Paginator(entries, 25).get_page(request.GET.get("page"))
    for entry in page:
        entry.available = any(entry.earliest_time <= s["start_time"] <= entry.latest_time for s in get_available_slots(entry.preferred_date, entry.duration, service=entry.service)) if entry.status in ("waiting", "contacted") else False
    return render(request, "admin/waitlist.html", {"page": page, "status": status})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.add_waitlistentry", raise_exception=True)
@require_http_methods(["GET", "POST"])
def waitlist_new(request):
    form = WaitlistForm(request.POST if request.method == "POST" else None, initial={"assigned_to": request.user, "preferred_date": timezone.localdate(), "earliest_time": "10:00", "latest_time": "20:00"})
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Customer added to the waitlist. No message has been sent.")
        return redirect("reception_waitlist")
    return render(request, "admin/workflow_form.html", {"form": form, "heading": "Add to Waitlist", "intro": "Record the requested treatment, duration and acceptable start times.", "submit": "Add to waitlist"})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.change_waitlistentry", raise_exception=True)
@require_http_methods(["GET", "POST"])
def waitlist_book(request, entry_id):
    entry = get_object_or_404(WaitlistEntry.objects.select_related("contact", "service"), pk=entry_id)
    slots = [s for s in get_available_slots(entry.preferred_date, entry.duration, service=entry.service) if entry.earliest_time <= s["start_time"] <= entry.latest_time]
    initial = {"name": entry.contact.name, "phone": entry.contact.phone, "service": entry.service_id, "duration": entry.duration, "appointment_date": entry.preferred_date, "appointment_time": slots[0]["start_time"] if slots else entry.earliest_time}
    form = BookingForm(request.POST if request.method == "POST" else None, initial=initial, customer_user=entry.contact.account)
    # The waitlist fixes treatment and identity; reception chooses an available time.
    for field in ("phone", "service", "duration", "appointment_date"): form.fields[field].disabled = True
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("contacted", "cancelled"):
            with transaction.atomic():
                locked = WaitlistEntry.objects.select_for_update().get(pk=entry.pk)
                if locked.updated_at.isoformat() == request.POST.get("version") and locked.status in ("waiting", "contacted"):
                    locked.status = action; locked.save(); messages.success(request, "Waitlist status updated.")
                    return redirect("reception_waitlist")
                form.add_error(None, "This entry changed. Reload it.")
        elif action == "book":
            if not request.user.has_perm("spa.add_booking"): raise PermissionDenied
            if form.is_valid():
                try:
                    booking = promote_waitlist(entry.pk, form, request.POST.get("version"))
                    messages.success(request, f"Booking #{booking.pk} created with reserved therapist and room.")
                    return redirect("reception_day_board")
                except ValidationError as exc: form.add_error(None, exc)
        else: raise PermissionDenied
    return render(request, "admin/waitlist_book.html", {"entry": entry, "form": form, "slots": slots})
