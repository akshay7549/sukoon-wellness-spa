from django.contrib import admin
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "booking",
        "amount",
        "currency",
        "status",
        "razorpay_order_id",
        "razorpay_payment_id",
        "paid_at",
        "created_at",
    )

    list_filter = (
        "status",
        "currency",
        "paid_at",
        "created_at",
    )

    search_fields = (
        "razorpay_order_id",
        "razorpay_payment_id",
        "booking__name",
        "booking__phone",
        "booking__email",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "paid_at",
        "razorpay_order_id",
        "razorpay_payment_id",
        "razorpay_signature",
    )

    list_per_page = 25

    fieldsets = (
        (
            "Payment Information",
            {
                "fields": (
                    "booking",
                    "amount",
                    "currency",
                    "status",
                ),
            },
        ),
        (
            "Razorpay Information",
            {
                "fields": (
                    "razorpay_order_id",
                    "razorpay_payment_id",
                    "razorpay_signature",
                ),
            },
        ),
        (
            "Payment Timeline",
            {
                "fields": (
                    "created_at",
                    "paid_at",
                    "updated_at",
                ),
            },
        ),
    )