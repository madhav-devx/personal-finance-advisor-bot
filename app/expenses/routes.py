from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.calculations import ZERO, last_day_of_month, month_bounds, week_bounds
from app.constants import EXPENSE_CATEGORIES, PAYMENT_METHODS
from app.extensions import db
from app.forms import ExpenseForm
from app.models import Expense
from app.utils import owned_or_404, page_arg, parse_date_arg

bp = Blueprint("expenses", __name__, url_prefix="/expenses")
VALID_CATEGORIES = {c for c, _ in EXPENSE_CATEGORIES}
VALID_PAYMENTS = {p for p, _ in PAYMENT_METHODS}


def _sum_between(start, end_inclusive):
    rows = Expense.query.filter(Expense.user_id == current_user.id, Expense.date >= start,
                                Expense.date <= end_inclusive).all()
    return sum((r.amount for r in rows), ZERO), rows


def spending_summary(today):
    monday, _sunday = week_bounds(today)
    month_start, month_end = month_bounds(today.year, today.month)
    day_total, _ = _sum_between(today, today)
    week_total, _ = _sum_between(monday, today)
    last_week_total, _ = _sum_between(monday - timedelta(days=7), monday - timedelta(days=1))
    month_total, _ = _sum_between(month_start, today)
    last7 = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        total, _ = _sum_between(d, d)
        last7.append({"date": d, "total": total})
    peak = max((x["total"] for x in last7), default=ZERO)
    for x in last7:
        x["pct"] = float(x["total"] / peak * 100) if peak > 0 else 0
    elapsed = max(1, today.day)
    return {"today": day_total, "week": week_total, "last_week": last_week_total, "month": month_total,
            "daily_avg": month_total / elapsed, "last7": last7}


@bp.route("/")
@login_required
def index():
    from datetime import date
    today = date.today()
    start = parse_date_arg(request.args.get("start"))
    end = parse_date_arg(request.args.get("end"))
    category = request.args.get("category", "")
    payment = request.args.get("payment", "")
    q = (request.args.get("q") or "").strip()[:100]
    month_raw, year_raw = request.args.get("month", ""), request.args.get("year", "")

    query = Expense.query.filter_by(user_id=current_user.id)
    if month_raw.isdigit() and year_raw.isdigit() and 1 <= int(month_raw) <= 12 and 2000 <= int(year_raw) <= 2100:
        m_start, m_end = month_bounds(int(year_raw), int(month_raw))
        query = query.filter(Expense.date >= m_start, Expense.date < m_end)
    if start:
        query = query.filter(Expense.date >= start)
    if end:
        query = query.filter(Expense.date <= end)
    if category in VALID_CATEGORIES:
        query = query.filter(Expense.category == category)
    if payment in VALID_PAYMENTS:
        query = query.filter(Expense.payment_method == payment)
    if q:
        query = query.filter(Expense.description.ilike(f"%{q}%"))

    matching = query.all()
    total = sum((r.amount for r in matching), ZERO)
    pagination = query.order_by(Expense.date.desc(), Expense.id.desc()).paginate(page=page_arg(), per_page=15, error_out=False)
    args = {k: v for k, v in request.args.items() if k != "page"}
    filtered = bool(start or end or category in VALID_CATEGORIES or payment in VALID_PAYMENTS or q or month_raw)
    return render_template("expenses/list.html", pagination=pagination, total=total, count=len(matching),
                           summary=spending_summary(today), categories=EXPENSE_CATEGORIES,
                           payments=PAYMENT_METHODS, args=args, filtered=filtered,
                           filters={"start": start, "end": end, "category": category, "payment": payment,
                                    "q": q, "month": month_raw, "year": year_raw})


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = ExpenseForm()
    if form.validate_on_submit():
        db.session.add(Expense(user_id=current_user.id, amount=form.amount.data, category=form.category.data,
                               date=form.date.data, payment_method=form.payment_method.data,
                               description=form.description.data or None))
        db.session.commit()
        flash("Expense added.", "success")
        return redirect(url_for("expenses.index"))
    return render_template("_form_page.html", form=form, title="Add expense", icon="bi-receipt",
                           cancel_url=url_for("expenses.index"), submit_label="Save expense")


@bp.route("/<int:expense_id>/edit", methods=["GET", "POST"])
@login_required
def edit(expense_id):
    record = owned_or_404(Expense, expense_id)
    form = ExpenseForm(obj=record)
    if form.validate_on_submit():
        record.amount = form.amount.data
        record.category = form.category.data
        record.date = form.date.data
        record.payment_method = form.payment_method.data
        record.description = form.description.data or None
        record.is_demo = False
        db.session.commit()
        flash("Expense updated.", "success")
        return redirect(url_for("expenses.index"))
    return render_template("_form_page.html", form=form, title="Edit expense", icon="bi-receipt",
                           cancel_url=url_for("expenses.index"), submit_label="Update expense")


@bp.route("/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete(expense_id):
    record = owned_or_404(Expense, expense_id)
    db.session.delete(record)
    db.session.commit()
    flash("Expense deleted.", "info")
    return redirect(url_for("expenses.index"))
