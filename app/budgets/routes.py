from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.advisor import engine
from app.calculations import ZERO
from app.constants import EXPENSE_CATEGORIES, TOTAL_BUDGET_KEY
from app.extensions import db
from app.models import Budget
from app.services import budget_chart, get_snapshot
from app.utils import parse_decimal, period_from_request

bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def _period_from_form():
    try:
        year, month = int(request.form.get("year", "")), int(request.form.get("month", ""))
    except ValueError:
        return None
    return (year, month) if 1 <= month <= 12 and 2000 <= year <= 2100 else None


def _upsert(year, month, category, amount):
    row = Budget.query.filter_by(user_id=current_user.id, year=year, month=month, category=category).first()
    if amount is None:
        if row:
            db.session.delete(row)
        return
    if row:
        row.amount, row.is_demo = amount, False
    else:
        db.session.add(Budget(user_id=current_user.id, year=year, month=month, category=category, amount=amount))


@bp.route("/")
@login_required
def index():
    year, month = period_from_request()
    snap = get_snapshot(current_user, year, month)
    rows = {r["category"]: r for r in engine.budget_rows(snap)}
    return render_template("budgets/index.html", snap=snap, year=year, month=month, rows=rows,
                           categories=EXPENSE_CATEGORIES, util=engine.budget_utilization(snap),
                           alerts=engine.budget_alerts(snap), suggestions=engine.budget_suggestions(snap),
                           chart_data={"budget": budget_chart(snap), "currency": current_user.currency})


@bp.route("/save", methods=["POST"])
@login_required
def save():
    period = _period_from_form()
    if not period:
        flash("Invalid month.", "danger")
        return redirect(url_for("budgets.index"))
    year, month = period
    values, errors = {}, []
    fields = [(TOTAL_BUDGET_KEY, "total budget")] + [(c, label) for c, label in EXPENSE_CATEGORIES]
    for key, label in fields:
        raw = (request.form.get("total" if key == TOTAL_BUDGET_KEY else "cat_" + key, "") or "").strip()
        if not raw:
            values[key] = None  # blank means "no limit"
            continue
        number = parse_decimal(raw, minimum=ZERO)
        if number is None or number <= 0:
            errors.append(f"{label.title()}: enter a positive amount or leave it blank.")
        else:
            values[key] = number
    if errors:
        for message in errors:
            flash(message, "danger")
        return redirect(url_for("budgets.index", year=year, month=month))
    for key, amount in values.items():
        _upsert(year, month, key, amount)
    db.session.commit()
    total = values.get(TOTAL_BUDGET_KEY)
    cat_sum = sum((v for k, v in values.items() if k != TOTAL_BUDGET_KEY and v), ZERO)
    if total and cat_sum > total:
        flash("Budgets saved - note that your category limits add up to more than your total budget.", "warning")
    else:
        flash("Budgets saved.", "success")
    return redirect(url_for("budgets.index", year=year, month=month))


@bp.route("/apply-suggestions", methods=["POST"])
@login_required
def apply_suggestions():
    period = _period_from_form()
    if not period:
        flash("Invalid month.", "danger")
        return redirect(url_for("budgets.index"))
    year, month = period
    snap = get_snapshot(current_user, year, month)
    suggestion = engine.budget_suggestions(snap)
    if not suggestion["possible"]:
        flash(suggestion["notes"][0], "warning")
        return redirect(url_for("budgets.index", year=year, month=month))
    for category, _label in EXPENSE_CATEGORIES:
        _upsert(year, month, category, suggestion["categories"].get(category))
    _upsert(year, month, TOTAL_BUDGET_KEY, suggestion["total"] if suggestion["total"] > 0 else None)
    db.session.commit()
    flash("Suggested budget applied. You can adjust any value below.", "success")
    return redirect(url_for("budgets.index", year=year, month=month))
