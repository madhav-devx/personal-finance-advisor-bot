"""Small helpers shared by routes and templates."""
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from flask import request
from flask_login import current_user

from app.calculations import format_money
from app.constants import CATEGORY_LABELS, PAYMENT_LABELS, SOURCE_LABELS

MONTH_CHOICES = [(i, date(2000, i, 1).strftime("%B")) for i in range(1, 13)]


def year_choices():
    year = date.today().year
    return list(range(year - 5, year + 2))


def money_filter(value, decimals=2):
    symbol = current_user.currency if current_user.is_authenticated else "₹"
    return format_money(value, symbol, decimals)


def percent_filter(value, decimals=0):
    if value is None:
        return "—"
    return f"{value:.{decimals}f}%"


def category_label(value):
    return CATEGORY_LABELS.get(value, str(value).title())


def source_label(value):
    return SOURCE_LABELS.get(value, str(value).title())


def payment_label(value):
    return PAYMENT_LABELS.get(value, str(value).title())


def owned_or_404(model, object_id):
    """Fetch a record only if it belongs to the logged-in user (otherwise 404)."""
    return model.query.filter_by(id=object_id, user_id=current_user.id).first_or_404()


def is_safe_redirect(target):
    """Only allow relative, same-site redirect targets."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc


def parse_date_arg(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def parse_decimal(value, minimum=Decimal("0"), maximum=Decimal("99999999.99")):
    """Parse user text to Decimal within bounds, or return None."""
    try:
        number = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    if not number.is_finite() or number < minimum or number > maximum:
        return None
    return number.quantize(Decimal("0.01"))


def period_from_request():
    """Read ?year=&month= from the query string, defaulting to the current month."""
    today = date.today()
    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
    except (TypeError, ValueError):
        return today.year, today.month
    if not (1 <= month <= 12 and 2000 <= year <= 2100):
        return today.year, today.month
    return year, month


def page_arg():
    try:
        return max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        return 1


def csv_safe(value):
    """Neutralise spreadsheet formula injection in exported text."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
