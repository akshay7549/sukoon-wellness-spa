"""Lead follow-ups and the reception customer timeline."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class FollowUpTask(models.Model):
    lead = models.ForeignKey("spa.Enquiry", on_delete=models.PROTECT, null=True, blank=True, related_name="tasks")
    contact = models.ForeignKey("spa.CustomerRecord", on_delete=models.PROTECT, related_name="tasks")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="crm_tasks")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, max_length=4000)
    kind = models.CharField(max_length=12, choices=[("call", "Call"), ("message", "Message"), ("meeting", "Meeting"), ("other", "Other")], default="call")
    priority = models.CharField(max_length=10, choices=[("normal", "Normal"), ("high", "High")], default="normal")
    due_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=12, choices=[("pending", "Pending"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="pending", db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="completed_crm_tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_crm_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_at", "pk"]

    def clean(self):
        if self.assigned_to_id and (not self.assigned_to.is_active or not self.assigned_to.is_staff):
            raise ValidationError({"assigned_to": "Choose an active staff member."})
        if self.lead_id and self.contact_id and self.lead.phone != self.contact.phone:
            raise ValidationError("The task customer must match its enquiry.")

    @property
    def overdue(self):
        return self.status == "pending" and self.due_at < timezone.now()

    def __str__(self):
        return self.title


class CRMActivity(models.Model):
    contact = models.ForeignKey("spa.CustomerRecord", on_delete=models.PROTECT, related_name="activities")
    lead = models.ForeignKey("spa.Enquiry", on_delete=models.SET_NULL, null=True, blank=True, related_name="activities")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=15, choices=[("note", "Note"), ("call", "Call"), ("email", "Email"), ("whatsapp", "WhatsApp"), ("meeting", "Meeting"), ("stage", "Lead update"), ("task", "Task update"), ("account_link", "Account linked")], default="note")
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
