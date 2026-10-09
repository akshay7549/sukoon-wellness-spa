from django.core.exceptions import ValidationError
from django.db import transaction
from ..models import Invoice, InvoiceLine, InvoicePayment, PackageEnrollment, PackageCredit


def activate_packages(invoice):
    if invoice.amount_paid is None or invoice.balance_due != 0:
        return
    for line in invoice.lines.select_related("service"):
        if not line.service or not line.service.is_package:
            continue
        enrollment, created = PackageEnrollment.objects.get_or_create(invoice_line=line, defaults={"customer":invoice.customer,"customer_name":invoice.customer_name,"phone":invoice.phone,"package_name":line.description})
        if not created: continue
        for rule in line.service.package_components.select_related("treatment", "alternative"):
            label = rule.treatment.name + (f" or {rule.alternative.name}" if rule.alternative else "")
            PackageCredit.objects.create(enrollment=enrollment, treatment=rule.treatment, alternative=rule.alternative, label=label, total_sessions=rule.sessions,max_duration=rule.max_duration)


@transaction.atomic
def save_invoice(form, formset, user):
    if form.instance.pk:
        locked=Invoice.objects.select_for_update().get(pk=form.instance.pk)
        if locked.payments.exists() or PackageEnrollment.objects.filter(invoice_line__invoice=locked).exists():
            raise ValidationError("Receipted invoices are locked. Create a separate invoice for additional services.")
    invoice=form.save(commit=False)
    rows=[f for f in formset.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
    subtotal=sum(f.cleaned_data["unit_price"]*f.cleaned_data["quantity"] for f in rows)
    if invoice.discount_amount>subtotal:
        raise ValidationError("Discount cannot exceed the service total.")
    if invoice.opening_paid is not None and invoice.opening_paid>subtotal-invoice.discount_amount:
        raise ValidationError("Previously received amount cannot exceed the invoice total.")
    if not invoice.pk: invoice.created_by=user
    invoice.save()
    for deleted in formset.deleted_forms:
        if deleted.instance.pk: deleted.instance.delete()
    for f in rows:
        line=f.save(commit=False);line.invoice=invoice;line.full_clean();line.save()
    activate_packages(invoice)
    return invoice


@transaction.atomic
def record_payment(invoice_id, data, user):
    invoice=Invoice.objects.select_for_update().get(pk=invoice_id)
    key=str(data["request_key"])
    existing=InvoicePayment.objects.filter(request_key=key).first()
    if existing:
        if existing.invoice_id!=invoice.pk or existing.amount!=data["amount"] or existing.mode!=data["mode"] or existing.reference!=data.get("reference",""):
            raise ValidationError("This receipt request was already used for another payment.")
        return existing
    if invoice.balance_due is None:
        raise ValidationError("Confirm the previously received amount before recording a new receipt.")
    if data["amount"]>invoice.balance_due:
        raise ValidationError("Payment cannot exceed the outstanding balance.")
    payment=InvoicePayment(invoice=invoice,recorded_by=user,**data)
    payment.request_key=key
    payment.full_clean();payment.save()
    activate_packages(invoice)
    return payment
