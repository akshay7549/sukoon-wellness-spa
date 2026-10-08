from django.db import models


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

    description = models.TextField(
        blank=True
    )

    # Service's default/base price
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # Default duration in minutes
    duration = models.PositiveIntegerField(
        help_text="Duration in minutes"
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
# SERVICE DURATION / PRICE OPTIONS
# =========================================================

class ServiceOption(models.Model):

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="options"
    )

    duration = models.PositiveIntegerField(
        help_text="Duration in minutes"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
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
            )
        ]

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

    # =====================================================
    # BOOKING STATUS
    # =====================================================
    #
    # Booking is created only after availability validation.
    #
    # Therefore:
    # confirmed = newly created booking
    # completed = appointment completed
    # cancelled = appointment cancelled
    #

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
    # SELECTED SERVICE OPTION
    # =====================================================

    selected_duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Selected service duration in minutes"
    )

    selected_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price of the selected service"
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
        ordering = [
            "-created_at"
        ]

    # =====================================================
    # STRING REPRESENTATION
    # =====================================================

    def __str__(self):

        service_name = (
            self.service.name
            if self.service
            else "No Service"
        )

        return (
            f"{self.name} - "
            f"{service_name} - "
            f"{self.appointment_date} "
            f"{self.appointment_time}"
        )