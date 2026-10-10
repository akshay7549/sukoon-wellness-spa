import uuid
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


def referral_code():
    return uuid.uuid4().hex[:16].upper()


class LoyaltyPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    rupees_per_point = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(1)], help_text="Receipt amount needed for one point. Blank disables purchase points.")
    expiry_days = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(3650)], help_text="Blank means no expiry. Changes apply only to new awards.")
    referrer_points = models.PositiveIntegerField(default=0)
    referred_points = models.PositiveIntegerField(default=0)
    reward_terms = models.TextField(blank=True, max_length=4000, help_text="Explain available rewards and how customers can redeem points at reception.")
    starts_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Customer rewards policy"


class LoyaltyWallet(models.Model):
    contact = models.OneToOneField("spa.CustomerRecord", on_delete=models.PROTECT, related_name="loyalty_wallet")
    code = models.CharField(max_length=16, unique=True, default=referral_code, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def balance(self):
        return sum(a.points - a.spent for a in self.awards.filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())))


class LoyaltyAward(models.Model):
    wallet = models.ForeignKey(LoyaltyWallet, on_delete=models.PROTECT, related_name="awards")
    points = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    spent = models.PositiveIntegerField(default=0, editable=False)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reason = models.CharField(max_length=1000)
    source_key = models.CharField(max_length=100, unique=True)
    payment = models.OneToOneField("spa.InvoicePayment", on_delete=models.PROTECT, null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [models.CheckConstraint(condition=models.Q(points__gt=0), name="loyalty_award_positive"), models.CheckConstraint(condition=models.Q(spent__lte=models.F("points")), name="loyalty_spent_within_award")]


class LoyaltySpend(models.Model):
    wallet = models.ForeignKey(LoyaltyWallet, on_delete=models.PROTECT, related_name="spends")
    points = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=1000)
    request_key = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    allocation = models.JSONField(default=dict, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(points__gt=0), name="loyalty_spend_positive")]


class Referral(models.Model):
    referrer = models.ForeignKey(LoyaltyWallet, on_delete=models.PROTECT, related_name="referrals")
    referred = models.OneToOneField("spa.CustomerRecord", on_delete=models.PROTECT, related_name="referral")
    status = models.CharField(max_length=12, choices=[("pending", "Pending"), ("rewarded", "Rewarded"), ("rejected", "Rejected")], default="pending")
    qualifying_invoice = models.OneToOneField("spa.Invoice", on_delete=models.PROTECT, null=True, blank=True)
    note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
