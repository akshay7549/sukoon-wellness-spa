
from django.apps import AppConfig


class SpaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "spa"
    verbose_name = "Sukoon Wellness & Spa"

    def ready(self):
        from . import crm_signals
