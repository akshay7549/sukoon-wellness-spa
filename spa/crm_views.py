from datetime import datetime, time, timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import Enquiry, FollowUpTask, CustomerRecord, Booking, Invoice, PackageEnrollment, CRMActivity
from .crm_forms import LeadForm, TaskForm, TaskOutcomeForm, ActivityForm, AccountLinkForm, staff_choices
from .business_forms import CustomerRecordForm
from .services.crm import save_lead, save_task, complete_task, link_guest_records, activity


def assign_filter(queryset, value, user):
    if value == "mine":
        return queryset.filter(assigned_to=user)
    if value == "unassigned":
        return queryset.filter(assigned_to__isnull=True)
    if value.isdigit():
        return queryset.filter(assigned_to_id=int(value))
    return queryset


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_enquiry", raise_exception=True)
def pipeline(request):
    kind = request.GET.get("kind", "contact")
    if kind not in {"contact", "franchise"}: kind = "contact"
    query = request.GET.get("q", "").strip()[:100]
    owner = request.GET.get("owner", "")
    leads = Enquiry.objects.filter(kind=kind).select_related("assigned_to", "next_task", "contact", "linked_booking")
    if query:
        leads = leads.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query) | Q(subject__icontains=query))
    leads = assign_filter(leads, owner, request.user)
    counts = dict(leads.values("status").annotate(n=Count("pk")).values_list("status", "n"))
    stages = list(Enquiry.STAGES)
    if kind == "franchise":
        stages = [(k, "Meeting Scheduled" if k == "booked" else "Won" if k == "converted" else v) for k, v in stages]
    columns = []
    for stage, label in stages:
        if stage == "closed" and not counts.get(stage): continue
        params = request.GET.copy(); params["view"] = "list"; params["stage"] = stage; params.pop("page", None)
        columns.append({"key": stage, "label": label, "count": counts.get(stage, 0), "leads": list(leads.filter(status=stage).order_by("created_at")[:25]), "all_query": params.urlencode()})
    stage = request.GET.get("stage", "")
    filtered = leads.filter(status=stage) if stage in dict(Enquiry.STAGES) else leads
    return render(request, "admin/crm_pipeline.html", {"columns": columns, "kind": kind, "query": query, "owner": owner,
                  "owners": staff_choices(), "total": leads.count(), "unassigned": leads.filter(assigned_to__isnull=True).count(),
                  "overdue": leads.filter(next_task__status="pending", next_task__due_at__lt=timezone.now()).count(),
                  "list_view": request.GET.get("view") == "list", "stage": stage,
                  "page": Paginator(filtered.order_by("-created_at"), 30).get_page(request.GET.get("page")), "page_query": page_query(request)})


def page_query(request):
    params = request.GET.copy(); params.pop("page", None)
    return params.urlencode()


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_booking", raise_exception=True)
def booking_options(request):
    from .forms import BookingForm
    phone = request.GET.get("phone", "")
    try: BookingForm.phone_validator(phone)
    except ValidationError: return JsonResponse({"bookings": []})
    bookings = Booking.objects.filter(phone=phone, status__in=["confirmed", "completed"]).select_related("service").order_by("-appointment_date", "-pk")[:30]
    return JsonResponse({"bookings": [{"id": b.pk, "label": f"#{b.pk} · {b.appointment_date:%d %b %Y} · {b.service_name_snapshot or (b.service.name if b.service else 'Treatment')} · {b.get_status_display()}"} for b in bookings]})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_enquiry", raise_exception=True)
@require_http_methods(["GET", "POST"])
def lead_edit(request, lead_id=None):
    can_edit = request.user.has_perm("spa.change_enquiry" if lead_id else "spa.add_enquiry")
    if not can_edit and (not lead_id or request.method == "POST"):
        raise PermissionDenied
    lead = get_object_or_404(Enquiry.objects.select_related("next_task", "assigned_to", "contact"), pk=lead_id) if lead_id else Enquiry()
    initial = {} if lead_id else {"assigned_to": request.user.pk, "source": "phone", "kind": "contact"}
    if not lead_id and request.GET.get("kind") == "franchise": initial["kind"] = "franchise"
    suggested = request.GET.get("stage")
    if suggested in dict(Enquiry.STAGES) and suggested != "closed": initial["status"] = suggested
    form = LeadForm(request.POST if request.method == "POST" else None, instance=lead, initial=initial)
    if request.method == "POST" and form.is_valid():
        if not all(request.user.has_perm(p) for p in ["spa.add_followuptask", "spa.change_followuptask"]): raise PermissionDenied
        try:
            lead = save_lead(form, request.user)
            messages.success(request, "Lead and next follow-up saved.")
            return redirect("crm_lead_edit", lead_id=lead.pk)
        except ValidationError as exc: form.add_error(None, exc)
    history = lead.activities.select_related("actor")[:15] if lead.pk else []
    if not can_edit:
        for field in form.fields.values(): field.disabled = True
    return render(request, "admin/crm_lead_edit.html", {"form": form, "lead": lead, "history": history, "can_edit": can_edit})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_followuptask", raise_exception=True)
def task_centre(request):
    now = timezone.now(); today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today, time.min)); end = start + timedelta(days=1)
    owner = request.GET.get("owner", "")
    base = assign_filter(FollowUpTask.objects.select_related("contact", "lead", "assigned_to"), owner, request.user)
    contact = request.GET.get("contact", "")
    if contact.isdigit(): base = base.filter(contact_id=contact)
    query = request.GET.get("q", "").strip()[:100]
    if query: base = base.filter(Q(title__icontains=query) | Q(contact__phone__icontains=query) | Q(contact__name__icontains=query))
    counts = {"today": base.filter(status="pending", due_at__gte=start, due_at__lt=end).count(),
              "overdue": base.filter(status="pending", due_at__lt=now).count(), "upcoming": base.filter(status="pending", due_at__gte=end).count(),
              "completed": base.filter(status="completed").count(), "pending": base.filter(status="pending").count()}
    tab = request.GET.get("tab", "pending")
    filters = {"today": Q(status="pending", due_at__gte=start, due_at__lt=end), "overdue": Q(status="pending", due_at__lt=now),
               "upcoming": Q(status="pending", due_at__gte=end), "completed": Q(status="completed"), "pending": Q(status="pending"), "all": Q()}
    if tab not in filters: tab = "pending"
    tasks = base.filter(filters[tab])
    priority = request.GET.get("priority", "")
    if priority in {"normal", "high"}: tasks = tasks.filter(priority=priority)
    if tab == "completed": tasks = tasks.order_by("-completed_at", "-pk")
    return render(request, "admin/crm_tasks.html", {"page": Paginator(tasks, 30).get_page(request.GET.get("page")), "tab": tab,
                  "counts": counts, "owner": owner, "owners": staff_choices(), "query": query, "priority": priority,
                  "contact_filter": contact, "page_query": page_query(request)})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_followuptask", raise_exception=True)
@require_http_methods(["GET", "POST"])
def task_edit(request, task_id=None):
    if not request.user.has_perm("spa.change_followuptask" if task_id else "spa.add_followuptask"): raise PermissionDenied
    task = get_object_or_404(FollowUpTask.objects.select_related("lead", "contact", "assigned_to"), pk=task_id) if task_id else FollowUpTask()
    initial = {} if task_id else {"assigned_to": request.user.pk}
    if request.GET.get("contact", "").isdigit(): initial["contact"] = request.GET["contact"]
    if request.GET.get("lead", "").isdigit(): initial["lead"] = request.GET["lead"]
    form = TaskForm(request.POST if request.method == "POST" else None, instance=task, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            task = save_task(form, request.user); messages.success(request, "Follow-up task saved.")
            return redirect("crm_task_edit", task_id=task.pk)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "admin/crm_task_edit.html", {"form": form, "task": task})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.change_followuptask", raise_exception=True)
@require_http_methods(["GET", "POST"])
def task_complete(request, task_id):
    task = get_object_or_404(FollowUpTask.objects.select_related("lead", "contact"), pk=task_id)
    form = TaskOutcomeForm(request.POST if request.method == "POST" else None, task=task)
    if request.method == "POST" and form.is_valid():
        try:
            changed = complete_task(task.pk, form.cleaned_data, request.user)
            messages.success(request, "Task completed and outcome saved." if changed else "This task was already closed.")
            return redirect("crm_tasks")
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "admin/crm_task_complete.html", {"form": form, "task": task})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_customerrecord", raise_exception=True)
def customers(request):
    query = request.GET.get("q", "").strip()[:100]
    contacts = CustomerRecord.objects.select_related("account").order_by("name", "phone")
    if query: contacts = contacts.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(account__email__icontains=query))
    return render(request, "admin/crm_customers.html", {"page": Paginator(contacts, 30).get_page(request.GET.get("page")), "query": query, "page_query": page_query(request)})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_customerrecord", raise_exception=True)
@require_http_methods(["GET", "POST"])
def customer_detail(request, phone):
    contact = get_object_or_404(CustomerRecord.objects.select_related("account", "account_verified_by"), phone=phone)
    action = request.POST.get("action") if request.method == "POST" else None
    preferences = CustomerRecordForm(request.POST if action == "preferences" else None, instance=contact)
    note = ActivityForm(request.POST if action == "activity" else None)
    if request.method == "POST":
        if action == "preferences":
            if not request.user.has_perm("spa.change_customerrecord"): raise PermissionDenied
            if preferences.is_valid(): preferences.save(); messages.success(request, "Customer preferences saved."); return redirect("crm_customer_detail", phone=phone)
        elif action == "activity":
            if not request.user.has_perm("spa.add_crmactivity"): raise PermissionDenied
            if note.is_valid(): activity(contact, request.user, note.cleaned_data["body"], note.cleaned_data["kind"]); messages.success(request, "Activity logged."); return redirect(reverse("crm_customer_detail", args=[phone]) + "#timeline")
        else: raise PermissionDenied
    identity = Q(phone=phone)
    if contact.account_id: identity |= Q(customer_id=contact.account_id)
    visits = list(Booking.objects.filter(identity).select_related("service", "staff", "secondary_staff", "room", "invoice").order_by("-appointment_date", "-appointment_time")) if request.user.has_perm("spa.view_booking") else []
    invoices = list(Invoice.objects.filter(identity | Q(booking_id__in=[b.pk for b in visits])).prefetch_related("lines", "payments")) if request.user.has_perm("spa.view_invoice") else []
    packages = PackageEnrollment.objects.filter(identity).prefetch_related("credits__bookings", "credits__redemptions") if request.user.has_perm("spa.view_packageenrollment") else []
    receipts = sum((i.dated_paid for i in invoices), Decimal("0"))
    historical = sum((i.opening_paid or Decimal("0") for i in invoices), Decimal("0"))
    legacy = [b for b in visits if not hasattr(b, "invoice") and b.status != "cancelled"]
    historical += sum((b.amount_paid or Decimal("0") for b in legacy), Decimal("0"))
    due = sum((i.balance_due or Decimal("0") for i in invoices), Decimal("0")) + sum((b.balance_due or Decimal("0") for b in legacy), Decimal("0"))
    unknown = sum(i.amount_paid is None or i.balance_due is None for i in invoices) + sum(b.amount_paid is None or b.balance_due is None for b in legacy)
    history = contact.activities.select_related("actor") if request.user.has_perm("spa.view_crmactivity") else CRMActivity.objects.none()
    last_contact = history.filter(kind__in=["call", "email", "whatsapp", "meeting"]).first()
    return render(request, "admin/crm_customer_detail.html", {"contact": contact, "preferences": preferences, "note": note,
                  "visits": Paginator(visits, 15).get_page(request.GET.get("visits_page")), "visit_count": len(visits),
                  "invoices": invoices, "packages": packages, "dated_received": receipts, "historical_received": historical,
                  "received": receipts + historical, "due": due, "unknown_payments": unknown, "last_contact": last_contact,
                  "timeline": Paginator(history, 20).get_page(request.GET.get("timeline_page")),
                  "tasks": contact.tasks.select_related("assigned_to", "lead").filter(status="pending")[:15] if request.user.has_perm("spa.view_followuptask") else [],
                  "leads": Enquiry.objects.filter(phone=phone).select_related("assigned_to", "next_task") if request.user.has_perm("spa.view_enquiry") else []})


@never_cache
@staff_member_required(login_url="login")
@permission_required(["spa.view_customerrecord", "spa.link_customer_account"], raise_exception=True)
@require_http_methods(["GET", "POST"])
def account_link(request, phone):
    contact = get_object_or_404(CustomerRecord.objects.select_related("account"), phone=phone)
    form = AccountLinkForm(request.POST if request.method == "POST" else None, initial={"account": contact.account_id})
    if request.method == "POST" and form.is_valid():
        try:
            link_guest_records(contact.pk, form.cleaned_data, request.user)
            messages.success(request, "Verified guest records linked. Financial amounts and receipt history were preserved.")
            return redirect("crm_customer_detail", phone=phone)
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "admin/crm_account_link.html", {"form": form, "contact": contact})
