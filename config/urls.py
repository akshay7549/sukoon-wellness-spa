from django.urls import include, path

from spa.admin_site import sukoon_admin_site


urlpatterns = [

    # =========================================================
    # SUKOON ADMIN
    # =========================================================

    path(
        "admin/",
        sukoon_admin_site.urls,
    ),

    # =========================================================
    # WEBSITE
    # =========================================================

    path(
        "",
        include("spa.urls"),
    ),

    # =========================================================
    # PAYMENTS
    # =========================================================

    path(
        "payments/",
        include("payments.urls"),
    ),
]