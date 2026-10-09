
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
    #
    # Duration is loaded from ServiceOption.
    #
    # Example:
    #
    # 45 minutes — ₹1200
    # 60 minutes — ₹1500
    # 90 minutes — ₹2000
    #
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
                "aria-label": "Selected appointment time",
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
            "package_credit",
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
        customer_user = kwargs.pop("customer_user", None)

        super().__init__(*args, **kwargs)
        from .models import PackageCredit
        credits = PackageCredit.objects.select_related("enrollment").prefetch_related("bookings")
        self.fields["package_credit"].queryset = credits.filter(enrollment__customer=customer_user) if customer_user and customer_user.is_authenticated else credits.none()
        self.fields["package_credit"].required = False
        self.fields["package_credit"].empty_label = "Pay for this session"

        # -------------------------------------------------
        # ACTIVE SERVICES
        # -------------------------------------------------

        self.fields["service"].queryset = (
            Service.objects
            .filter(is_active=True, options__is_active=True).distinct()
            .order_by("name")
        )

        # -------------------------------------------------
        # DEFAULT DURATION
        # -------------------------------------------------

        self.fields["duration"].choices = [
            ("", "Select service first")
        ]

        # -------------------------------------------------
        # FIND SELECTED SERVICE
        # -------------------------------------------------

        service_id = None

        # -------------------------------------------------
        # BOUND FORM
        # -------------------------------------------------

        if self.is_bound:

            service_id = self.data.get("service")

        # -------------------------------------------------
        # INITIAL SERVICE
        # -------------------------------------------------

        if not service_id:

            initial_service = self.initial.get(
                "service"
            )

            if initial_service:

                if isinstance(
                    initial_service,
                    Service,
                ):

                    service_id = initial_service.id

                else:

                    service_id = initial_service

        # -------------------------------------------------
        # EXISTING BOOKING
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
        # LOAD SERVICE OPTIONS
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
    #
    # ONLY ServiceOption is used.
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
        # NO OPTIONS
        # -------------------------------------------------

        if len(choices) == 1:

            choices = [
                (
                    "",
                    "No duration available",
                )
            ]

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

        # -------------------------------------------------
        # SERVICE MUST HAVE AT LEAST ONE ACTIVE OPTION
        # -------------------------------------------------

        has_options = (
            ServiceOption.objects
            .filter(
                service=service,
                is_active=True,
            )
            .exists()
        )

        if not has_options:

            raise forms.ValidationError(
                "No duration is currently available "
                "for this service."
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

        if self.instance.pk and appointment_date == self.instance.appointment_date:
            return appointment_date

        if appointment_date < today:

            raise forms.ValidationError(
                "Appointment date cannot be in the past."
            )

        return appointment_date

    # =====================================================
    # CLEAN DURATION
    #
    # SECURITY:
    # Never trust the duration sent by the browser.
    #
    # Verify that the selected duration belongs to
    # the selected service and is active.
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

        option_exists = (
            ServiceOption.objects
            .filter(
                service=service,
                duration=duration,
                is_active=True,
            )
            .exists()
        )

        if not option_exists:

            raise forms.ValidationError(
                "Selected duration is not available "
                "for this service."
            )

        return duration

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

        from .services.availability import appointment_is_past
        unchanged = self.instance.pk and appointment_date == self.instance.appointment_date and appointment_time == self.instance.appointment_time
        if not unchanged and appointment_is_past(appointment_date, appointment_time):
            raise forms.ValidationError("Please choose a future appointment time.")

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

        # -------------------------------------------------
        # GET OPTION
        #
        # Store the validated option internally so that
        # save() uses the exact same database record.
        # -------------------------------------------------

        option = (
            ServiceOption.objects
            .filter(
                service=service,
                duration=duration,
                is_active=True,
            )
            .first()
        )

        if not option:

            raise forms.ValidationError(
                "Selected service duration is no longer available."
            )

        cleaned_data[
            "_selected_option"
        ] = option

        return cleaned_data

    # =====================================================
    # GET SELECTED OPTION
    # =====================================================

    def get_selected_option(self):

        option = self.cleaned_data.get(
            "_selected_option"
        )

        if option:

            return option

        service = self.cleaned_data.get(
            "service"
        )

        duration = self.cleaned_data.get(
            "duration"
        )

        if not service or not duration:

            return None

        return (
            ServiceOption.objects
            .filter(
                service=service,
                duration=duration,
                is_active=True,
            )
            .first()
        )

    # =====================================================
    # GET SELECTED PRICE
    #
    # Price ALWAYS comes from ServiceOption.
    # =====================================================

    def get_selected_price(self):

        option = self.get_selected_option()

        if not option:

            return None

        return option.price

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

        booking.selected_duration = duration

        # -------------------------------------------------
        # SELECTED PRICE
        #
        # NEVER take price from frontend.
        # Get it directly from ServiceOption.
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
        # AUTO CONFIRM
        #
        # No payment.
        # No admin approval.
        #
        # Availability/resource assignment should be
        # handled by views.py/service layer.
        # -------------------------------------------------

        booking.status = "confirmed"

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
