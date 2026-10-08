
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
# SERVICE ADMIN
# =========================================================

class ServiceAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "price",
        "duration",
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


# =========================================================
# SERVICE OPTION ADMIN
# =========================================================

class ServiceOptionAdmin(admin.ModelAdmin):

    list_display = (
        "service",
        "duration",
        "price",
        "is_active",
    )

    list_filter = (
        "service",
        "is_active",
    )

    search_fields = (
        "service__name",
    )

    ordering = (
        "service",
        "duration",
    )

    list_per_page = 25

    autocomplete_fields = (
        "service",
    )


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

    list_display = (
        "name",
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

    # =====================================================
    # LIST DISPLAY
    # =====================================================

    list_display = (
        "booking_id",
        "customer_name",
        "customer_phone",
        "service_name",
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

        updated = queryset.filter(
            status="confirmed"
        ).update(
            status="completed"
        )

        if updated:

            self.message_user(
                request,
                (
                    f"{updated} booking(s) marked "
                    f"as completed."
                ),
                messages.SUCCESS,
            )

        else:

            self.message_user(
                request,
                "No confirmed bookings were selected.",
                messages.WARNING,
            )

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

        cancellable = queryset.filter(
            status="confirmed"
        )

        count = cancellable.count()

        cancellable.update(
            status="cancelled"
        )

        if count:

            self.message_user(
                request,
                f"{count} booking(s) cancelled.",
                messages.SUCCESS,
            )

        else:

            self.message_user(
                request,
                "No confirmed bookings were selected.",
                messages.WARNING,
            )

    # =====================================================
    # FIELDSETS
    # =====================================================

    fieldsets = (

        (
            "Customer Information",
            {
                "fields": (
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

sukoon_admin_site.register(
    ServiceOption,
    ServiceOptionAdmin,
)

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
