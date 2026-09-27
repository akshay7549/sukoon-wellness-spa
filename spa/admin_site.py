from django.contrib.admin import AdminSite


class SukoonAdminSite(AdminSite):
    """
    Custom AdminSite for Sukoon Wellness & Spa.

    /admin/ acts as the central CRM dashboard.
    """

    # =====================================================
    # BRANDING
    # =====================================================

    site_header = "Sukoon Wellness & Spa"
    site_title = "Sukoon Admin"
    index_title = "Dashboard"

    # Main website
    site_url = "/"

    # Django sidebar
    enable_nav_sidebar = True

    # =====================================================
    # CUSTOM ADMIN INDEX
    # =====================================================

    def index(self, request, extra_context=None):
        """
        Replace Django's default admin homepage
        with the Sukoon CRM dashboard.
        """

        from .admin_dashboard import admin_dashboard

        return admin_dashboard(request)


# =========================================================
# SUKOON ADMIN SITE
# =========================================================

sukoon_admin_site = SukoonAdminSite(
    name="sukoon_admin"
)