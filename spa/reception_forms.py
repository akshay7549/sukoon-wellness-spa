from django import forms
from django.utils import timezone
from .models import WaitlistEntry, Service, ServiceOption
from .crm_forms import staff_choices
from .services.availability import BUSINESS_START, BUSINESS_END, time_to_minutes


class WaitlistForm(forms.ModelForm):
    class Meta:
        model = WaitlistEntry
        fields = ["contact", "service", "duration", "preferred_date", "earliest_time", "latest_time", "assigned_to", "notes"]
        widgets = {"preferred_date": forms.DateInput(attrs={"type": "date"}), "earliest_time": forms.TimeInput(attrs={"type": "time"}), "latest_time": forms.TimeInput(attrs={"type": "time"}), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.filter(is_active=True, options__is_active=True).distinct()
        self.fields["assigned_to"].queryset = staff_choices()

    def clean(self):
        data = super().clean()
        service, duration = data.get("service"), data.get("duration")
        if service and duration and not ServiceOption.objects.filter(service=service, duration=duration, is_active=True).exists():
            self.add_error("duration", "Choose an active duration from this treatment's rate card.")
        day, earliest, latest = data.get("preferred_date"), data.get("earliest_time"), data.get("latest_time")
        if day and day < timezone.localdate():
            self.add_error("preferred_date", "Choose today or a future date.")
        if earliest and latest and duration:
            if earliest > latest or time_to_minutes(earliest) < BUSINESS_START or time_to_minutes(latest) + duration > BUSINESS_END:
                self.add_error("latest_time", "Choose an ordered time window that fits 10 AM–10 PM, including the treatment duration.")
        return data


class StageForm(forms.Form):
    stage = forms.ChoiceField(choices=[(s, s.replace("_", " ").title()) for s in ("checked_in", "in_service", "completed", "cancelled", "no_show")])
    version = forms.CharField(widget=forms.HiddenInput)
    note = forms.CharField(max_length=1000, required=False)
