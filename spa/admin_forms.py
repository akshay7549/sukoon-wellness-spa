from types import SimpleNamespace
from django import forms
from django.db.models import Q
from .forms import BookingForm
from .models import Booking, Service
from .services.availability import calculate_end_time, day_resources, free_resources

class AdminBookingForm(BookingForm):
    class Meta(BookingForm.Meta):
        fields = ["customer", "name", "phone", "email", "service", "duration", "appointment_date", "appointment_time", "staff", "room", "message", "status", "discount_amount", "amount_paid", "payment_mode", "payment_reference"]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["service"].queryset = Service.objects.filter(Q(is_active=True, options__is_active=True) | Q(pk=self.instance.service_id)).distinct()
            duration = self.instance.selected_duration
            if duration:
                choices = list(self.fields["duration"].choices)
                if duration not in {x[0] for x in choices}:
                    choices.append((duration, f"{duration} minutes (recorded session)"))
                self.fields["duration"].choices = choices
                self.initial["duration"] = duration
    def clean_service(self):
        service = self.cleaned_data.get("service")
        if self.instance.pk and service and service.pk == self.instance.service_id:
            return service
        return super().clean_service()
    def clean_duration(self):
        d = self.cleaned_data.get("duration")
        service = self.cleaned_data.get("service")
        if self.instance.pk and service and service.pk == self.instance.service_id and d == self.instance.selected_duration:
            return d
        return super().clean_duration()
    def clean(self):
        same = self.instance.pk and self.cleaned_data.get("service") == self.instance.service and self.cleaned_data.get("duration") == self.instance.selected_duration
        if same:
            data = forms.ModelForm.clean(self)
            if data.get("appointment_time") and data.get("duration"):
                data["_calculated_end_time"] = calculate_end_time(data["appointment_time"], data["duration"])
                data["_selected_option"] = SimpleNamespace(price=self.instance.selected_price, duration=data["duration"])
        else:
            data = super().clean()
        needed = [data.get(k) for k in ("service", "duration", "appointment_date", "appointment_time")]
        if all(needed):
            from .services.availability import appointment_is_past, is_within_business_hours
            end = calculate_end_time(data["appointment_time"], data["duration"])
            unchanged = self.instance.pk and data["appointment_date"] == self.instance.appointment_date and data["appointment_time"] == self.instance.appointment_time and data.get("status") == self.instance.status
            if not unchanged and appointment_is_past(data["appointment_date"], data["appointment_time"]):
                raise forms.ValidationError("Choose a future appointment time.")
            if not is_within_business_hours(data["appointment_time"], end):
                raise forms.ValidationError("Appointment must fit between 10 AM and 10 PM.")
            if data.get("status") == "confirmed":
                staff, rooms = free_resources(day_resources(data["appointment_date"], self.instance.pk), data["appointment_time"], end)
                if not staff or not rooms:
                    raise forms.ValidationError("No therapist or room is available.")
                if data.get("staff") and data["staff"].pk not in {s.pk for s in staff}:
                    self.add_error("staff", "Therapist is unavailable or on leave.")
                if data.get("room") and data["room"].pk not in {r.pk for r in rooms}:
                    self.add_error("room", "Room is unavailable.")
            option = data.get("_selected_option")
            if option:
                self.instance.selected_price = option.price
        return data
