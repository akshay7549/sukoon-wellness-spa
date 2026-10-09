from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordResetView
from django.core import signing
from django.db import IntegrityError
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .models import CustomerProfile
from .notifications import queue_email
from django.contrib.auth import get_user_model
import hashlib

def verification_token(user):
    return signing.dumps({"id":user.pk,"email":user.email.casefold(),"password":hashlib.sha256(user.password.encode()).hexdigest()},salt="customer-email-verification")

def queue_verification(user):
    if settings.EMAIL_ENABLED:
        token = verification_token(user)
        url = settings.PUBLIC_SITE_URL + "/verify-email/" + token + "/"
        queue_email(f"verification:{token}",user.email,"Verify your Sukoon email",f"Verify your email address using this link (valid for 24 hours):\n{url}\nIf you did not request this, ignore this email.")

@never_cache
@login_required
@require_POST
def send_verification(request):
    if not settings.EMAIL_ENABLED:
        messages.info(request,"Email verification will be available once our email service is connected.")
    else:
        profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
        if not profile.email_verified:
            queue_verification(request.user)
            messages.success(request,"Verification email queued. Check your inbox shortly.")
    return redirect("my_bookings")

@never_cache
def verify_email(request, token):
    try:
        data = signing.loads(token,salt="customer-email-verification",max_age=86400)
        user = get_object_or_404(get_user_model(),pk=data["id"],is_active=True)
        if user.email.casefold()!=data["email"] or hashlib.sha256(user.password.encode()).hexdigest()!=data["password"]:
            raise signing.BadSignature()
        profile, _ = CustomerProfile.objects.get_or_create(user=user)
        profile.email_address=user.email.casefold()
        profile.email_verified=True
        profile.save()
    except (signing.BadSignature, IntegrityError, KeyError):
        return render(request,"spa/account_notice.html",{"notice_title":"Verification link unavailable","notice":"This link expired or could not be verified. Sign in to request a new link, or contact reception."},status=400)
    return render(request,"spa/account_notice.html",{"notice_title":"Email verified","notice":"Your email address has been verified."})

class CustomerPasswordResetView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    extra_email_context = {"domain":settings.PUBLIC_SITE_URL.split("://",1)[-1],"protocol":"https"}
    def form_valid(self, form):
        if not settings.EMAIL_ENABLED:
            return render(self.request,"spa/account_notice.html",{"notice_title":"Password assistance","notice":"Email recovery is not connected yet. Please contact Sukoon reception on +91 90316 40551 for account assistance."})
        from django.contrib.auth.tokens import default_token_generator
        from django.template.loader import render_to_string
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        from django.http import HttpResponseRedirect
        for user in form.get_users(form.cleaned_data["email"]):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            context = {"user":user,"uid":uid,"token":token,"protocol":"https","domain":settings.PUBLIC_SITE_URL.split("://",1)[-1]}
            body = render_to_string(self.email_template_name, context)
            queue_email(f"reset:{uid}:{token}", user.email, "Reset your Sukoon account password", body)
        return HttpResponseRedirect(self.get_success_url())
