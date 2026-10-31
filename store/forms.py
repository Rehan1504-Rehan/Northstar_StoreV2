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
                "placeholder": "House/flat no., street, area, city, state and PIN code",
            }
        ),
    )
    phone_number = forms.CharField(
        label="Phone number",
        max_length=30,
        help_text="10-digit Indian mobile number (starting with 6–9). Optional +91, spaces or hyphens allowed.",
        error_messages={
            "required": "Enter your 10-digit Indian mobile number.",
            "max_length": "Phone number is too long. Enter a 10-digit Indian mobile number (with optional +91).",
        },
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "type": "tel",
                "inputmode": "tel",
                "maxlength": "16",
                "placeholder": "+91 98765 43210",
                "autocomplete": "tel",
                "pattern": r"^\s*(?:\+91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}\s*$",
                "title": "Enter a 10-digit Indian mobile number starting with 6, 7, 8, or 9 (optional +91)",
                "aria-describedby": "phone-number-help",
            }
        ),
    )

    def clean_phone_number(self):
        raw = (self.cleaned_data.get("phone_number") or "").strip()
        if not raw:
            raise forms.ValidationError("Enter your 10-digit Indian mobile number.")

        # Reject letters or unsupported symbols (only digits, spaces, hyphens, and an optional leading '+').
        if not re.fullmatch(r"\+?[\d\s\-]+", raw):
            raise forms.ValidationError(
                "Enter a valid Indian mobile number using digits only (optional +91, spaces, or hyphens)."
            )

        # Reject malformed separator usage such as leading/trailing hyphens or consecutive hyphens.
        if (
            raw.startswith("-")
            or raw.endswith("-")
            or "--" in raw
            or "+-" in raw
            or "-+" in raw
        ):
            raise forms.ValidationError(
                "Enter a valid 10-digit Indian mobile number (e.g. 98765 43210 or +91 98765 43210)."
            )

        compact = re.sub(r"[\s\-]+", "", raw)
        if compact.startswith("+"):
            if not compact.startswith("+91"):
                raise forms.ValidationError(
                    "Only Indian mobile numbers (+91 country code) are supported."
                )
            if not re.match(r"^\+91(?:[\s\-]?\d)", raw):
                raise forms.ValidationError(
                    "Enter a valid +91 country code followed by a 10-digit mobile number."
                )
            national = compact[3:]
        else:
            national = compact

        if not national.isdigit() or len(national) != 10:
            raise forms.ValidationError(
                "Enter a valid 10-digit Indian mobile number (with optional +91 country code)."
            )

        if national[0] not in {"6", "7", "8", "9"}:
            raise forms.ValidationError(
                "Indian mobile numbers must start with 6, 7, 8, or 9."
            )

        return f"+91{national}"


class SmartMatchForm(forms.Form):
    """Server-validated choices for the rule-based Northstar Smart Match finder."""

    CATEGORY_CHOICES = (
        ("audio", "Audio & Music"),
        ("gaming", "Gaming"),
        ("computers_work_study", "Computers, Work & Study"),
        ("electronics_mobile", "Electronics & Mobile Accessories"),
        ("home_kitchen_smart", "Home & Kitchen / Smart Home"),
        ("fashion_footwear", "Fashion & Footwear"),
        ("all", "Explore All Categories"),
    )

    BUDGET_CHOICES = (
        ("under_1000", "Under ₹1,000"),
        ("1000_3000", "₹1,000–₹3,000"),
        ("3000_5000", "Above ₹3,000–₹5,000"),
        ("above_5000", "Above ₹5,000"),
        ("any", "No budget limit"),
    )

    SORT_CHOICES = (
        ("price_asc", "Lowest price first"),
        ("price_desc", "Highest price first"),
        ("discount_desc", "Biggest discount first"),
        ("newest", "Newest first"),
    )

    category = forms.ChoiceField(
        label="What are you looking for?",
        choices=CATEGORY_CHOICES,
        error_messages={
            "required": "Please select what you are looking for.",
            "invalid_choice": "Please choose one of the available category options.",
        },
    )
    budget = forms.ChoiceField(
        label="What is your budget?",
        choices=BUDGET_CHOICES,
        error_messages={
            "required": "Please select a budget range.",
            "invalid_choice": "Please choose one of the available budget ranges.",
        },
    )
    sort = forms.ChoiceField(
        label="How would you like to sort the results?",
        choices=SORT_CHOICES,
        error_messages={
            "required": "Please select how you would like to sort the results.",
            "invalid_choice": "Please choose one of the available sorting options.",
        },
    )

    _CATEGORY_ALIASES = {label.lower(): key for key, label in CATEGORY_CHOICES}
    _BUDGET_ALIASES = {
        **{label.lower(): key for key, label in BUDGET_CHOICES},
        "1000-3000": "1000_3000",
        "₹1,000-₹3,000": "1000_3000",
        "above ₹3,000-₹5,000": "3000_5000",
        "3000-5000": "3000_5000",
        "no_limit": "any",
        "all": "any",
    }
    _SORT_ALIASES = {
        **{label.lower(): key for key, label in SORT_CHOICES},
        "price_low": "price_asc",
        "price_high": "price_desc",
        "discount": "discount_desc",
    }

    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            normalized = data.copy()
            raw_cat = (normalized.get("category") or normalized.get("interest") or "").strip()
            if raw_cat and raw_cat.lower() in self._CATEGORY_ALIASES:
                normalized["category"] = self._CATEGORY_ALIASES[raw_cat.lower()]
            elif raw_cat and "category" not in normalized:
                normalized["category"] = raw_cat

            raw_budget = (normalized.get("budget") or "").strip()
            if raw_budget and raw_budget.lower() in self._BUDGET_ALIASES:
                normalized["budget"] = self._BUDGET_ALIASES[raw_budget.lower()]

            raw_sort = (normalized.get("sort") or normalized.get("sort_by") or "").strip()
            if raw_sort and raw_sort.lower() in self._SORT_ALIASES:
                normalized["sort"] = self._SORT_ALIASES[raw_sort.lower()]
            elif raw_sort and "sort" not in normalized:
                normalized["sort"] = raw_sort
            data = normalized
        super().__init__(data=data, *args, **kwargs)

