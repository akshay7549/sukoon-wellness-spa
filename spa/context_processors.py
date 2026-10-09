from django.conf import settings
def site_context(request):
    return {"public_site_url":settings.PUBLIC_SITE_URL, "canonical_url":settings.PUBLIC_SITE_URL + request.path, "email_enabled":settings.EMAIL_ENABLED, "change_cutoff_hours":settings.CUSTOMER_CHANGE_CUTOFF_HOURS}
