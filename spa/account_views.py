from urllib.parse import urlsplit

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction, IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .account_forms import CustomerRegistrationForm
from .models import Booking, CustomerProfile


def account_destination(user):
    return "sukoon_admin:index" if user.is_staff else "my_bookings"


def remember_guest_booking(request, booking):
    if not request.user.is_authenticated:
        booking_ids = request.session.get("guest_booking_ids", [])
        request.session["guest_booking_ids"] = (booking_ids + [booking.pk])[-50:]


def booking_initial(request):
    if request.user.is_authenticated:
        return {
            "name": request.user.first_name or request.user.get_username(),
            "email": request.user.email,
        }
    return {}


def claim_session_bookings(request):
    """Only attach guest bookings created in this authenticated browser session."""
    booking_ids = request.session.pop("guest_booking_ids", [])
    if booking_ids:
        Booking.objects.filter(pk__in=booking_ids, customer__isnull=True).update(
            customer=request.user,
        )


@method_decorator(never_cache, name="dispatch")
class AccountLoginView(LoginView):
    template_name = "spa/sign_in.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        target = self.get_redirect_url()
        if target and not (
            not self.request.user.is_staff
            and urlsplit(target).path.startswith("/admin/")
        ):
            return target
        return reverse(account_destination(self.request.user))

    def form_valid(self, form):
        response = super().form_valid(form)
        claim_session_bookings(self.request)
        return response


class AccountLogoutView(LogoutView):
    next_page = "login"


@never_cache
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect(account_destination(request.user))
    form = CustomerRegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
                CustomerProfile.objects.create(user=user, email_address=user.email.casefold())
                login(request, user)
                claim_session_bookings(request)
                from .email_views import queue_verification
                queue_verification(user)
            return redirect("my_bookings")
        except IntegrityError:
            form.add_error("email", "This email is already registered. Sign in or request a password reset.")
    return render(request, "spa/register.html", {"form": form})


@never_cache
@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(customer=request.user).select_related(
        "service",
    ).order_by("-appointment_date", "-appointment_time")
    from .customer_views import can_change
    bookings = list(bookings)
    for booking in bookings:
        booking.can_change = can_change(booking)
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    return render(request, "spa/my_bookings.html", {"bookings": bookings, "profile":profile})
