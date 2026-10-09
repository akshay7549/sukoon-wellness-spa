from django.contrib import messages
from django.core.exceptions import ValidationError

from .bookings import transition_booking


def apply_status_action(admin, request, queryset, status):
    changed = skipped = 0
    for pk in queryset.values_list("pk", flat=True):
        try:
            changed += bool(transition_booking(pk, status))
        except ValidationError:
            skipped += 1
    admin.message_user(request, f"{changed} booking(s) {status}." + (f" {skipped} future appointments skipped." if skipped else ""), messages.SUCCESS if changed else messages.WARNING)
