from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator


class WaitlistEntry(models.Model):
    contact = models.ForeignKey("spa.CustomerRecord", on_delete=models.PROTECT, related_name="waitlist_entries")
    service = models.ForeignKey("spa.Service", on_delete=models.PROTECT)
    duration = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    preferred_date = models.DateField(db_index=True)
    earliest_time = models.TimeField()
    latest_time = models.TimeField(help_text="Latest acceptable appointment start time.")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=12, choices=[("waiting", "Waiting"), ("contacted", "Contacted"), ("booked", "Booked"), ("cancelled", "Cancelled")], default="waiting", db_index=True)
    booking = models.OneToOneField("spa.Booking", on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["preferred_date", "created_at"]

    def __str__(self):
        return f"{self.contact} · {self.preferred_date}"


class ReceptionEvent(models.Model):
    booking = models.ForeignKey("spa.Booking", on_delete=models.PROTECT, related_name="reception_events")
    stage = models.CharField(max_length=12)
    note = models.CharField(max_length=1000, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def stage_label(self):
        return {"checked_in": "Checked-in", "in_service": "In Service", "completed": "Completed", "cancelled": "Cancelled", "no_show": "No-show"}.get(self.stage, self.stage)

    class Meta:
        ordering = ["-created_at", "-pk"]
