from django.urls import path

from . import views


# =========================================================
# SUKOON WELLNESS & SPA — URL ROUTES
# =========================================================

urlpatterns = [

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