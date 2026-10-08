from django.contrib.admin import AdminSite


class SukoonAdminSite(AdminSite):
    """
    Custom Django AdminSite for Sukoon Wellness & Spa.

    /admin/ is the central CRM dashboard.
    """

    # =====================================================
    # BRANDING
    # =====================================================

    site_header = "Sukoon Wellness & Spa"
    site_title = "Sukoon Admin"
    index_title = "Sukoon CRM Dashboard"

    # Main website
    site_url = "/"

    # Django navigation sidebar
    enable_nav_sidebar = True

    # =====================================================
    # CUSTOM ADMIN INDEX
    # =====================================================

    def index(self, request, extra_context=None):
        """
        Use the custom Sukoon CRM dashboard as the
        main /admin/ homepage.
        """

        from .admin_dashboard import admin_dashboard

        return admin_dashboard(
            request,
        )


# =========================================================
# SUKOON ADMIN SITE
# =========================================================

sukoon_admin_site = SukoonAdminSite(
    name="sukoon_admin",
)