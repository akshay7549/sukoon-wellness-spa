import uuid
from django import forms
from .models import LoyaltyPolicy, InvoicePayment, Invoice


class PolicyForm(forms.ModelForm):
    class Meta:
        model = LoyaltyPolicy
        fields = ["enabled", "rupees_per_point", "expiry_days", "referrer_points", "referred_points", "reward_terms"]
        widgets = {"reward_terms": forms.Textarea(attrs={"rows": 4})}

    def clean(self):
        data = super().clean()
        if data.get("enabled") and not data.get("reward_terms", "").strip():
            self.add_error("reward_terms", "Describe the rewards customers can receive before enabling the programme.")
        return data


class RedemptionForm(forms.Form):
    points = forms.IntegerField(min_value=1, max_value=100000000)
    reason = forms.CharField(max_length=1000, label="Reward delivered / reason")
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)


class PurchasePointsForm(forms.Form):
    payment = forms.ModelChoiceField(queryset=InvoicePayment.objects.none())

    def __init__(self, *args, contact, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment"].queryset = InvoicePayment.objects.filter(invoice__phone=contact.phone, invoice__customer=contact.account, invoice__booking__status="completed").select_related("invoice").order_by("-received_at") if contact.account_id else InvoicePayment.objects.none()
        self.fields["payment"].label_from_instance = lambda p: f"Receipt #{p.pk} · SWI-{p.invoice_id:06d} · ₹{p.amount} · {p.received_at:%d %b %Y}"


class ReferralForm(forms.Form):
    code = forms.CharField(max_length=16, label="Referrer's code")


class ReferralReviewForm(forms.Form):
    action = forms.ChoiceField(choices=[("reward", "Qualify and reward"), ("reject", "Reject referral")])
    invoice = forms.ModelChoiceField(queryset=Invoice.objects.none(), required=False)
    note = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, referral, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invoice"].queryset = Invoice.objects.filter(phone=referral.referred.phone, customer=referral.referred.account).order_by("-created_at")

    def clean(self):
        data = super().clean()
        if data.get("action") == "reward" and not data.get("invoice"):
            self.add_error("invoice", "Choose the qualifying invoice.")
        return data
