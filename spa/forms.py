from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone

from .models import (
    Booking,
    Service,
    ServiceOption,
)


# =========================================================
# BOOKING FORM
# =========================================================

class BookingForm(forms.ModelForm):

    # =====================================================
    # PHONE
    # =====================================================

    phone_validator = RegexValidator(
        regex=r"^[6-9]\d{9}$",
        message=(
            "Please enter a valid 10-digit "
            "Indian mobile number."
        ),
    )

    phone = forms.CharField(
        validators=[phone_validator],
        max_length=10,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter your phone number",
                "autocomplete": "tel",
                "inputmode": "numeric",
                "maxlength": "10",
                "class": "booking-phone-input",
            }
        ),
    )

    # =====================================================
    # EMAIL
    # =====================================================

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Enter your email address",
                "autocomplete": "email",
                "class": "booking-email-input",
            }
        ),
    )

    # =====================================================
    # SERVICE
    # =====================================================

    service = forms.ModelChoiceField(
        queryset=Service.objects.none(),
        required=True,
        empty_label="Select a service",
        widget=forms.Select(
            attrs={
                "class": "booking-service-select",
                "id": "id_service",
            }
        ),
    )

    # =====================================================
    # DURATION
    # =====================================================

    duration = forms.TypedChoiceField(
        required=True,
        coerce=int,
        choices=[],
        empty_value=None,
        widget=forms.Select(
            attrs={
                "class": "booking-duration-select",
                "id": "id_duration",
            }
        ),
    )

    # =====================================================
    # APPOINTMENT DATE
    # =====================================================

    appointment_date = forms.DateField(
        required=True,
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "type": "date",
                "class": "booking-date-input",
                "id": "id_appointment_date",
            },
        ),
        input_formats=[
            "%Y-%m-%d",
        ],
    )

    # =====================================================
    # APPOINTMENT TIME
    # =====================================================

    appointment_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={
                "type": "time",
                "class": "booking-time-input",
                "id": "id_appointment_time",
                "step": "900",
            },
        ),
        input_formats=[
            "%H:%M",
        ],
    )

    # =====================================================
    # META
    # =====================================================

    class Meta:

        model = Booking

        fields = [
            "name",
            "phone",
            "email",
            "service",
            "appointment_date",
            "appointment_time",
            "message",
        ]

        widgets = {

            "name": forms.TextInput(
                attrs={
                    "placeholder": "Enter your name",
                    "autocomplete": "name",
                    "class": "booking-name-input",
                }
            ),

            "message": forms.Textarea(
                attrs={
                    "placeholder": "Any special request?",
                    "rows": 5,
                    "class": "booking-message-input",
                }
            ),
        }

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # -------------------------------------------------
        # ACTIVE SERVICES
        # -------------------------------------------------

        self.fields["service"].queryset = (
            Service.objects
            .filter(is_active=True)
            .order_by("name")
        )

        # -------------------------------------------------
        # DEFAULT DURATION
        # -------------------------------------------------

        self.fields["duration"].choices = [
            ("", "Select service first")
        ]

        # -------------------------------------------------
        # GET SELECTED SERVICE
        # -------------------------------------------------

        service_id = None

        if self.is_bound:

            service_id = self.data.get("service")

        # -------------------------------------------------
        # INITIAL SERVICE
        # -------------------------------------------------

        if not service_id:

            initial_service = self.initial.get("service")

            if initial_service:

                if isinstance(initial_service, Service):

                    service_id = initial_service.id

                else:

                    service_id = initial_service

        # -------------------------------------------------
        # EXISTING INSTANCE SERVICE
        # -------------------------------------------------

        if not service_id and self.instance:

            instance_service = getattr(
                self.instance,
                "service",
                None,
            )

            if instance_service:

                service_id = instance_service.id

        # -------------------------------------------------
        # LOAD DURATION CHOICES
        # -------------------------------------------------

        if service_id:

            try:

                selected_service = (
                    Service.objects
                    .filter(
                        id=int(service_id),
                        is_active=True,
                    )
                    .first()
                )

            except (
                TypeError,
                ValueError,
            ):

                selected_service = None

            if selected_service:

                self.set_duration_choices(
                    selected_service
                )

        # -------------------------------------------------
        # MINIMUM DATE
        # -------------------------------------------------

        today = timezone.localdate()

        self.fields[
            "appointment_date"
        ].widget.attrs["min"] = today.strftime(
            "%Y-%m-%d"
        )

        # -------------------------------------------------
        # TIME STEP
        # -------------------------------------------------

        self.fields[
            "appointment_time"
        ].widget.attrs["step"] = "900"

    # =====================================================
    # SET DURATION CHOICES
    # =====================================================

    def set_duration_choices(self, service):

        choices = [
            ("", "Select duration")
        ]

        options = (
            ServiceOption.objects
            .filter(
                service=service,
                is_active=True,
            )
            .order_by("duration")
        )

        options = list(options)

        # -------------------------------------------------
        # SERVICE OPTIONS AVAILABLE
        # -------------------------------------------------

        if options:

            for option in options:

                choices.append(
                    (
                        option.duration,
                        (
                            f"{option.duration} minutes"
                            f" — ₹{option.price:,.0f}"
                        ),
                    )
                )

        # -------------------------------------------------
        # FALLBACK SERVICE DURATION
        # -------------------------------------------------

        elif service.duration:

            choices.append(
                (
                    service.duration,
                    (
                        f"{service.duration} minutes"
                        f" — ₹{service.price:,.0f}"
                    ),
                )
            )

        self.fields[
            "duration"
        ].choices = choices

    # =====================================================
    # CLEAN NAME
    # =====================================================

    def clean_name(self):

        name = self.cleaned_data.get("name")

        if not name:

            raise forms.ValidationError(
                "Please enter your name."
            )

        name = name.strip()

        if len(name) < 2:

            raise forms.ValidationError(
                "Name must contain at least 2 characters."
            )

        return name

    # =====================================================
    # CLEAN PHONE
    # =====================================================

    def clean_phone(self):

        phone = self.cleaned_data.get("phone")

        if not phone:

            raise forms.ValidationError(
                "Please enter your phone number."
            )

        return phone.strip()

    # =====================================================
    # CLEAN SERVICE
    # =====================================================

    def clean_service(self):

        service = self.cleaned_data.get("service")

        if not service:

            raise forms.ValidationError(
                "Please select a service."
            )

        if not service.is_active:

            raise forms.ValidationError(
                "This service is currently unavailable."
            )

        return service

    # =====================================================
    # CLEAN DATE
    # =====================================================

    def clean_appointment_date(self):

        appointment_date = self.cleaned_data.get(
            "appointment_date"
        )

        if not appointment_date:

            return appointment_date

        today = timezone.localdate()

        if appointment_date < today:

            raise forms.ValidationError(
                "Appointment date cannot be in the past."
            )

        return appointment_date

    # =====================================================
    # CLEAN DURATION
    # =====================================================

    def clean_duration(self):

        duration = self.cleaned_data.get(
            "duration"
        )

        service = self.cleaned_data.get(
            "service"
        )

        if not service:

            return duration

        if not duration:

            raise forms.ValidationError(
                "Please select a session duration."
            )

        # -------------------------------------------------
        # MATCH ACTIVE SERVICE OPTION
        # -------------------------------------------------

        option_exists = (
            ServiceOption.objects
            .filter(
                service=service,
                duration=duration,
                is_active=True,
            )
            .exists()
        )

        if option_exists:

            return duration

        # -------------------------------------------------
        # CHECK WHETHER SERVICE HAS OPTIONS
        # -------------------------------------------------

        has_options = (
            ServiceOption.objects
            .filter(
                service=service,
                is_active=True,
            )
            .exists()
        )

        # -------------------------------------------------
        # FALLBACK
        # -------------------------------------------------

        if not has_options:

            if duration == service.duration:

                return duration

        raise forms.ValidationError(
            "Selected duration is not available "
            "for this service."
        )

    # =====================================================
    # CLEAN TIME
    # =====================================================

    def clean_appointment_time(self):

        appointment_time = self.cleaned_data.get(
            "appointment_time"
        )

        if not appointment_time:

            return appointment_time

        from .services.availability import (
            BUSINESS_START,
            BUSINESS_END,
            time_to_minutes,
        )

        minutes = time_to_minutes(
            appointment_time
        )

        # -------------------------------------------------
        # OPENING TIME
        # -------------------------------------------------

        if minutes < BUSINESS_START:

            raise forms.ValidationError(
                "Appointments start from 10:00 AM."
            )

        # -------------------------------------------------
        # CLOSING TIME
        # -------------------------------------------------

        if minutes >= BUSINESS_END:

            raise forms.ValidationError(
                "Appointments must start before 10:00 PM."
            )

        # -------------------------------------------------
        # 15 MINUTE INTERVAL
        # -------------------------------------------------

        if minutes % 15 != 0:

            raise forms.ValidationError(
                "Please select a time in 15-minute intervals."
            )

        return appointment_time

    # =====================================================
    # CLEAN FORM
    # =====================================================

    def clean(self):

        cleaned_data = super().clean()

        service = cleaned_data.get("service")

        duration = cleaned_data.get("duration")

        appointment_date = cleaned_data.get(
            "appointment_date"
        )

        appointment_time = cleaned_data.get(
            "appointment_time"
        )

        if not service:
            return cleaned_data

        if not duration:
            return cleaned_data

        if not appointment_date:
            return cleaned_data

        if not appointment_time:
            return cleaned_data

        from .services.availability import (
            calculate_end_time,
            is_within_business_hours,
        )

        # -------------------------------------------------
        # CALCULATE END TIME
        # -------------------------------------------------

        try:

            end_time = calculate_end_time(
                appointment_time,
                duration,
            )

        except (
            TypeError,
            ValueError,
        ):

            raise forms.ValidationError(
                "Unable to calculate appointment end time."
            )

        # -------------------------------------------------
        # BUSINESS HOURS
        # -------------------------------------------------

        if not is_within_business_hours(
            appointment_time,
            end_time,
        ):

            raise forms.ValidationError(
                "Selected session does not fit within "
                "spa business hours (10:00 AM - 10:00 PM)."
            )

        # -------------------------------------------------
        # STORE CALCULATED END TIME
        # -------------------------------------------------

        cleaned_data[
            "_calculated_end_time"
        ] = end_time

        return cleaned_data

    # =====================================================
    # GET SELECTED PRICE
    # =====================================================

    def get_selected_price(self):

        service = self.cleaned_data.get(
            "service"
        )

        duration = self.cleaned_data.get(
            "duration"
        )

        if not service:

            return None

        # -------------------------------------------------
        # FIND SERVICE OPTION
        # -------------------------------------------------

        if duration:

            option = (
                ServiceOption.objects
                .filter(
                    service=service,
                    duration=duration,
                    is_active=True,
                )
                .first()
            )

            if option:

                return option.price

        # -------------------------------------------------
        # FALLBACK
        # -------------------------------------------------

        return service.price

    # =====================================================
    # GET END TIME
    # =====================================================

    def get_end_time(self):

        calculated_end_time = self.cleaned_data.get(
            "_calculated_end_time"
        )

        if calculated_end_time:

            return calculated_end_time

        appointment_time = self.cleaned_data.get(
            "appointment_time"
        )

        duration = self.cleaned_data.get(
            "duration"
        )

        if not appointment_time or not duration:

            return None

        from .services.availability import (
            calculate_end_time,
        )

        return calculate_end_time(
            appointment_time,
            duration,
        )

    # =====================================================
    # SAVE
    # =====================================================

    def save(self, commit=True):

        booking = super().save(
            commit=False
        )

        service = self.cleaned_data.get(
            "service"
        )

        duration = self.cleaned_data.get(
            "duration"
        )

        # -------------------------------------------------
        # SELECTED DURATION
        # -------------------------------------------------

        if service:

            if not duration:

                duration = service.duration

            booking.selected_duration = duration

        # -------------------------------------------------
        # SELECTED PRICE
        # -------------------------------------------------

        booking.selected_price = (
            self.get_selected_price()
        )

        # -------------------------------------------------
        # END TIME
        # -------------------------------------------------

        booking.end_time = (
            self.get_end_time()
        )

        # -------------------------------------------------
        # DEFAULT STATUS
        # -------------------------------------------------

        if not booking.status:

            booking.status = "pending"

        # -------------------------------------------------
        # STAFF + ROOM
        #
        # DO NOT ASSIGN HERE.
        #
        # views.py handles:
        #
        # 1. Staff availability
        # 2. Room availability
        # 3. Final locking
        # 4. Assignment
        # -------------------------------------------------

        if commit:

            booking.save()

        return booking