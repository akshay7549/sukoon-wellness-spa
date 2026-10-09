from django import forms
from .models import Enquiry
from .forms import BookingForm

class EnquiryForm(forms.ModelForm):
    phone = forms.CharField(max_length=10, validators=[BookingForm.phone_validator])
    message = forms.CharField(max_length=5000, widget=forms.Textarea)
    class Meta:
        model = Enquiry
        fields = ["name", "phone", "email", "subject", "message", "city", "investment_range", "franchise_model"]
    def __init__(self, *args, kind="contact", **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        self.fields["subject"].required = kind == "contact"
        self.fields["city"].required = kind == "franchise"
        self.fields["investment_range"].required = kind == "franchise"
        self.fields["franchise_model"].required = kind == "franchise"
    def clean(self):
        data = super().clean()
        if self.kind == "franchise":
            if data.get("investment_range") not in ("25-35", "35-50", "50-75", "75+"):
                self.add_error("investment_range", "Choose a valid investment range.")
            if data.get("franchise_model") not in ("FOFO", "FOCO", "HOTEL_RESORT"):
                self.add_error("franchise_model", "Choose a valid franchise model.")
        return data
