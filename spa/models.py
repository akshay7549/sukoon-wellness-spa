
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


# =========================================================
# SERVICE CATEGORY
# =========================================================

class ServiceCategory(models.Model):

    name = models.CharField(
        max_length=100
    )

    description = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="categories/",
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        default=True
    )

    class Meta:
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


# =========================================================
# SERVICE
# =========================================================

class Service(models.Model):
    staff_required = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(2)])
    requires_couple_room = models.BooleanField(default=False)
    is_package = models.BooleanField(default=False)

    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services"
    )

    name = models.CharField(
        max_length=150
    )

    short_description = models.CharField(
        max_length=255,
        blank=True
    )

    menu_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Menu rate without a fixed duration, for body care or multi-session packages. Online appointments require a duration option below.",
    )

    description = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="services/",
        blank=True,
        null=True
    )

    is_featured = models.BooleanField(
        default=False
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# =========================================================
# SERVICE OPTIONS
#
# ONE SERVICE CAN HAVE MULTIPLE DURATIONS / PRICES
#
# Example:
#
# Swedish Massage
# ├── 45 min → ₹1200
# ├── 60 min → ₹1500
# └── 90 min → ₹2000
#
# ServiceOption is now the ONLY source for
# duration and price.
# =========================================================

class ServiceOption(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="options"
    )

    duration = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Duration in minutes"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Price for this duration"
    )

    is_active = models.BooleanField(
        default=True
    )

    class Meta:
        ordering = [
            "service",
            "duration"
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["service", "duration"],
                name="unique_service_duration"
            ),
            models.CheckConstraint(condition=models.Q(duration__gt=0), name="option_positive_duration"),
            models.CheckConstraint(condition=models.Q(price__gte=0), name="option_nonnegative_price")
        ]

        verbose_name = "Service Option"
        verbose_name_plural = "Service Options"

    def __str__(self):
        return (
            f"{self.service.name} - "
            f"{self.duration} min - "
            f"₹{self.price}"
        )


# =========================================================
# STAFF
# =========================================================

class Staff(models.Model):

    name = models.CharField(
        max_length=100
    )

    phone = models.CharField(
        max_length=15,
        blank=True,
        null=True
    )

    email = models.EmailField(
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name


# =========================================================
# ROOM
# =========================================================

class Room(models.Model):
    is_couple_room = models.BooleanField(default=False, help_text="Room suitable for two simultaneous massage appointments.")

    name = models.CharField(
        max_length=100
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name


# =========================================================
# STAFF LEAVE
# =========================================================

class StaffLeave(models.Model):

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="leaves"
    )

    leave_date = models.DateField()

    reason = models.CharField(
        max_length=255,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints = [
            models.UniqueConstraint(
                fields=["staff", "leave_date"],
                name="unique_staff_leave_date"
            )
        ]

        ordering = [
            "leave_date"
        ]

    def __str__(self):
        return (
            f"{self.staff.name} - "
            f"{self.leave_date}"
        )


# =========================================================
# BOOKING
# =========================================================

class Booking(models.Model):
    secondary_staff = models.ForeignKey("Staff", on_delete=models.SET_NULL, null=True, blank=True, related_name="secondary_bookings")
    package_credit = models.ForeignKey("PackageCredit", on_delete=models.PROTECT, null=True, blank=True, related_name="bookings")

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )

    # =====================================================
    # BOOKING STATUS
    # =====================================================

    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    # =====================================================
    # CUSTOMER INFORMATION
    # =====================================================

    name = models.CharField(
        max_length=100
    )

    phone = models.CharField(
        max_length=15
    )

    email = models.EmailField(
        blank=True,
        null=True
    )

    # =====================================================
    # SELECTED SERVICE
    # =====================================================

    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings"
    )

    # =====================================================
    # SELECTED SERVICE DURATION
    #
    # The selected duration must come from ServiceOption.
    #
    # Example:
    # 45 / 60 / 90 minutes
    # =====================================================

    selected_duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Selected service duration in minutes"
    )

    # =====================================================
    # SELECTED SERVICE PRICE
    #
    # The selected price must come from ServiceOption.
    # =====================================================

    selected_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price of the selected service option"
    )

    # =====================================================
    # APPOINTMENT DATE & TIME
    # =====================================================

    appointment_date = models.DateField()

    appointment_time = models.TimeField(
        help_text="Booking start time"
    )

    end_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Booking end time"
    )

    # =====================================================
    # STAFF ASSIGNMENT
    # =====================================================

    staff = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings"
    )

    # =====================================================
    # ROOM ASSIGNMENT
    # =====================================================

    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings"
    )

    # =====================================================
    # CUSTOMER MESSAGE
    # =====================================================

    message = models.TextField(
        blank=True
    )

    # =====================================================
    # BOOKING STATUS
    # =====================================================

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="confirmed"
    )

    service_name_snapshot = models.CharField(max_length=150, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=None, validators=[MinValueValidator(0)], help_text="Leave blank if payment has not been recorded; enter 0 for known unpaid bookings.")
    payment_mode = models.CharField(max_length=12, blank=True, choices=[("cash", "Cash"), ("upi", "UPI"), ("card", "Card"), ("other", "Other")])
    payment_reference = models.CharField(max_length=100, blank=True)

    @property
    def net_amount(self):
        return None if self.selected_price is None else self.selected_price - self.discount_amount

    @property
    def balance_due(self):
        return None if self.net_amount is None or self.amount_paid is None else self.net_amount - self.amount_paid

    @property
    def payment_status(self):
        if self.net_amount is None or self.amount_paid is None:
            return "Not recorded"
        if self.amount_paid >= self.net_amount:
            return "Paid"
        return "Part paid" if self.amount_paid else "Unpaid"

    def clean(self):
        super().clean()
        errors = {}
        if self.selected_price is not None:
            if self.discount_amount > self.selected_price:
                errors["discount_amount"] = "Discount cannot exceed the service price."
            if self.amount_paid is not None and self.amount_paid > self.selected_price - self.discount_amount:
                errors["amount_paid"] = "Payment cannot exceed the total after discount."
        elif self.discount_amount or self.amount_paid:
            errors["amount_paid"] = "Record a service price before payment or discount."
        if self.amount_paid and not self.payment_mode:
            errors["payment_mode"] = "Choose a payment mode."
        if errors:
            raise ValidationError(errors)

    # =====================================================
    # WHATSAPP NOTIFICATION TRACKING
    # =====================================================

    whatsapp_sent = models.BooleanField(
        default=False,
        help_text="Whether a WhatsApp notification was sent."
    )

    whatsapp_last_status = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Last WhatsApp delivery/API status."
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    # =====================================================
    # META
    # =====================================================

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["appointment_date", "status"], name="booking_day_status"), models.Index(fields=["customer", "appointment_date"], name="booking_customer_day")]
        constraints = [models.CheckConstraint(condition=models.Q(discount_amount__gte=0), name="booking_discount_nonnegative"), models.CheckConstraint(condition=models.Q(amount_paid__gte=0), name="booking_paid_nonnegative")]
        permissions = [("view_business_analytics", "Can view full business analytics")]

    # =====================================================
    # STRING REPRESENTATION
    # =====================================================

    def __str__(self):

        service_name = (
            self.service.name
            if self.service
            else "No Service"
        )

        duration = (
            f"{self.selected_duration} min"
            if self.selected_duration
            else "No Duration"
        )

        return (
            f"{self.name} - "
            f"{service_name} - "
            f"{duration} - "
            f"{self.appointment_date} "
            f"{self.appointment_time}"
        )

class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    email_address = models.EmailField(unique=True, null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    def __str__(self):
        return self.user.get_username()

class Enquiry(models.Model):
    STAGES = [("new", "New"), ("contacted", "Contacted"), ("interested", "Interested"), ("booked", "Booking Confirmed"), ("converted", "Converted"), ("lost", "Lost"), ("closed", "Closed (legacy)")]
    SOURCES = [("website", "Website"), ("phone", "Phone"), ("whatsapp", "WhatsApp"), ("instagram", "Instagram"), ("facebook", "Facebook"), ("walkin", "Walk-in"), ("other", "Other")]
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_enquiries")
    contact = models.ForeignKey("CustomerRecord", on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")
    linked_booking = models.ForeignKey("Booking", on_delete=models.SET_NULL, null=True, blank=True, related_name="enquiries")
    next_task = models.ForeignKey("FollowUpTask", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    source = models.CharField(max_length=15, choices=SOURCES, default="website")
    lost_reason = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    kind = models.CharField(max_length=12, choices=[("contact", "Contact"), ("franchise", "Franchise")])
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    subject = models.CharField(max_length=150, blank=True)
    message = models.TextField()
    city = models.CharField(max_length=100, blank=True)
    investment_range = models.CharField(max_length=20, blank=True)
    franchise_model = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=15, choices=STAGES, default="new", db_index=True)
    staff_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"

class RateLimitBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

class Notification(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True)
    dedupe_key = models.CharField(max_length=200, unique=True)
    channel = models.CharField(max_length=12, choices=[("email", "Email"), ("whatsapp", "WhatsApp")])
    recipient = models.CharField(max_length=254)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    due_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=15, choices=[("pending", "Pending"), ("processing", "Processing"), ("sent", "Sent"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="pending")
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-due_at"]


from .business_models import Invoice, InvoiceLine, InvoicePayment, PackageComponent, PackageEnrollment, PackageCredit, CustomerRecord, PackageRedemption
from .crm_models import FollowUpTask, CRMActivity
