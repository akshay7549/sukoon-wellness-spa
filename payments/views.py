from decimal import Decimal

import razorpay

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from spa.models import Booking
from .models import Payment


# =========================================================
# RAZORPAY CLIENT
# =========================================================

razorpay_client = razorpay.Client(
    auth=(
        settings.RAZORPAY_KEY_ID,
        settings.RAZORPAY_KEY_SECRET,
    )
)


# =========================================================
# PAYMENT PAGE
# =========================================================

def payment_page(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id
    )

    # -----------------------------------------------------
    # Check booking amount
    # -----------------------------------------------------

    if booking.selected_price is None:
        return render(
            request,
            "payments/payment.html",
            {
                "booking": booking,
                "payment_error": "Booking amount is not available.",
            }
        )

    # -----------------------------------------------------
    # Check if already paid
    # -----------------------------------------------------

    existing_payment = Payment.objects.filter(
        booking=booking,
        status="paid"
    ).first()

    if existing_payment:
        return render(
            request,
            "payments/payment.html",
            {
                "booking": booking,
                "already_paid": True,
                "payment": existing_payment,
            }
        )

    # -----------------------------------------------------
    # Only pending bookings can be paid
    # -----------------------------------------------------

    if booking.status != "pending":
        return render(
            request,
            "payments/payment.html",
            {
                "booking": booking,
                "payment_error": (
                    "This booking is no longer available for payment."
                ),
            }
        )

    # -----------------------------------------------------
    # Render payment page
    # -----------------------------------------------------

    return render(
        request,
        "payments/payment.html",
        {
            "booking": booking,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        }
    )


# =========================================================
# CREATE RAZORPAY ORDER
# =========================================================

@require_POST
def create_order(request, booking_id):

    booking = get_object_or_404(
        Booking,
        id=booking_id
    )

    # -----------------------------------------------------
    # Only pending bookings can create payment
    # -----------------------------------------------------

    if booking.status != "pending":
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "This booking is not available for payment."
                ),
            },
            status=400
        )

    # -----------------------------------------------------
    # Check booking price
    # -----------------------------------------------------

    if booking.selected_price is None:
        return JsonResponse(
            {
                "success": False,
                "message": "Booking price is not available.",
            },
            status=400
        )

    amount = Decimal(booking.selected_price)

    if amount <= 0:
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid booking amount.",
            },
            status=400
        )

    # -----------------------------------------------------
    # Check if already paid
    # -----------------------------------------------------

    existing_payment = Payment.objects.filter(
        booking=booking,
        status="paid"
    ).first()

    if existing_payment:
        return JsonResponse(
            {
                "success": False,
                "message": "This booking has already been paid.",
            },
            status=400
        )

    # -----------------------------------------------------
    # Razorpay uses paise
    # -----------------------------------------------------

    amount_in_paise = int(
        amount * Decimal("100")
    )

    # -----------------------------------------------------
    # Create Razorpay Order
    # -----------------------------------------------------

    try:

        razorpay_order = razorpay_client.order.create(
            {
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": f"booking_{booking.id}",
            }
        )

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Unable to create Razorpay order. "
                    "Please try again."
                ),
            },
            status=500
        )

    # -----------------------------------------------------
    # Save Payment
    # -----------------------------------------------------

    payment, created = Payment.objects.update_or_create(
        booking=booking,
        defaults={
            "amount": amount,
            "currency": "INR",
            "razorpay_order_id": razorpay_order["id"],
            "status": "created",
            "razorpay_payment_id": None,
            "razorpay_signature": None,
            "paid_at": None,
        },
    )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return JsonResponse(
        {
            "success": True,
            "payment_id": payment.id,
            "booking_id": booking.id,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "amount": amount_in_paise,
            "currency": "INR",
            "customer": {
                "name": booking.name,
                "email": booking.email or "",
                "phone": booking.phone,
            },
        }
    )


# =========================================================
# VERIFY RAZORPAY PAYMENT
# =========================================================

@csrf_exempt
@require_POST
def verify_payment(request):

    razorpay_order_id = request.POST.get(
        "razorpay_order_id"
    )

    razorpay_payment_id = request.POST.get(
        "razorpay_payment_id"
    )

    razorpay_signature = request.POST.get(
        "razorpay_signature"
    )

    # -----------------------------------------------------
    # Validate required data
    # -----------------------------------------------------

    if not all(
        [
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
        ]
    ):
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Missing Razorpay payment verification data."
                ),
            },
            status=400
        )

    # -----------------------------------------------------
    # Find payment
    # -----------------------------------------------------

    payment = get_object_or_404(
        Payment,
        razorpay_order_id=razorpay_order_id
    )

    # -----------------------------------------------------
    # Already verified
    # -----------------------------------------------------

    if payment.status == "paid":
        return JsonResponse(
            {
                "success": True,
                "message": "Payment is already verified.",
                "payment_id": payment.id,
                "booking_id": payment.booking.id,
                "booking_status": payment.booking.status,
            }
        )

    # -----------------------------------------------------
    # Verify Razorpay signature
    # -----------------------------------------------------

    try:

        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )

    except razorpay.errors.SignatureVerificationError:

        payment.status = "failed"

        payment.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Payment signature verification failed."
                ),
            },
            status=400
        )

    except Exception:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Payment verification failed. "
                    "Please contact support."
                ),
            },
            status=500
        )

    # -----------------------------------------------------
    # Payment verified successfully
    # -----------------------------------------------------

    payment.razorpay_payment_id = razorpay_payment_id
    payment.razorpay_signature = razorpay_signature
    payment.status = "paid"
    payment.paid_at = timezone.now()

    payment.save(
        update_fields=[
            "razorpay_payment_id",
            "razorpay_signature",
            "status",
            "paid_at",
            "updated_at",
        ]
    )

    # -----------------------------------------------------
    # Update booking status
    # -----------------------------------------------------

    booking = payment.booking

    if booking.status == "pending":

        booking.status = "confirmed"

        booking.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

    # -----------------------------------------------------
    # Final response
    # -----------------------------------------------------

    return JsonResponse(
        {
            "success": True,
            "message": "Payment verified successfully.",
            "payment_id": payment.id,
            "razorpay_payment_id": razorpay_payment_id,
            "booking_id": booking.id,
            "booking_status": booking.status,
        }
    )