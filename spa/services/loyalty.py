from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from ..models import LoyaltyPolicy, LoyaltyWallet, LoyaltyAward, LoyaltySpend, Referral, CustomerRecord, Invoice, InvoicePayment


def policy_locked():
    policy, _ = LoyaltyPolicy.objects.get_or_create(pk=1)
    policy = LoyaltyPolicy.objects.select_for_update().get(pk=policy.pk)
    if not policy.enabled:
        raise ValidationError("Customer rewards are disabled. Ask the owner to configure and enable the policy.")
    return policy


def wallet_locked(contact_id):
    contact = CustomerRecord.objects.select_for_update().get(pk=contact_id)
    if not contact.account_id or not contact.account.is_active or contact.account.is_staff:
        raise ValidationError("Reception must verify and link an active customer account before rewards are used.")
    wallet, _ = LoyaltyWallet.objects.get_or_create(contact=contact)
    return LoyaltyWallet.objects.select_for_update().get(pk=wallet.pk)


def award(wallet, points, reason, key, policy, actor, payment=None):
    if not points:
        return None
    expiry = timezone.now() + timedelta(days=policy.expiry_days) if policy.expiry_days else None
    return LoyaltyAward.objects.get_or_create(source_key=key, defaults={"wallet": wallet, "points": points, "reason": reason, "expires_at": expiry, "actor": actor, "payment": payment})[0]


@transaction.atomic
def purchase_points(contact_id, payment_id, actor):
    policy = policy_locked()
    wallet = wallet_locked(contact_id)
    payment = InvoicePayment.objects.select_related("invoice").get(pk=payment_id)
    invoice = payment.invoice
    if invoice.customer_id != wallet.contact.account_id or invoice.phone != wallet.contact.phone:
        raise ValidationError("Choose a receipt owned by this verified customer.")
    existing = LoyaltyAward.objects.filter(payment=payment).first()
    if existing:
        return existing
    if invoice.created_at < policy.starts_at or payment.received_at < policy.starts_at:
        raise ValidationError("Only purchases and receipts recorded after the rewards programme started qualify.")
    if not invoice.booking_id or invoice.booking.status != "completed":
        raise ValidationError("Purchase points are available after the billed visit is completed.")
    if not policy.rupees_per_point:
        raise ValidationError("Set the purchase points rate in the rewards policy first.")
    if payment.received_at > timezone.now():
        raise ValidationError("Future-dated receipts cannot earn points.")
    points = int(payment.amount // policy.rupees_per_point)
    if points < 1:
        raise ValidationError("This receipt is below the configured points threshold.")
    return award(wallet, points, f"Receipt #{payment.pk} · invoice #{invoice.pk}", f"receipt:{payment.pk}", policy, actor, payment)


@transaction.atomic
def redeem_points(contact_id, points, reason, request_key, actor):
    policy_locked()
    wallet = wallet_locked(contact_id)
    previous = LoyaltySpend.objects.filter(request_key=request_key).first()
    if previous:
        if previous.wallet_id != wallet.pk or previous.points != points or previous.reason != reason:
            raise ValidationError("This redemption request was already used for a different reward.")
        return previous
    if points < 1 or not reason.strip():
        raise ValidationError("Enter positive points and describe the reward delivered.")
    awards = list(wallet.awards.select_for_update().filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).order_by("expires_at", "created_at", "pk"))
    # MySQL sorts NULL first; spend the earliest expiring awards before non-expiring ones.
    awards.sort(key=lambda a: (a.expires_at is None, a.expires_at or timezone.now(), a.pk))
    if sum(a.points - a.spent for a in awards) < points:
        raise ValidationError("Not enough unexpired points for this reward.")
    remaining = points
    allocation = {}
    for item in awards:
        used = min(item.points - item.spent, remaining)
        if used:
            item.spent += used
            item.save(update_fields=["spent"])
            allocation[str(item.pk)] = used
            remaining -= used
        if not remaining:
            break
    return LoyaltySpend.objects.create(wallet=wallet, points=points, reason=reason, request_key=request_key, actor=actor, allocation=allocation)


@transaction.atomic
def record_referral(referred_id, code, actor=None):
    policy_locked()
    referrer = LoyaltyWallet.objects.select_related("contact").filter(code=code.strip().upper()).first()
    if not referrer:
        raise ValidationError("That referral code was not found.")
    contacts = {c.pk: c for c in CustomerRecord.objects.select_for_update().filter(pk__in=[referred_id, referrer.contact_id]).order_by("pk")}
    referred = contacts[referred_id]
    source = contacts[referrer.contact_id]
    if source.pk == referred.pk or source.account_id == referred.account_id:
        raise ValidationError("A customer cannot refer themselves or another contact on their own account.")
    if not all(c.account_id and c.account.is_active and not c.account.is_staff for c in (source, referred)):
        raise ValidationError("Both customers need reception-verified accounts.")
    if InvoicePayment.objects.filter(Q(invoice__phone=referred.phone) | Q(invoice__customer_id=referred.account_id)).exists():
        raise ValidationError("Referral codes must be recorded before the new customer's first payment.")
    if Referral.objects.filter(referred=referred).exists():
        raise ValidationError("This customer already has a referral record.")
    return Referral.objects.create(referrer=referrer, referred=referred)


@transaction.atomic
def activate_wallet(contact_id):
    policy_locked()
    return wallet_locked(contact_id)


@transaction.atomic
def review_referral(referral_id, invoice_id, action, note, actor):
    policy = policy_locked()
    referral = Referral.objects.select_related("referrer").get(pk=referral_id)
    wallets = {}
    for contact_id in sorted([referral.referrer.contact_id, referral.referred_id]):
        wallets[contact_id] = wallet_locked(contact_id)
    referral = Referral.objects.select_for_update().get(pk=referral_id)
    if referral.status != "pending":
        raise ValidationError("This referral has already been reviewed.")
    if not note.strip():
        raise ValidationError("Record how this referral was checked.")
    if action == "reject":
        referral.status = "rejected"
    elif action == "reward":
        invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
        contact = wallets[referral.referred_id].contact
        first = InvoicePayment.objects.filter(Q(invoice__phone=contact.phone) | Q(invoice__customer_id=contact.account_id)).order_by("received_at", "pk").first()
        if invoice.phone != contact.phone or invoice.customer_id != contact.account_id or invoice.created_at < referral.created_at or not first or first.invoice_id != invoice.pk or not invoice.booking_id or invoice.booking.status != "completed" or invoice.net_amount <= 0 or invoice.balance_due != 0:
            raise ValidationError("Use the new customer's first paid invoice, created after this referral, for a completed visit and fully settled.")
        if not (policy.referrer_points or policy.referred_points):
            raise ValidationError("Configure referral reward points first.")
        if first.received_at > timezone.now() or first.received_at < referral.created_at:
            raise ValidationError("The first receipt must be dated after the referral and cannot be in the future.")
        award(wallets[referral.referrer.contact_id], policy.referrer_points, "Referral reward", f"referral:{referral.pk}:referrer", policy, actor)
        award(wallets[referral.referred_id], policy.referred_points, "Welcome referral reward", f"referral:{referral.pk}:referred", policy, actor)
        referral.status = "rewarded"
        referral.qualifying_invoice = invoice
    else:
        raise ValidationError("Choose reward or reject.")
    referral.note, referral.reviewed_by, referral.reviewed_at = note, actor, timezone.now()
    referral.save()
    return referral
