from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


class CustomerRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        label="Full name", max_length=100,
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("first_name", "email", "username", "password1", "password2")
    def clean_email(self):
        from .models import CustomerProfile
        email = self.cleaned_data["email"].strip().casefold()
        if get_user_model().objects.filter(email__iexact=email).exists() or CustomerProfile.objects.filter(email_address=email).exists():
            raise forms.ValidationError("This email is already registered. Sign in or reset your password.")
        return email
