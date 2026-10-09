
from urllib.parse import quote

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .admin_site import sukoon_admin_site

from .models import (
    Booking,
    Service,
    ServiceCategory,
    ServiceOption,
    Staff,
    Room,
    StaffLeave,
)


# =========================================================
# SERVICE CATEGORY ADMIN
# =========================================================

class ServiceCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
    )

    ordering = (
        "name",
    )

    list_per_page = 25


# =========================================================
# SERVICE OPTION INLINE
#
# Duration + Price are now managed INSIDE Service.
#
# Example:
# Swedish Massage
#   45 min - ₹1200
#   60 min - ₹1500
#   90 min - ₹2000
# =========================================================

from .models import PackageComponent, PackageEnrollment, PackageCredit, CustomerRecord, Invoice, InvoicePayment


class PackageComponentInline(admin.TabularInline):
    model = PackageComponent
    fk_name = "package"
    extra = 0
    fields = ("treatment", "alternative", "sessions", "max_duration")


class ServiceOptionInline(admin.TabularInline):

    model = ServiceOption

    extra = 1

    min_num = 0

    fields = (
        "duration",
        "price",
        "is_active",
    )

    ordering = (
        "duration",
    )

    show_change_link = False

    verbose_name = "Duration & Price Option"

    verbose_name_plural = "Duration & Price Options"


# =========================================================
# SERVICE ADMIN
# =========================================================

class ServiceAdmin(admin.ModelAdmin):

    # -----------------------------------------------------
    # SERVICE LIST
    # -----------------------------------------------------

    list_display = (
        "name",
        "category",
        "duration_options",
        "is_featured",
        "is_active",
    )

    list_filter = (
        "category",
        "is_featured",
        "is_active",
    )

    search_fields = (
        "name",
        "short_description",
        "description",
    )

    ordering = (
        "name",
    )

    list_per_page = 25

    autocomplete_fields = (
        "category",
    )

    # -----------------------------------------------------
    # INLINE OPTIONS
    # -----------------------------------------------------

    inlines = (
        ServiceOptionInline,
        PackageComponentInline,
    )

    # -----------------------------------------------------
    # CUSTOM DISPLAY
    # -----------------------------------------------------

    @admin.display(
        description="Durations",
    )
    def duration_options(self, obj):

        options = obj.options.filter(
            is_active=True
        ).order_by("duration")

        if not options.exists():
            if obj.menu_price is not None:
                return format_html("₹{} · Reception booking", obj.menu_price)
            return mark_safe(
                '<span style="color:#999;">No options</span>'
            )

        items = []

        for option in options:

            items.append(
                format_html(
                    '<span style="'
                    'display:inline-block;'
                    'margin:2px 3px 2px 0;'
                    'padding:4px 8px;'
                    'border-radius:12px;'
                    'background:#f5efe3;'
                    'color:#403a32;'
                    'font-size:11px;'
                    'font-weight:600;'
                    '">'
                    '{} min · ₹{}'
                    '</span>',
                    option.duration,
                    option.price,
                )
            )

        return format_html(
            "{}",
            mark_safe("".join(items))
        )


# =========================================================
# NOTE:
#
# ServiceOption is intentionally NOT registered separately.
#
# Duration + Price are managed through ServiceAdmin inline.
# =========================================================


# =========================================================
# STAFF ADMIN
# =========================================================

class StaffAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "phone",
        "email",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "phone",
        "email",
    )

    ordering = (
        "name",
    )

    readonly_fields = (
        "created_at",
    )

    list_per_page = 25


# =========================================================
# ROOM ADMIN
# =========================================================

class RoomAdmin(admin.ModelAdmin):
    list_editable = ("is_couple_room",)

    list_display = (
        "name",
        "is_couple_room",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
    )

    ordering = (
        "name",
    )

    readonly_fields = (
        "created_at",
    )

    list_per_page = 25


# =========================================================
# STAFF LEAVE ADMIN
# =========================================================

class StaffLeaveAdmin(admin.ModelAdmin):

    list_display = (
        "staff",
        "leave_date",
        "reason",
        "created_at",
    )

    list_filter = (
        "leave_date",
        "staff",
    )

    search_fields = (
        "staff__name",
        "reason",
    )

    ordering = (
        "leave_date",
    )

    readonly_fields = (
        "created_at",
    )

    list_per_page = 25

    autocomplete_fields = (
        "staff",
    )


# =========================================================
# BOOKING ADMIN
# CRM STYLE BOOKING MANAGEMENT
# =========================================================

class BookingAdmin(admin.ModelAdmin):
    from .admin_forms import AdminBookingForm
    form = AdminBookingForm

    class Media:
        js = ("js/admin-booking.js",)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method == "POST":
            from django.db import transaction
            with transaction.atomic():
                list(Staff.objects.select_for_update().order_by("pk"))
                list(Room.objects.select_for_update().order_by("pk"))
                return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        from .services.bookings import save_booking
        saved = save_booking(form)
        obj.__dict__.update(saved.__dict__)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "customer":
            from django.contrib.auth import get_user_model
            kwargs["queryset"] = get_user_model().objects.filter(is_staff=False, is_superuser=False, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


    # =====================================================
    # LIST DISPLAY
    # =====================================================

    list_display = (
        "booking_id",
        "customer_name",
        "customer_phone",
        "service_name",
        "duration_display",
        "appointment_datetime",
        "staff_name",
        "room_name",
        "booking_price",
        "booking_status",
        "whatsapp_status",
        "whatsapp_button",
        "bill_button",
    )

    # =====================================================
    # FILTERS
    # =====================================================

    list_filter = (
        "status",
        "appointment_date",
        "service",
        "staff",
        "room",
        "whatsapp_sent",
        "whatsapp_last_status",
    )

    # =====================================================
    # SEARCH
    # =====================================================

    search_fields = (
        "name",
        "phone",
        "email",
        "service__name",
        "staff__name",
        "room__name",
    )

    # =====================================================
    # ORDERING
    # =====================================================

    ordering = (
        "appointment_date",
        "appointment_time",
    )

    # =====================================================
    # PERFORMANCE
    # =====================================================

    list_select_related = (
        "service",
        "staff",
        "room",
    )

    # =====================================================
    # PAGINATION
    # =====================================================

    list_per_page = 25

    # =====================================================
    # DATE NAVIGATION
    # =====================================================

    date_hierarchy = "appointment_date"

    # =====================================================
    # FORM FEATURES
    # =====================================================

    save_on_top = True

    autocomplete_fields = (
        "service",
        "staff",
        "room",
    )

    # =====================================================
    # READONLY FIELDS
    # =====================================================

    readonly_fields = (
        "selected_duration",
        "selected_price",
        "end_time",
        "whatsapp_sent",
        "whatsapp_last_status",
        "created_at",
        "updated_at",
    )

    # =====================================================
    # EMPTY VALUE
    # =====================================================

    empty_value_display = "—"

    # =====================================================
    # ADMIN ACTIONS
    # =====================================================

    actions = (
        "complete_bookings",
        "cancel_bookings",
    )

    # =====================================================
    # BOOKING ID
    # =====================================================

    @admin.display(
        description="ID",
        ordering="id",
    )
    def booking_id(self, obj):

        try:

            url = reverse(
                "sukoon_admin:spa_booking_change",
                args=[obj.pk],
            )

        except Exception:

            url = "#"

        return format_html(
            '<a href="{}"><strong>#{}</strong></a>',
            url,
            obj.pk,
        )

    # =====================================================
    # CUSTOMER
    # =====================================================

    @admin.display(
        description="Customer",
        ordering="name",
    )
    def customer_name(self, obj):

        try:

            url = reverse(
                "sukoon_admin:spa_booking_change",
                args=[obj.pk],
            )

        except Exception:

            url = "#"

        return format_html(
            '<a href="{}"><strong>{}</strong></a>',
            url,
            obj.name,
        )

    # =====================================================
    # PHONE
    # =====================================================

    @admin.display(
        description="Phone",
        ordering="phone",
    )
    def customer_phone(self, obj):

        if not obj.phone:
            return "—"

        return format_html(
            '<a href="tel:{}">{}</a>',
            obj.phone,
            obj.phone,
        )

    # =====================================================
    # SERVICE
    # =====================================================

    @admin.display(
        description="Service",
        ordering="service__name",
    )
    def service_name(self, obj):

        if not obj.service:
            return "—"

        return obj.service.name

    # =====================================================
    # DURATION
    # =====================================================

    @admin.display(
        description="Duration",
        ordering="selected_duration",
    )
    def duration_display(self, obj):

        if obj.selected_duration is None:
            return "—"

        return format_html(
            "<strong>{} min</strong>",
            obj.selected_duration,
        )

    # =====================================================
    # APPOINTMENT
    # =====================================================

    @admin.display(
        description="Appointment",
        ordering="appointment_date",
    )
    def appointment_datetime(self, obj):

        if not obj.appointment_date:
            return "—"

        date_value = obj.appointment_date.strftime(
            "%d %b %Y"
        )

        if not obj.appointment_time:

            return format_html(
                "<strong>{}</strong>",
                date_value,
            )

        time_value = obj.appointment_time.strftime(
            "%I:%M %p"
        )

        if obj.end_time:

            end_value = obj.end_time.strftime(
                "%I:%M %p"
            )

            return format_html(
                "<strong>{}</strong><br>"
                "<span style='color:#666;'>{} – {}</span>",
                date_value,
                time_value,
                end_value,
            )

        return format_html(
            "<strong>{}</strong><br>"
            "<span style='color:#666;'>{}</span>",
            date_value,
            time_value,
        )

    # =====================================================
    # STAFF
    # =====================================================

    @admin.display(
        description="Staff",
        ordering="staff__name",
    )
    def staff_name(self, obj):

        if not obj.staff:

            return mark_safe(
                '<span style="color:#999;">Unassigned</span>'
            )

        return obj.staff.name

    # =====================================================
    # ROOM
    # =====================================================

    @admin.display(
        description="Room",
        ordering="room__name",
    )
    def room_name(self, obj):

        if not obj.room:

            return mark_safe(
                '<span style="color:#999;">Unassigned</span>'
            )

        return obj.room.name

    # =====================================================
    # PRICE
    # =====================================================

    @admin.display(
        description="Amount",
        ordering="selected_price",
    )
    def booking_price(self, obj):

        if obj.selected_price is None:

            return mark_safe(
                '<span style="color:#999;">—</span>'
            )

        return format_html(
            "<strong>₹{}</strong>",
            obj.selected_price,
        )

    # =====================================================
    # BOOKING STATUS
    # =====================================================

    @admin.display(
        description="Status",
        ordering="status",
    )
    def booking_status(self, obj):

        status = obj.status or ""

        labels = {
            "confirmed": (
                "Confirmed",
                "#155724",
                "#d4edda",
            ),
            "completed": (
                "Completed",
                "#004085",
                "#cce5ff",
            ),
            "cancelled": (
                "Cancelled",
                "#721c24",
                "#f8d7da",
            ),
        }

        label, text_color, background = labels.get(
            status,
            (
                status.title() if status else "Unknown",
                "#333",
                "#eee",
            ),
        )

        return format_html(
            '<span style="'
            'display:inline-block;'
            'padding:4px 9px;'
            'border-radius:20px;'
            'font-size:12px;'
            'font-weight:600;'
            'color:{};'
            'background:{};'
            '">'
            '{}'
            '</span>',
            text_color,
            background,
            label,
        )

    # =====================================================
    # WHATSAPP STATUS
    # =====================================================

    @admin.display(
        description="WhatsApp",
    )
    def whatsapp_status(self, obj):

        if obj.whatsapp_sent:

            return mark_safe(
                '<span style="'
                'display:inline-block;'
                'padding:4px 9px;'
                'border-radius:20px;'
                'font-size:12px;'
                'font-weight:600;'
                'color:#155724;'
                'background:#d4edda;'
                '">'
                'Sent'
                '</span>'
            )

        if obj.whatsapp_last_status:

            return format_html(
                '<span style="'
                'display:inline-block;'
                'padding:4px 9px;'
                'border-radius:20px;'
                'font-size:12px;'
                'font-weight:600;'
                'color:#856404;'
                'background:#fff3cd;'
                '">'
                '{}'
                '</span>',
                obj.whatsapp_last_status,
            )

        return mark_safe(
            '<span style="color:#999;">Not Sent</span>'
        )

    # =====================================================
    # WHATSAPP BUTTON
    # =====================================================

    @admin.display(
        description="WhatsApp",
    )
    def whatsapp_button(self, obj):

        if not obj.phone:
            return "—"

        phone = "".join(
            character
            for character in obj.phone
            if character.isdigit()
        )

        # -------------------------------------------------
        # INDIA NUMBER HANDLING
        # -------------------------------------------------

        if len(phone) == 10:
            phone = "91" + phone

        service_name = (
            obj.service.name
            if obj.service
            else "N/A"
        )

        appointment_date = (
            obj.appointment_date.strftime("%d %b %Y")
            if obj.appointment_date
            else "N/A"
        )

        appointment_time = (
            obj.appointment_time.strftime("%I:%M %p")
            if obj.appointment_time
            else "N/A"
        )

        duration = (
            f"{obj.selected_duration} minutes"
            if obj.selected_duration
            else "N/A"
        )

        status = (
            obj.status.title()
            if obj.status
            else "Confirmed"
        )

        message = (
            f"Hello {obj.name},\n\n"
            f"This is Sukoon Wellness & Spa.\n\n"
            f"Your appointment details:\n"
            f"Booking ID: #{obj.id}\n"
            f"Service: {service_name}\n"
            f"Duration: {duration}\n"
            f"Date: {appointment_date}\n"
            f"Time: {appointment_time}\n"
            f"Status: {status}\n\n"
            f"Thank you for choosing "
            f"Sukoon Wellness & Spa."
        )

        whatsapp_url = (
            f"https://wa.me/{phone}"
            f"?text={quote(message)}"
        )

        return format_html(
            '<a href="{}" target="_blank" '
            'rel="noopener noreferrer" '
            'style="'
            'display:inline-block;'
            'padding:5px 10px;'
            'border-radius:5px;'
            'background:#25D366;'
            'color:white;'
            'font-size:12px;'
            'font-weight:600;'
            'text-decoration:none;'
            '">'
            'Open'
            '</a>',
            whatsapp_url,
        )

    # =====================================================
    # BILL BUTTON
    # =====================================================

    @admin.display(
        description="Bill",
    )
    def bill_button(self, obj):

        try:

            url = reverse(
                "booking_bill",
                args=[obj.pk],
            )

            return format_html(
                '<a href="{}" target="_blank" '
                'style="'
                'display:inline-block;'
                'padding:5px 10px;'
                'border-radius:5px;'
                'background:#c9a96e;'
                'color:#111;'
                'font-size:12px;'
                'font-weight:600;'
                'text-decoration:none;'
                '">'
                'Bill'
                '</a>',
                url,
            )

        except Exception:

            return mark_safe(
                '<span style="color:#999;">Bill</span>'
            )

    # =====================================================
    # COMPLETE BOOKINGS
    # =====================================================

    @admin.action(
        description="Mark selected confirmed bookings as completed"
    )
    def complete_bookings(
        self,
        request,
        queryset,
    ):

        from .services.status_actions import apply_status_action
        apply_status_action(self, request, queryset, "completed")

    # =====================================================
    # CANCEL BOOKINGS
    # =====================================================

    @admin.action(
        description="Cancel selected bookings"
    )
    def cancel_bookings(
        self,
        request,
        queryset,
    ):

        from .services.status_actions import apply_status_action
        apply_status_action(self, request, queryset, "cancelled")

    # =====================================================
    # FIELDSETS
    # =====================================================

    fieldsets = (

        (
            "Customer Information",
            {
                "fields": (
                    "customer",
                    "name",
                    "phone",
                    "email",
                )
            },
        ),

        (
            "Service Selection",
            {
                "fields": (
                    "service",
                    "duration",
                    "package_credit",
                    "selected_duration",
                    "selected_price",
                )
            },
        ),

        (
            "Appointment",
            {
                "fields": (
                    "appointment_date",
                    "appointment_time",
                    "end_time",
                )
            },
        ),

        (
            "Resource Assignment",
            {
                "fields": (
                    "staff",
                    "secondary_staff",
                    "room",
                )
            },
        ),

        (
            "Customer Message",
            {
                "fields": (
                    "message",
                )
            },
        ),

        (
            "Booking Status",
            {
                "fields": (
                    "status",
                )
            },
        ),

        (
            "WhatsApp Notification",
            {
                "fields": (
                    "whatsapp_sent",
                    "whatsapp_last_status",
                )
            },
        ),

        ("Payment Details", {"fields": ("discount_amount", "amount_paid", "payment_mode", "payment_reference")}),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


# =========================================================
# CUSTOM ADMIN SITE REGISTRATION
# =========================================================

sukoon_admin_site.register(
    ServiceCategory,
    ServiceCategoryAdmin,
)

sukoon_admin_site.register(
    Service,
    ServiceAdmin,
)

# IMPORTANT:
# ServiceOption is NOT registered separately.
#
# It is managed inside ServiceAdmin through
# ServiceOptionInline.
#
# DO NOT ADD:
#
# sukoon_admin_site.register(
#     ServiceOption,
#     ServiceOptionAdmin,
# )


sukoon_admin_site.register(
    Staff,
    StaffAdmin,
)

sukoon_admin_site.register(
    Room,
    RoomAdmin,
)

sukoon_admin_site.register(
    StaffLeave,
    StaffLeaveAdmin,
)

sukoon_admin_site.register(
    Booking,
    BookingAdmin,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from .models import Enquiry, CustomerProfile, Notification
from django.contrib.admin.utils import model_ngettext

class CustomerUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "email", "is_active", "is_staff")
    def has_module_permission(self, request):
        return request.user.is_superuser
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_add_permission(self, request):
        return request.user.is_superuser
    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "phone", "city", "status", "created_at")
    search_fields = ("name", "phone", "email", "city")
    list_filter = ("kind", "status", "created_at")
    readonly_fields = ("created_at",)
    list_per_page = 25

class NotificationAdmin(admin.ModelAdmin):
    list_display = ("channel", "subject", "status", "due_at", "attempts")
    list_filter = ("channel", "status")
    readonly_fields = ("booking", "dedupe_key", "channel", "recipient", "subject", "message", "due_at", "status", "attempts", "last_error", "sent_at")
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


class PackageCreditInline(admin.TabularInline):
    model = PackageCredit
    extra = 0
    can_delete = False
    fields = ("label", "max_duration", "total_sessions", "used", "reserved", "available")
    readonly_fields = fields
    def has_add_permission(self, request, obj=None): return False


class PackageEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("customer_name", "phone", "package_name", "purchased_at")
    search_fields = ("customer_name", "phone", "package_name")
    readonly_fields = ("invoice_line", "customer", "customer_name", "phone", "package_name", "purchased_at")
    inlines = (PackageCreditInline,)
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


class CustomerRecordAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "updated_at")
    search_fields = ("name", "phone")


sukoon_admin_site.register(PackageEnrollment, PackageEnrollmentAdmin)
sukoon_admin_site.register(CustomerRecord, CustomerRecordAdmin)

sukoon_admin_site.register(get_user_model(), CustomerUserAdmin)
sukoon_admin_site.register(Group)
sukoon_admin_site.register(Enquiry, EnquiryAdmin)
sukoon_admin_site.register(Notification, NotificationAdmin)
