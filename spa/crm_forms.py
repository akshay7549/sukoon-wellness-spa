from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Enquiry, FollowUpTask, CustomerRecord, Booking
from .forms import BookingForm

OPEN_STAGES = {"new", "contacted", "interested", "booked", "qualification", "meeting", "proposal", "agreement"}
DATE_WIDGET = forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})


def staff_choices():
    return get_user_model().objects.filter(is_active=True, is_staff=True).order_by("first_name", "username")


class LeadForm(forms.ModelForm):
    phone = forms.CharField(max_length=10, validators=[BookingForm.phone_validator])
    message = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 3}))
    staff_notes = forms.CharField(max_length=4000, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    next_action = forms.CharField(max_length=150, required=False)
    next_follow_up = forms.DateTimeField(required=False, widget=DATE_WIDGET)
    version = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Enquiry
        fields = ["name", "phone", "email", "kind", "source", "subject", "message", "city", "investment_range", "franchise_model", "status", "assigned_to", "linked_booking", "lost_reason", "staff_notes"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3}), "staff_notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = staff_choices()
        self.fields["assigned_to"].required = True
        self.fields["assigned_to"].label = "Lead owner"
        if self.instance.pk:
            self.fields["version"].initial = self.instance.updated_at.isoformat()
            self.fields["phone"].disabled = True
            self.fields["kind"].disabled = True
            task = self.instance.next_task
            if task and task.status == "pending":
                self.fields["next_action"].initial = task.title
                self.fields["next_follow_up"].initial = timezone.localtime(task.due_at).replace(second=0, microsecond=0)
        kind = self.instance.kind or self.data.get("kind") or self.initial.get("kind", "contact")
        self.fields["status"].choices = Enquiry.FRANCHISE_STAGES if kind == "franchise" else [(k, v) for k, v in Enquiry.CONTACT_STAGES if k != "closed" or self.instance.status == "closed"]
        phone = self.instance.phone or (self.data.get("phone", "") if self.is_bound else "")
        self.fields["linked_booking"].queryset = Booking.objects.filter(phone=phone).order_by("-appointment_date") if phone else Booking.objects.none()
        self.fields["linked_booking"].help_text = "For customer leads, Booking Confirmed needs a matching active booking; Converted needs a completed visit."
        if kind != "franchise":
            self.fields.pop("investment_range")
            self.fields.pop("franchise_model")

    def clean(self):
        data = super().clean()
        stage = data.get("status")
        if stage in OPEN_STAGES:
            if not data.get("next_action"):
                self.add_error("next_action", "Enter the next action for this open lead.")
            due = data.get("next_follow_up")
            previous = self.instance.next_task if self.instance.pk else None
            unchanged = previous and previous.status == "pending" and due and previous.due_at.replace(second=0, microsecond=0) == due
            if not due:
                self.add_error("next_follow_up", "Choose a follow-up deadline.")
            elif due <= timezone.now() and not unchanged:
                self.add_error("next_follow_up", "Choose a future follow-up time.")
        if stage == "lost" and not data.get("lost_reason", "").strip():
            self.add_error("lost_reason", "Record why this lead was lost.")
        booking = data.get("linked_booking")
        if booking and booking.phone != data.get("phone"):
            self.add_error("linked_booking", "The booking phone must match this lead.")
        if data.get("kind") == "contact" and stage in {"booked", "converted"}:
            if not booking or booking.status == "cancelled":
                self.add_error("linked_booking", "Choose this customer's confirmed or completed booking.")
            elif stage == "converted" and booking.status != "completed":
                self.add_error("linked_booking", "Mark Converted after a completed visit.")
        return data


class TaskForm(forms.ModelForm):
    version = forms.CharField(required=False, widget=forms.HiddenInput)
    class Meta:
        model = FollowUpTask
        fields = ["contact", "lead", "assigned_to", "title", "kind", "priority", "due_at", "description"]
        widgets = {"due_at": DATE_WIDGET, "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = staff_choices()
        self.fields["assigned_to"].required = True
        self.fields["contact"].queryset = CustomerRecord.objects.order_by("name", "phone")
        self.fields["lead"].queryset = Enquiry.objects.filter(status__in=OPEN_STAGES).order_by("-created_at")
        if self.instance.pk:
            self.fields["contact"].disabled = True
            self.fields["lead"].disabled = True
            self.fields["lead"].queryset = Enquiry.objects.all()
            self.fields["version"].initial = self.instance.updated_at.isoformat()

    def clean_due_at(self):
        due = self.cleaned_data["due_at"]
        unchanged = self.instance.pk and self.instance.due_at.replace(second=0, microsecond=0) == due
        if due <= timezone.now() and not unchanged:
            raise forms.ValidationError("Choose a future follow-up time.")
        return due

    def clean(self):
        data = super().clean()
        lead, contact = data.get("lead"), data.get("contact")
        if lead and contact and lead.phone != contact.phone:
            self.add_error("lead", "Choose an enquiry for this customer.")
        return data


class TaskOutcomeForm(forms.Form):
    outcome = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 3}))
    next_action = forms.CharField(max_length=150, required=False)
    next_follow_up = forms.DateTimeField(required=False, widget=DATE_WIDGET)
    version = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, task, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = task
        self.fields["version"].initial = task.updated_at.isoformat()
        self.needs_next = task.lead and task.lead.status in OPEN_STAGES and task.lead.next_task_id == task.pk

    def clean(self):
        data = super().clean()
        if self.needs_next:
            if not data.get("next_action"):
                self.add_error("next_action", "Schedule the next action, or close the lead from its pipeline page first.")
            if not data.get("next_follow_up") or data["next_follow_up"] <= timezone.now():
                self.add_error("next_follow_up", "Choose a future deadline for this open lead.")
        return data


class ActivityForm(forms.Form):
    kind = forms.ChoiceField(choices=[("note", "Note"), ("call", "Call"), ("email", "Email"), ("whatsapp", "WhatsApp"), ("meeting", "Meeting")])
    body = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 3}))


class AccountLinkForm(forms.Form):
    account = forms.ModelChoiceField(queryset=get_user_model().objects.none())
    verification_note = forms.CharField(min_length=10, max_length=1000, widget=forms.Textarea(attrs={"rows": 3}), help_text="Record how reception verified that this mobile number and the guest purchases belong to the selected customer.")
    verified = forms.BooleanField(label="I verified the customer's identity and ownership of these guest records")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = get_user_model().objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by("username")


class CRMContactForm(forms.ModelForm):
    phone = forms.CharField(max_length=10, validators=[BookingForm.phone_validator])
    class Meta:
        model = CustomerRecord
        fields = ["name", "phone", "preferences"]
