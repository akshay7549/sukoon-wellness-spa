from django.urls import include, path

from spa.admin_site import sukoon_admin_site
from spa.bill_views import booking_bill


# =========================================================
# URL CONFIGURATION
# =========================================================

urlpatterns = [

    # =====================================================
    # BOOKING BILL
    # =====================================================

    path(
        "admin/booking/<int:booking_id>/bill/",
        booking_bill,
        name="booking_bill",
    ),

    # =====================================================
    # SUKOON CRM ADMIN
    # =====================================================
    #
    # Main admin dashboard:
    # http://127.0.0.1:1000/admin/
    #
    # The custom SukoonAdminSite handles the dashboard.
    #

    path(
        "admin/",
        sukoon_admin_site.urls,
    ),

    # =====================================================
    # CUSTOMER WEBSITE
    # =====================================================

    path(
        "",
        include("spa.urls"),
    ),
]
from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
