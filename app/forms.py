"""Flask-WTF forms with server-side validation."""
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, DecimalField, PasswordField, SelectField,
                     StringField, TextAreaField)
from wtforms.validators import (DataRequired, EqualTo, InputRequired, Length, NumberRange,
                                Optional, Regexp, ValidationError)

from app.constants import (CURRENCIES, EXPENSE_CATEGORIES, INCOME_SOURCES, PAYMENT_METHODS,
                           PROFILE_TYPES)
from app.models import User

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
MAX_AMOUNT = Decimal("99999999.99")


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _lower_strip(value):
    return value.strip().lower() if isinstance(value, str) else value


def amount_field(label="Amount"):
    return DecimalField(
        label, places=2, rounding=ROUND_HALF_UP,
        validators=[InputRequired(message="Please enter an amount."),
                    NumberRange(min=Decimal("0.01"), max=MAX_AMOUNT,
                                message="Amount must be greater than 0 and at most 99,999,999.99.")],
        render_kw={"type": "number", "step": "0.01", "min": "0.01", "inputmode": "decimal"},
    )


def reasonable_date(form, field):
    if field.data and not (date(2000, 1, 1) <= field.data <= date(2100, 12, 31)):
        raise ValidationError("Please enter a date between the years 2000 and 2100.")


def strong_password(form, field):
    value = field.data or ""
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValidationError("Password must contain at least one letter and one number.")


class RegisterForm(FlaskForm):
    name = StringField("Full name", filters=[_strip], validators=[DataRequired(), Length(max=80)])
    email = StringField("Email", filters=[_lower_strip],
                        validators=[DataRequired(), Length(max=255), Regexp(EMAIL_RE, message="Enter a valid email address.")])
    profile_type = SelectField("I am a...", choices=PROFILE_TYPES, default="salaried")
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128), strong_password])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("An account with this email already exists.")


class LoginForm(FlaskForm):
    email = StringField("Email", filters=[_lower_strip], validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Keep me signed in on this device")


class IncomeForm(FlaskForm):
    amount = amount_field()
    source = SelectField("Source", choices=INCOME_SOURCES)
    client = StringField("Client / payer (optional)", filters=[_strip], validators=[Optional(), Length(max=100)])
    date = DateField("Date", validators=[InputRequired(message="Please choose a date."), reasonable_date], default=date.today)
    description = TextAreaField("Description (optional)", filters=[_strip], validators=[Optional(), Length(max=255)],
                                render_kw={"rows": 2})


class ExpenseForm(FlaskForm):
    amount = amount_field()
    category = SelectField("Category", choices=EXPENSE_CATEGORIES)
    date = DateField("Date", validators=[InputRequired(message="Please choose a date."), reasonable_date], default=date.today)
    payment_method = SelectField("Payment method", choices=PAYMENT_METHODS)
    description = TextAreaField("Description (optional)", filters=[_strip], validators=[Optional(), Length(max=255)],
                                render_kw={"rows": 2})


class GoalForm(FlaskForm):
    name = StringField("Goal name", filters=[_strip], validators=[DataRequired(), Length(max=100)])
    target_amount = amount_field("Target amount")
    target_date = DateField("Target date", validators=[InputRequired(message="Please choose a target date."), reasonable_date])
    description = TextAreaField("Description (optional)", filters=[_strip], validators=[Optional(), Length(max=255)],
                                render_kw={"rows": 2})
    is_emergency = BooleanField("This is my emergency fund")


class ContributionForm(FlaskForm):
    amount = amount_field("Contribution amount")
    date = DateField("Date", validators=[InputRequired(message="Please choose a date."), reasonable_date], default=date.today)
    note = StringField("Note (optional)", filters=[_strip], validators=[Optional(), Length(max=255)])


class ProfileForm(FlaskForm):
    name = StringField("Full name", filters=[_strip], validators=[DataRequired(), Length(max=80)])
    profile_type = SelectField("Profile type", choices=PROFILE_TYPES)
    currency = SelectField("Currency symbol", choices=CURRENCIES)
    ai_consent = BooleanField("Allow aggregated figures to be sent to my configured external AI provider")


class PasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128), strong_password])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")])


class DeleteAccountForm(FlaskForm):
    password = PasswordField("Confirm your password", validators=[DataRequired()])


class DemoForm(FlaskForm):
    scenario = SelectField("Demo scenario", choices=[
        ("salaried", "Salaried professional"), ("student", "College student"),
        ("freelancer", "Freelancer (multiple clients)"), ("household", "Household manager")])
