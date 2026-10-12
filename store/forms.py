import re

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import UserCreationForm


User = get_user_model()


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "username": "Choose a username",
            "email": "you@example.com",
            "first_name": "First name",
            "last_name": "Last name",
            "password1": "Create a password",
            "password2": "Repeat your password",
        }
        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-control form-control-lg"})
            if name in placeholders:
                field.widget.attrs["placeholder"] = placeholders[name]
        self.fields["username"].help_text = "Letters, numbers and @/./+/-/_ only."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ProfileForm(forms.ModelForm):
    """Editable account details for the storefront Profile page.

    Reuses Django's built-in user model so there is no duplicate profile
    table; the fields here live directly on the authenticated user.
    """

    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "first_name": "First name",
            "last_name": "Last name",
            "email": "you@example.com",
        }
        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "form-control form-control-lg"})
            if name in placeholders:
                field.widget.attrs["placeholder"] = placeholders[name]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class LoginForm(forms.Form):
    identifier = forms.CharField(
        label="Username or email",
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Username or email",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Your password",
                "autocomplete": "current-password",
            }
        )
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Keep me signed in",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get("identifier", "").strip()
        password = cleaned_data.get("password")
        if not identifier or not password:
            return cleaned_data

        self.user_cache = authenticate(
            self.request,
            username=identifier,
            password=password,
        )
        if self.user_cache is None:
            user = User.objects.filter(email__iexact=identifier).first()
            if user:
                self.user_cache = authenticate(
                    self.request,
                    username=user.get_username(),
                    password=password,
                )
        if self.user_cache is None:
            raise forms.ValidationError(
                "We could not match that username/email and password. Please try again."
            )
        return cleaned_data

    def get_user(self):
        return self.user_cache


class CheckoutForm(forms.Form):
    shipping_address = forms.CharField(
        label="Shipping address",
        min_length=8,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Street, city, state/province and postal code",
            }
        ),
    )
    phone_number = forms.CharField(
        label="Phone number",
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "+1 555 123 4567",
                "autocomplete": "tel",
            }
        ),
    )

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        if not re.fullmatch(r"[+()\-\s\d.]{7,30}", phone):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone
