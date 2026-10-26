"""Pure helpers: decimals, month arithmetic, money formatting and goal progress.

Nothing here imports Flask or SQLAlchemy, so it is easy to unit test.
"""
import calendar
import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")


def D(value):
    """Convert anything numeric (or None) to Decimal."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q2(value):
    """Round to 2 decimal places (half up)."""
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def average(values):
    values = list(values)
    if not values:
        return ZERO
    return sum((D(v) for v in values), ZERO) / Decimal(len(values))


def pct(part, whole):
    """Percentage as a float, or None when the whole is zero/negative."""
    whole = D(whole)
    if whole <= 0:
        return None
    return float(D(part) / whole * 100)


def shift_month(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_bounds(year, month):
    """Return (first_day, first_day_of_next_month); the end is exclusive."""
    start = date(year, month, 1)
    ny, nm = shift_month(year, month, 1)
    return start, date(ny, nm, 1)


def last_day_of_month(year, month):
    return calendar.monthrange(year, month)[1]


def month_label(year, month):
    return date(year, month, 1).strftime("%B %Y")


def week_bounds(day):
    """Monday and Sunday of the week containing ``day``."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def _group_indian(digits):
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def format_money(value, symbol="₹", decimals=2, indian=None):
    """Format a number as money. Indian digit grouping is used for the rupee symbol."""
    if indian is None:
        indian = symbol.strip() in ("₹", "Rs.", "Rs")
    value = D(value)
    value = q2(value) if decimals else value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    negative = value < 0
    value = abs(value)
    text = f"{value:.{decimals}f}"
    whole, _, frac = text.partition(".")
    grouped = _group_indian(whole) if indian else f"{int(whole):,}"
    out = f"{symbol}{grouped}" + (f".{frac}" if decimals else "")
    return f"-{out}" if negative else out


def goal_progress(target, saved, created_on, target_date, today=None, first_contribution=None):
    """Progress, required monthly saving and a simple projection for a savings goal."""
    today = today or date.today()
    target, saved = D(target), D(saved)
    achieved = target > 0 and saved >= target
    remaining = max(ZERO, target - saved)
    percent = float(min(Decimal(100), saved / target * 100)) if target > 0 else 0.0

    days_left = (target_date - today).days if target_date else None
    overdue = days_left is not None and days_left < 0 and not achieved
    months_left = None
    if days_left is not None:
        months_left = max(1, math.ceil(max(days_left, 0) / 30.44))

    required_monthly = ZERO
    if not achieved and months_left:
        required_monthly = q2(remaining / Decimal(months_left))

    start = first_contribution or created_on or today
    months_active = max(1.0, (today - start).days / 30.44)
    avg_monthly = saved / Decimal(str(months_active)) if saved > 0 else ZERO
    projected = saved + avg_monthly * Decimal(months_left or 0)
    projected_percent = float(min(Decimal(100), projected / target * 100)) if target > 0 else 0.0

    if achieved:
        status = "achieved"
    elif overdue:
        status = "overdue"
    elif saved <= 0:
        status = "not_started"
    elif projected >= target:
        status = "on_track"
    else:
        status = "behind"

    return {
        "target": target, "saved": saved, "remaining": remaining, "percent": round(percent, 1),
        "days_left": days_left, "months_left": months_left, "required_monthly": required_monthly,
        "avg_monthly": q2(avg_monthly), "projected": q2(projected),
        "projected_percent": round(projected_percent, 1), "status": status,
    }
