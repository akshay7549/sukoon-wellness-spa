from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required, login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import LoyaltyPolicy, LoyaltyWallet, Referral, CustomerRecord
from .loyalty_forms import PolicyForm, RedemptionForm, PurchasePointsForm, ReferralForm, ReferralReviewForm
from .services.loyalty import purchase_points, redeem_points, record_referral, review_referral, activate_wallet


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_loyaltywallet", raise_exception=True)
def rewards(request):
    query = request.GET.get("q", "").strip()[:100]
    contacts = CustomerRecord.objects.select_related("account", "loyalty_wallet").order_by("name", "phone")
    if query: contacts = contacts.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    return render(request, "admin/rewards.html", {"policy": LoyaltyPolicy.objects.filter(pk=1).first(), "page": Paginator(contacts, 25).get_page(request.GET.get("page")), "query": query})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.change_loyaltypolicy", raise_exception=True)
@require_http_methods(["GET", "POST"])
def rewards_policy(request):
    policy = LoyaltyPolicy.objects.filter(pk=1).first() or LoyaltyPolicy(pk=1)
    form = PolicyForm(request.POST if request.method == "POST" else None, instance=policy)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Rewards policy saved. Existing awards keep their expiry dates.")
        return redirect("loyalty_rewards")
    return render(request, "admin/workflow_form.html", {"form": form, "heading": "Rewards Policy", "intro": "Configure purchase points, referral rewards and expiry. Points are redeemed for the rewards described in your terms; invoice amounts remain separately recorded.", "submit": "Save policy"})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_loyaltywallet", raise_exception=True)
@require_http_methods(["GET", "POST"])
def wallet_detail(request, contact_id):
    contact = get_object_or_404(CustomerRecord.objects.select_related("account"), pk=contact_id)
    purchase_form = PurchasePointsForm(request.POST if request.method == "POST" and request.POST.get("action") == "purchase" else None, contact=contact)
    redeem_form = RedemptionForm(request.POST if request.method == "POST" and request.POST.get("action") == "redeem" else None)
    referral_form = ReferralForm(request.POST if request.method == "POST" and request.POST.get("action") == "referral" else None)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "activate":
            if not request.user.has_perm("spa.add_loyaltywallet"): raise PermissionDenied
            try:
                activate_wallet(contact.pk)
                messages.success(request, "Rewards account and referral code created.")
                return redirect("loyalty_wallet", contact_id=contact.pk)
            except ValidationError as exc: messages.error(request, " ".join(exc.messages))
            action = None
        forms = {"purchase": (purchase_form, "spa.add_loyaltyaward"), "redeem": (redeem_form, "spa.add_loyaltyspend"), "referral": (referral_form, "spa.add_referral")}
        if action is not None and (action not in forms or not request.user.has_perm(forms[action][1])): raise PermissionDenied
        form = forms[action][0] if action else None
        if form and form.is_valid():
            try:
                if action == "purchase": purchase_points(contact.pk, form.cleaned_data["payment"].pk, request.user)
                elif action == "redeem": redeem_points(contact.pk, actor=request.user, **form.cleaned_data)
                else: record_referral(contact.pk, form.cleaned_data["code"], request.user)
                messages.success(request, "Reward record saved.")
                return redirect("loyalty_wallet", contact_id=contact.pk)
            except ValidationError as exc: form.add_error(None, exc)
    wallet = LoyaltyWallet.objects.filter(contact=contact).first()
    return render(request, "admin/reward_wallet.html", {"contact": contact, "wallet": wallet, "policy": LoyaltyPolicy.objects.filter(pk=1).first(), "purchase_form": purchase_form, "redeem_form": redeem_form, "referral_form": referral_form,
                  "awards": Paginator(wallet.awards.all(), 25).get_page(request.GET.get("page")) if wallet else [], "spends": wallet.spends.order_by("-created_at")[:25] if wallet else []})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.view_referral", raise_exception=True)
def referrals(request):
    records = Referral.objects.select_related("referrer__contact", "referred", "qualifying_invoice", "reviewed_by").order_by("-created_at")
    return render(request, "admin/referrals.html", {"page": Paginator(records, 25).get_page(request.GET.get("page"))})


@never_cache
@staff_member_required(login_url="login")
@permission_required("spa.change_referral", raise_exception=True)
@require_http_methods(["GET", "POST"])
def referral_review(request, referral_id):
    record = get_object_or_404(Referral.objects.select_related("referred", "referrer__contact"), pk=referral_id)
    form = ReferralReviewForm(request.POST if request.method == "POST" else None, referral=record)
    if request.method == "POST" and form.is_valid():
        if not request.user.has_perm("spa.add_loyaltyaward"): raise PermissionDenied
        try:
            data = form.cleaned_data
            review_referral(record.pk, getattr(data["invoice"], "pk", None), data["action"], data["note"], request.user)
            messages.success(request, "Referral reviewed.")
            return redirect("loyalty_referrals")
        except ValidationError as exc: form.add_error(None, exc)
    return render(request, "admin/workflow_form.html", {"form": form, "heading": "Review Referral", "intro": f"{record.referrer.contact.name} referred {record.referred.name}. Rewards require the first paid invoice for a completed visit, fully settled.", "submit": "Save review"})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def my_rewards(request):
    if request.user.is_staff: return redirect("loyalty_rewards")
    contacts = CustomerRecord.objects.filter(account=request.user).order_by("pk")
    policy = LoyaltyPolicy.objects.filter(pk=1).first()
    form = ReferralForm(request.POST if request.method == "POST" else None)
    selected = contacts.first()
    if request.method == "POST" and request.POST.get("action") == "activate":
        try:
            if not selected: raise ValidationError("Ask reception to verify and link your account first.")
            activate_wallet(selected.pk)
            return redirect("my_rewards")
        except ValidationError as exc: messages.error(request, " ".join(exc.messages))
    elif request.method == "POST" and form.is_valid():
        try:
            if not selected: raise ValidationError("Ask reception to verify your mobile number and link your account first.")
            record_referral(selected.pk, form.cleaned_data["code"])
            messages.success(request, "Referral code recorded. Reception will review it after your first paid visit.")
            return redirect("my_rewards")
        except ValidationError as exc: form.add_error(None, exc)
    wallets = list(LoyaltyWallet.objects.filter(contact__in=contacts).select_related("contact"))
    for wallet in wallets:
        wallet.share_url = settings.PUBLIC_SITE_URL.rstrip("/") + "/my-rewards/?ref=" + wallet.code
    if not request.method == "POST" and request.GET.get("ref"): form.initial["code"] = request.GET["ref"][:16]
    return render(request, "spa/my_rewards.html", {"wallets": wallets, "policy": policy, "form": form, "verified": bool(selected)})
