from datetime import datetime, time, timedelta
from decimal import Decimal
import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required, login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import Invoice, InvoiceLine, InvoicePayment, Booking, Staff, Room, CustomerRecord, PackageEnrollment
from .business_forms import InvoiceForm, InvoiceLines, PaymentForm, CustomerRecordForm
from .services.invoicing import save_invoice, record_payment
from .connect_views import ADDRESS, connect_url, connect_qr_data_uri


def selected_date(value, default):
    try: return datetime.strptime(value or "", "%Y-%m-%d").date()
    except (ValueError, TypeError): return default


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_invoice", raise_exception=True)
def invoice_list(request):
    query=request.GET.get("q", "").strip()[:100]
    invoices=Invoice.objects.select_related("booking").prefetch_related("lines", "payments")
    if query: invoices=invoices.filter(Q(customer_name__icontains=query)|Q(phone__icontains=query))
    return render(request,"admin/invoices.html",{"page":Paginator(invoices,20).get_page(request.GET.get("page")),"query":query})


@never_cache
@staff_member_required(login_url="login")
def invoice_edit(request, invoice_id=None):
    permission="spa.change_invoice" if invoice_id else "spa.add_invoice"
    if not request.user.has_perm(permission):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    invoice=get_object_or_404(Invoice,pk=invoice_id) if invoice_id else Invoice()
    initial={};lines_initial=[]
    if not invoice_id and request.GET.get("booking","").isdigit():
        b=get_object_or_404(Booking,pk=request.GET["booking"])
        if hasattr(b,"invoice"):return redirect("invoice_edit",invoice_id=b.invoice.pk)
        initial={"booking":b.pk,"customer":b.customer_id,"customer_name":b.name,"phone":b.phone,"email":b.email or "","discount_amount":b.discount_amount,"opening_paid":b.amount_paid}
        lines_initial=[{"service":b.service_id,"description":b.service_name_snapshot or (b.service.name if b.service else "Treatment"),"duration":b.selected_duration,"quantity":1,"unit_price":b.selected_price}]
    form=InvoiceForm(request.POST if request.method=="POST" else None,instance=invoice,initial=initial)
    lines=InvoiceLines(request.POST if request.method=="POST" else None,queryset=invoice.lines.all() if invoice.pk else InvoiceLine.objects.none(),initial=lines_initial,prefix="items")
    locked=invoice.pk and (invoice.payments.exists() or PackageEnrollment.objects.filter(invoice_line__invoice=invoice).exists())
    if request.method=="POST" and form.is_valid() and lines.is_valid():
        try:
            saved=save_invoice(form,lines,request.user)
            messages.success(request,"Invoice saved. Record receipts below; packages activate when fully paid.")
            return redirect("invoice_edit",invoice_id=saved.pk)
        except ValidationError as exc:form.add_error(None,exc)
    if locked:
        for field in form.fields.values():field.disabled=True
        for item in lines:
            for field in item.fields.values():field.disabled=True
    return render(request,"admin/invoice_edit.html",{"form":form,"lines":lines,"invoice":invoice,"locked":locked,"payment_form":PaymentForm()})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.add_invoicepayment",raise_exception=True)
@require_POST
def invoice_payment(request,invoice_id):
    invoice=get_object_or_404(Invoice,pk=invoice_id)
    form=PaymentForm(request.POST)
    if form.is_valid():
        try:
            record_payment(invoice.pk,form.cleaned_data,request.user)
            messages.success(request,"Receipt recorded.")
        except ValidationError as exc:messages.error(request," ".join(exc.messages))
    else:messages.error(request," ".join(f"{k}: {' '.join(v)}" for k,v in form.errors.items()))
    return redirect("invoice_edit",invoice_id=invoice.pk)


@never_cache
@login_required
def invoice_print(request,invoice_id):
    invoices=Invoice.objects.select_related("booking").prefetch_related("lines","payments")
    if not (request.user.is_staff and request.user.has_perm("spa.view_invoice")):
        invoices=invoices.filter(customer=request.user)
    invoice=get_object_or_404(invoices,pk=invoice_id)
    return render(request,"admin/bill.html",{"invoice":invoice,"booking":invoice,"line_items":invoice.lines.all(),"price":invoice.subtotal,"generated_at":timezone.now(),"business_address":ADDRESS,"connect_url":connect_url(),"qr_code":connect_qr_data_uri()})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_booking",raise_exception=True)
def appointment_calendar(request):
    day=selected_date(request.GET.get("date"),timezone.localdate())
    bookings=list(Booking.objects.filter(appointment_date=day).exclude(status="cancelled").select_related("service","staff","secondary_staff","room"))
    staff=list(Staff.objects.filter(is_active=True))
    rooms=list(Room.objects.filter(is_active=True))
    from .services.availability import day_resources,free_resources,minutes_to_time,time_to_minutes
    resources=day_resources(day)
    rows=[]
    for minute in range(600,1320,15):
        start,end=minutes_to_time(minute),minutes_to_time(minute+15)
        free_staff,free_rooms=free_resources(resources,start,end)
        staff_cells=[];room_cells=[]
        for resource,items,attr in [(s,staff_cells,"staff") for s in staff]+[(r,room_cells,"room") for r in rooms]:
            event=next((b for b in bookings if (resource.pk in (b.staff_id,b.secondary_staff_id) if attr=="staff" else resource.pk==b.room_id) and time_to_minutes(b.appointment_time)<=minute<time_to_minutes(b.end_time or b.appointment_time)),None)
            free=resource.pk in {r.pk for r in (free_staff if attr=="staff" else free_rooms)}
            items.append({"resource":resource,"booking":event,"free":free,"first":event and minute==time_to_minutes(event.appointment_time)})
        rows.append({"time":start,"staff":staff_cells,"rooms":room_cells})
    return render(request,"admin/calendar.html",{"day":day,"previous":day-timedelta(days=1),"next":day+timedelta(days=1),"staff":staff,"rooms":rooms,"rows":rows})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_business_analytics",raise_exception=True)
def collections(request):
    today=timezone.localdate()
    start=selected_date(request.GET.get("start"),today.replace(day=1))
    end=selected_date(request.GET.get("end"),today)
    if end<start:end=start
    receipts=InvoicePayment.objects.filter(received_at__gte=timezone.make_aware(datetime.combine(start,time.min)),received_at__lt=timezone.make_aware(datetime.combine(end+timedelta(days=1),time.min))).select_related("invoice","recorded_by")
    totals=receipts.values("mode").annotate(amount=Sum("amount"),count=Count("pk")).order_by("mode")
    invoices=list(Invoice.objects.prefetch_related("lines","payments"))
    due=[i for i in invoices if i.balance_due is not None and i.balance_due>0]
    return render(request,"admin/collections.html",{"start":start,"end":end,"totals":totals,"collected":receipts.aggregate(value=Sum("amount"))["value"] or Decimal("0"),"receipts":Paginator(receipts,25).get_page(request.GET.get("page")),"outstanding":sum(i.balance_due for i in due),"due":due[:30],"unknown":sum(i.balance_due is None for i in invoices)})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_booking",raise_exception=True)
def customer_history(request):
    phone=request.GET.get("phone", "").strip()
    context={"phone":phone}
    if re.fullmatch(r"[6-9]\d{9}",phone):
        record=CustomerRecord.objects.filter(phone=phone).first() or CustomerRecord(phone=phone)
        form=CustomerRecordForm(request.POST if request.method=="POST" else None,instance=record)
        if request.method=="POST":
            if not request.user.has_perm("spa.change_customerrecord"):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied
            if form.is_valid():form.save();messages.success(request,"Reception preferences saved.");return redirect(request.get_full_path())
        context.update({"form":form,"visits":Booking.objects.filter(phone=phone).select_related("service","staff").order_by("-appointment_date"),"invoices":Invoice.objects.filter(phone=phone).prefetch_related("lines","payments"),"packages":PackageEnrollment.objects.filter(phone=phone).prefetch_related("credits__bookings","credits__redemptions"),"can_edit_notes":request.user.has_perm("spa.change_customerrecord")})
    return render(request,"admin/customer_history.html",context)
