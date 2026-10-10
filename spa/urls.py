from django.urls import path

from . import views
from .account_views import AccountLoginView, AccountLogoutView, my_bookings, register
from .connect_views import connect
from . import customer_views, email_views, public_views
from .business_views import invoice_print
from .loyalty_views import my_rewards
from django.contrib.auth import views as auth_views


# =========================================================
# SUKOON WELLNESS & SPA — URL ROUTES
# =========================================================

urlpatterns = [
    path("my-rewards/", my_rewards, name="my_rewards"),
    path("invoices/<int:invoice_id>/print/",invoice_print,name="invoice_print"),
    path("api/service-options/",views.service_options,name="service_options"),
    path("privacy/", public_views.privacy, name="privacy"),
    path("cancellation-policy/", public_views.cancellation_policy, name="cancellation_policy"),
    path("sitemap.xml", public_views.sitemap_xml, name="sitemap"),
    path("robots.txt", public_views.robots, name="robots"),
    path("password-reset/", email_views.CustomerPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("verify-email/send/", email_views.send_verification, name="send_verification"),
    path("verify-email/<str:token>/", email_views.verify_email, name="verify_email"),
    path("my-bookings/<int:booking_id>/cancel/", customer_views.cancel_booking, name="cancel_booking"),
    path("my-bookings/<int:booking_id>/reschedule/", customer_views.reschedule_booking, name="reschedule_booking"),


    path("connect/", connect, name="connect"),

    path("login/", AccountLoginView.as_view(), name="login"),
    path("sign-up/", register, name="register"),
    path("logout/", AccountLogoutView.as_view(), name="logout"),
    path("my-bookings/", my_bookings, name="my_bookings"),

    # =====================================================
    # HOME
    # =====================================================

    path(
        "",
        views.home,
        name="home",
    ),


    # =====================================================
    # ABOUT
    # =====================================================

    path(
        "about/",
        views.about,
        name="about",
    ),


    # =====================================================
    # SERVICES
    # =====================================================

    path(
        "services/",
        views.services,
        name="services",
    ),


    # =====================================================
    # GALLERY
    # =====================================================

    path(
        "gallery/",
        views.gallery,
        name="gallery",
    ),


    # =====================================================
    # BOOKING
    # =====================================================

    path(
        "book/",
        views.booking,
        name="booking",
    ),


    # =====================================================
    # BOOKING SUCCESS
    # =====================================================

    path(
        "booking/success/<int:booking_id>/",
        views.booking_success,
        name="booking_success",
    ),


    # =====================================================
    # CONTACT
    # =====================================================

    path(
        "contact/",
        views.contact,
        name="contact",
    ),


    # =====================================================
    # FRANCHISE
    # =====================================================
    # Premium franchise landing page.
    #
    # Template:
    # spa/templates/spa/franchise.html
    #
    # View will be added in views.py.

    path(
        "franchise/",
        views.franchise,
        name="franchise",
    ),


    # =====================================================
    # BOOKING AVAILABILITY API
    # =====================================================

    path(
        "api/available-slots/",
        views.available_slots,
        name="available_slots",
    ),

]
