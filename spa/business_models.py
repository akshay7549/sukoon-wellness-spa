"""Reception invoices, dated collections and purchased treatment credits."""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Invoice(models.Model):
    booking = models.OneToOneField("spa.Booking", on_delete=models.PROTECT, null=True, blank=True, related_name="invoice")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    customer_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    opening_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0, validators=[MinValueValidator(0)], help_text="Previously received amount with no recorded receipt date. Leave blank if unknown. Excluded from dated collection reports.")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_invoices")

    class Meta:
        ordering = ["-issue_date", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(discount_amount__gte=0), name="invoice_discount_nonnegative"), models.CheckConstraint(condition=models.Q(opening_paid__gte=0), name="invoice_opening_nonnegative")]

    def __str__(self):
        return f"SWI-{self.pk:06d} · {self.customer_name}" if self.pk else self.customer_name

    @property
    def name(self):
        return self.customer_name

    @property
    def subtotal(self):
        return sum((line.total for line in self.lines.all()), Decimal("0"))

    @property
    def net_amount(self):
        return self.subtotal - self.discount_amount

    @property
    def dated_paid(self):
        return sum((p.amount for p in self.payments.all()), Decimal("0"))

    @property
    def amount_paid(self):
        return None if self.opening_paid is None else self.opening_paid + self.dated_paid

    @property
    def balance_due(self):
        return None if self.amount_paid is None else self.net_amount - self.amount_paid

    @property
    def payment_status(self):
        if self.amount_paid is None:
            return "Not recorded"
        if self.balance_due == 0:
            return "Paid"
        return "Part paid" if self.amount_paid else "Unpaid"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    service = models.ForeignKey("spa.Service", on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=200)
    duration = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0),name="invoice_line_positive_quantity"),models.CheckConstraint(condition=models.Q(unit_price__gte=0),name="invoice_line_nonnegative_price"),models.CheckConstraint(condition=models.Q(duration__gt=0),name="invoice_line_positive_duration")]

    @property
    def total(self):
        return self.unit_price * self.quantity


class InvoicePayment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    mode = models.CharField(max_length=12, choices=[("cash", "Cash"), ("upi", "UPI"), ("card", "Card"), ("other", "Other")])
    reference = models.CharField(max_length=100, blank=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    request_key = models.CharField(max_length=36, unique=True)

    class Meta:
        ordering = ["-received_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0),name="receipt_positive_amount")]


class PackageComponent(models.Model):
    max_duration = models.PositiveIntegerField(null=True,blank=True,validators=[MinValueValidator(1)],help_text="Maximum covered minutes. Blank permits every active duration; confirm the package policy before selling.")
    package = models.ForeignKey("spa.Service", on_delete=models.CASCADE, related_name="package_components")
    treatment = models.ForeignKey("spa.Service", on_delete=models.PROTECT, related_name="package_rules")
    alternative = models.ForeignKey("spa.Service", on_delete=models.PROTECT, null=True, blank=True, related_name="alternative_package_rules")
    sessions = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["package", "treatment"], name="unique_package_treatment")]

    def clean(self):
        if self.treatment_id == self.package_id or self.alternative_id == self.package_id:
            raise ValidationError("A package cannot contain itself.")


class PackageEnrollment(models.Model):
    invoice_line = models.OneToOneField(InvoiceLine, on_delete=models.PROTECT, related_name="enrollment")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="packages")
    customer_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    package_name = models.CharField(max_length=150)
    purchased_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-purchased_at"]

    def __str__(self):
        return f"{self.package_name} · {self.customer_name}"


class PackageCredit(models.Model):
    max_duration = models.PositiveIntegerField(null=True,blank=True,validators=[MinValueValidator(1)])
    enrollment = models.ForeignKey(PackageEnrollment, on_delete=models.CASCADE, related_name="credits")
    treatment = models.ForeignKey("spa.Service", on_delete=models.PROTECT, related_name="purchased_credits")
    alternative = models.ForeignKey("spa.Service", on_delete=models.PROTECT, null=True, blank=True, related_name="purchased_alternative_credits")
    label = models.CharField(max_length=200)
    total_sessions = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    @property
    def used(self):
        return len(self.redemptions.all())

    @property
    def reserved(self):
        return sum(b.status == "confirmed" for b in self.bookings.all())

    @property
    def remaining(self):
        return self.total_sessions - self.used

    @property
    def available(self):
        return max(0, self.remaining - self.reserved)

    def __str__(self):
        return f"{self.enrollment.customer_name} · {self.label} · {self.available} available"


class CustomerRecord(models.Model):
    phone = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=100, blank=True)
    preferences = models.TextField(blank=True, help_text="Reception-only preferences. Keep notes relevant to the service.")
    updated_at = models.DateTimeField(auto_now=True)


class PackageRedemption(models.Model):
    booking = models.OneToOneField("spa.Booking", on_delete=models.PROTECT, related_name="package_redemption")
    credit = models.ForeignKey(PackageCredit, on_delete=models.PROTECT, related_name="redemptions")
    redeemed_at = models.DateTimeField(default=timezone.now)
