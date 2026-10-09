import uuid
from decimal import Decimal
from django import forms
from django.forms import BaseModelFormSet, modelformset_factory
from django.utils import timezone
from .models import Invoice, InvoiceLine, InvoicePayment, Service, CustomerRecord
from .forms import BookingForm


class InvoiceForm(forms.ModelForm):
    phone = forms.CharField(max_length=10, validators=[BookingForm.phone_validator])
    class Meta:
        model = Invoice
        fields = ["booking", "customer", "customer_name", "phone", "email", "issue_date", "discount_amount", "opening_paid", "notes"]
        widgets = {"issue_date": forms.DateInput(attrs={"type":"date"}), "notes":forms.Textarea(attrs={"rows":2})}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from django.contrib.auth import get_user_model
        self.fields["customer"].queryset=get_user_model().objects.filter(is_active=True,is_staff=False,is_superuser=False)
        self.fields["customer"].help_text="Select the customer's account before recording payment so purchased packages and invoices appear in their portal. Guest purchases remain available to reception by phone."

    def clean_issue_date(self):
        day = self.cleaned_data["issue_date"]
        if day > timezone.localdate():
            raise forms.ValidationError("An invoice cannot be dated in the future.")
        return day


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = ["service", "description", "duration", "quantity", "unit_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.filter(is_active=True)
        self.fields["description"].required = False
        self.fields["unit_price"].required = False

    def clean(self):
        data = super().clean()
        service, duration, rate = data.get("service"), data.get("duration"), data.get("unit_price")
        if not service and not data.get("description"):
            raise forms.ValidationError("Choose a treatment or enter a description.")
        if service:
            if not data.get("description"):
                data["description"] = service.name
            if service.is_package and data.get("quantity") != 1:
                raise forms.ValidationError("Use a separate row for each package purchase.")
            if service.is_package and not service.package_components.exists():
                raise forms.ValidationError("Configure this package's treatment credits before selling it.")
            if rate is None:
                option = service.options.filter(duration=duration,is_active=True).first() if duration else None
                rate = option.price if option else service.menu_price
        if rate is None:
            self.add_error("unit_price", "Choose a duration or enter the agreed price.")
        else:
            data["unit_price"] = rate
        return data


class LineSet(BaseModelFormSet):
    def clean(self):
        super().clean()
        if any(self.errors): return
        allowed=set(self.get_queryset().values_list("pk",flat=True))
        if any(f.cleaned_data.get("id") and f.cleaned_data["id"].pk not in allowed for f in self.forms):
            raise forms.ValidationError("An invoice row belongs to another invoice.")
        rows = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not rows: raise forms.ValidationError("Add at least one service to the invoice.")


InvoiceLines = modelformset_factory(InvoiceLine, form=InvoiceLineForm, formset=LineSet, extra=1, can_delete=True, max_num=20, validate_max=True)


class PaymentForm(forms.ModelForm):
    request_key = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)
    class Meta:
        model = InvoicePayment
        fields = ["amount", "mode", "reference", "received_at", "request_key"]
        widgets = {"received_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"})}

    def clean_received_at(self):
        value = self.cleaned_data["received_at"]
        if value > timezone.now(): raise forms.ValidationError("Receipt time cannot be in the future.")
        return value

    def validate_unique(self):
        # The locked service handles request-key replay idempotently.
        pass


class CustomerRecordForm(forms.ModelForm):
    class Meta:
        model = CustomerRecord
        fields = ["name", "preferences"]
        widgets = {"preferences":forms.Textarea(attrs={"rows":4,"maxlength":4000})}

    def clean_preferences(self):
        value=self.cleaned_data["preferences"]
        if len(value)>4000: raise forms.ValidationError("Keep preferences within 4,000 characters.")
        return value
