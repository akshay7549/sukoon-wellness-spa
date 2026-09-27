
from django.urls import path

from . import views


app_name = "payments"


urlpatterns = [

    # =========================================================
    # PAYMENT PAGE
    # =========================================================

    path(
        "payment/<int:booking_id>/",
        views.payment_page,
        name="payment_page",
    ),


    # =========================================================
    # CREATE RAZORPAY ORDER
    # =========================================================

    path(
        "create-order/<int:booking_id>/",
        views.create_order,
        name="create_order",
    ),


    # =========================================================
    # VERIFY RAZORPAY PAYMENT
    # =========================================================

    path(
        "verify/",
        views.verify_payment,
        name="verify_payment",
    ),

]
