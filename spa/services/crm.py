from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from ..models import Enquiry, FollowUpTask, CRMActivity, CustomerRecord, Booking, Invoice, PackageEnrollment, Staff, Room
from ..crm_forms import OPEN_STAGES


def activity(contact, actor, body, kind="note", lead=None):
    return CRMActivity.objects.create(contact=contact, actor=actor, body=body, kind=kind, lead=lead)


def _check_version(original, value):
    if original and original.updated_at.isoformat() != value:
        raise ValidationError("This record changed while you were editing. Reload the page before saving.")


@transaction.atomic
def save_lead(form, actor):
    original = Enquiry.objects.select_for_update().get(pk=form.instance.pk) if form.instance.pk else None
    _check_version(original, form.cleaned_data.get("version"))
    lead = form.save(commit=False)
    contact, _ = CustomerRecord.objects.get_or_create(phone=lead.phone, defaults={"name": lead.name})
    lead.contact = contact
    lead.full_clean(exclude=["next_task"])
    lead.save()
    if lead.status in OPEN_STAGES:
        task = FollowUpTask.objects.select_for_update().filter(pk=original.next_task_id, status="pending").first() if original and original.next_task_id else None
        if not task:
            task = FollowUpTask(contact=contact, lead=lead, created_by=actor)
        task.title = form.cleaned_data["next_action"]
        task.due_at = form.cleaned_data["next_follow_up"]
        task.assigned_to = lead.assigned_to
        task.full_clean()
        task.save()
        lead.next_task = task
    else:
        lead.tasks.filter(status="pending").update(status="cancelled", updated_at=timezone.now())
        lead.next_task = None
    lead.save(update_fields=["next_task"])
    old_label = original.get_status_display() if original else "New enquiry"
    body = f"{old_label} → {lead.get_status_display()}. Owner: {lead.assigned_to.get_username()}."
    if lead.status == "lost":
        body += f" Reason: {lead.lost_reason}"
    activity(contact, actor, body, "stage", lead)
    return lead


@transaction.atomic
def save_task(form, actor):
    lead_id = form.instance.lead_id or getattr(form.cleaned_data.get("lead"), "pk", None)
    lead = Enquiry.objects.select_for_update().get(pk=lead_id) if lead_id else None
    original = FollowUpTask.objects.select_for_update().get(pk=form.instance.pk) if form.instance.pk else None
    _check_version(original, form.cleaned_data.get("version"))
    if original and original.status != "pending":
        raise ValidationError("Completed or cancelled tasks are read-only. Create a new task.")
    if lead and lead.status not in OPEN_STAGES:
        raise ValidationError("Reopen this lead before adding a follow-up.")
    task = form.save(commit=False)
    if not original:
        task.created_by = actor
    task.full_clean()
    task.save()
    if lead and (not lead.next_task_id or lead.next_task_id == task.pk or not lead.next_task or lead.next_task.status != "pending"):
        lead.next_task = task
        lead.assigned_to = task.assigned_to
        lead.save(update_fields=["next_task", "assigned_to", "updated_at"])
    activity(task.contact, actor, f"Follow-up {'updated' if original else 'created'}: {task.title}.", "task", lead)
    return task


@transaction.atomic
def complete_task(task_id, data, actor):
    lead_id = FollowUpTask.objects.values_list("lead_id", flat=True).get(pk=task_id)
    lead = Enquiry.objects.select_for_update().get(pk=lead_id) if lead_id else None
    task = FollowUpTask.objects.select_for_update().get(pk=task_id)
    if task.status != "pending":
        return False
    _check_version(task, data.get("version"))
    needs_next = lead and lead.status in OPEN_STAGES and lead.next_task_id == task.pk
    if needs_next and (not data.get("next_action") or not data.get("next_follow_up") or data["next_follow_up"] <= timezone.now()):
        raise ValidationError("An open lead needs a next action and a future follow-up deadline.")
    task.status = "completed"
    task.completed_at = timezone.now()
    task.completed_by = actor
    task.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
    if needs_next:
        following = FollowUpTask.objects.create(contact=task.contact, lead=lead, assigned_to=lead.assigned_to or task.assigned_to,
                                                title=data["next_action"], due_at=data["next_follow_up"], created_by=actor)
        lead.next_task = following
        lead.save(update_fields=["next_task", "updated_at"])
    activity(task.contact, actor, f"Completed: {task.title}\n{data['outcome']}", "task", lead)
    return True


@transaction.atomic
def link_guest_records(contact_id, data, actor):
    # Match booking writers' lock order while customer ownership changes.
    list(Staff.objects.select_for_update().order_by("pk"))
    list(Room.objects.select_for_update().order_by("pk"))
    contact = CustomerRecord.objects.select_for_update().get(pk=contact_id)
    target = get_user_model().objects.select_for_update().get(pk=data["account"].pk)
    if target.is_staff or target.is_superuser or not target.is_active or not data.get("verified"):
        raise ValidationError("Choose an active customer and record reception verification.")
    if contact.account_id and contact.account_id != target.pk:
        raise ValidationError("This contact is already linked to another account. Existing ownership cannot be reassigned here.")
    groups = [Booking.objects.select_for_update().filter(phone=contact.phone),
              Invoice.objects.select_for_update().filter(phone=contact.phone),
              PackageEnrollment.objects.select_for_update().filter(phone=contact.phone)]
    for records in groups:
        for record in records:
            if record.customer_id and record.customer_id != target.pk:
                raise ValidationError("This mobile number has records owned by another account. Resolve the identity conflict before linking guests.")
            if isinstance(record, Invoice) and record.booking_id and (record.booking.phone != contact.phone or record.booking.customer_id not in (None, target.pk)):
                raise ValidationError("A linked invoice has a booking identity conflict. Resolve it before linking guests.")
            if isinstance(record, PackageEnrollment) and (record.invoice_line.invoice.phone != contact.phone or record.invoice_line.invoice.customer_id not in (None, target.pk)):
                raise ValidationError("A package has an invoice identity conflict. Resolve it before linking guests.")
    counts = [records.filter(customer__isnull=True).update(customer=target) for records in groups]
    contact.account = target
    contact.account_verified_at = timezone.now()
    contact.account_verified_by = actor
    contact.account_verification_note = data["verification_note"]
    contact.save()
    activity(contact, actor, f"Reception verified account {target.get_username()}. Linked {counts[0]} guest bookings, {counts[1]} invoices and {counts[2]} packages. Verification: {data['verification_note']}", "account_link")
    return counts
