import hashlib
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import RateLimitBucket

def allow_attempt(scope, identity, limit=10, seconds=900):
    key = hashlib.sha256(f"{scope}:{identity}".encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        RateLimitBucket.objects.get_or_create(key=key, defaults={"expires_at":now + timedelta(seconds=seconds)})
        bucket = RateLimitBucket.objects.select_for_update().get(key=key)
        if bucket.expires_at <= now:
            bucket.attempts = 0
            bucket.expires_at = now + timedelta(seconds=seconds)
        if bucket.attempts >= limit:
            return False
        bucket.attempts += 1
        bucket.save(update_fields=["attempts", "expires_at"])
    return True

class SubmissionRateLimitMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        routes = {"/login/": (20, 900), "/admin/login/": (20, 900), "/sign-up/": (5, 3600),
                  "/password-reset/": (5, 3600), "/verify-email/send/": (5, 3600),
                  "/book/": (10, 3600), "/": (10, 3600), "/contact/": (10, 3600), "/franchise/": (5, 3600)}
        if request.method == "POST" and request.path in routes:
            limit, seconds = routes[request.path]
            allowed = allow_attempt("ip:" + request.path, request.META.get("REMOTE_ADDR", "unknown"), limit, seconds)
            if allowed and request.path in ("/login/", "/admin/login/"):
                allowed = allow_attempt("login", request.POST.get("username", "").strip().casefold(), 5, 900)
            if not allowed:
                from django.shortcuts import render
                response = render(request, "spa/account_notice.html", {"notice_title":"Please try again later", "notice":"Too many attempts. Please wait before trying again."}, status=429)
                response["Retry-After"] = str(seconds)
                response["Cache-Control"] = "no-store"
                return response
        return self.get_response(request)
