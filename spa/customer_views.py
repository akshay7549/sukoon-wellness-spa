from datetime import datetime, timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .forms import BookingForm
from .models import Booking, Staff, Room
from .services.bookings import save_booking

def can_change(booking):
    start = timezone.make_aware(datetime.combine(booking.appointment_date, booking.appointment_time))
    return booking.status == "confirmed" and start > timezone.now() + timedelta(hours=settings.CUSTOMER_CHANGE_CUTOFF_HOURS)

@never_cache
@login_required
@require_POST
def cancel_booking(request, booking_id):
    with transaction.atomic():
        booking = get_object_or_404(Booking.objects.select_for_update(), pk=booking_id, customer=request.user)
        if not can_change(booking):
            messages.error(request, "Online changes close 2 hours before the appointment. Please contact reception.")
        else:
            booking.status = "cancelled"
            booking.save(update_fields=["status","updated_at"])
            from .notifications import queue_booking_notifications
            queue_booking_notifications(booking, "cancelled")
            messages.success(request, "Your appointment has been cancelled. Contact reception regarding any amount already paid.")
    return redirect("my_bookings")

@never_cache
@login_required
def reschedule_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    if not can_change(booking):
        messages.error(request, "Online changes close 2 hours before the appointment. Please contact reception.")
        return redirect("my_bookings")
    form = BookingForm(request.POST if request.method=="POST" else None, instance=booking, initial={"duration":booking.selected_duration})
    if request.method=="POST" and form.is_valid():
        try:
            with transaction.atomic():
                list(Staff.objects.select_for_update().order_by("pk"))
                list(Room.objects.select_for_update().order_by("pk"))
                locked = get_object_or_404(Booking.objects.select_for_update(), pk=booking_id, customer=request.user)
                if not can_change(locked):
                    raise ValidationError("The appointment can no longer be changed online.")
                if form.cleaned_data["service"].pk != locked.service_id or form.cleaned_data["duration"] != locked.selected_duration:
                    raise ValidationError("Rescheduling keeps the booked treatment and duration. Book a new appointment to change treatment.")
                save_booking(form, request.user)
            messages.success(request, "Your appointment has been rescheduled.")
            return redirect("my_bookings")
        except ValidationError as exc:
            form.add_error(None, exc)
    from .models import Service
    return render(request,"spa/booking.html",{"booking_form":form,"services":Service.objects.filter(pk=booking.service_id).prefetch_related("options"),"rescheduling":True,"reschedule_booking_id":booking.pk})
