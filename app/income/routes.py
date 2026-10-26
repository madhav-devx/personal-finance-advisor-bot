from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.calculations import ZERO
from app.constants import INCOME_SOURCES, SOURCE_LABELS
from app.extensions import db
from app.forms import IncomeForm
from app.models import Income
from app.utils import owned_or_404, page_arg, parse_date_arg

bp = Blueprint("income", __name__, url_prefix="/income")


@bp.route("/")
@login_required
def index():
    start = parse_date_arg(request.args.get("start"))
    end = parse_date_arg(request.args.get("end"))
    source = request.args.get("source", "")
    q = (request.args.get("q") or "").strip()[:100]

    query = Income.query.filter_by(user_id=current_user.id)
    if start:
        query = query.filter(Income.date >= start)
    if end:
        query = query.filter(Income.date <= end)
    if source in SOURCE_LABELS:
        query = query.filter(Income.source == source)
    if q:
        query = query.filter(Income.description.ilike(f"%{q}%") | Income.client.ilike(f"%{q}%"))

    matching = query.all()
    total = sum((r.amount for r in matching), ZERO)
    by_source = {}
    for r in matching:
        by_source[r.source] = by_source.get(r.source, ZERO) + r.amount
    pagination = query.order_by(Income.date.desc(), Income.id.desc()).paginate(page=page_arg(), per_page=15, error_out=False)
    args = {k: v for k, v in request.args.items() if k != "page"}
    return render_template("income/list.html", pagination=pagination, total=total, count=len(matching),
                           by_source=by_source, sources=INCOME_SOURCES, args=args,
                           filters={"start": start, "end": end, "source": source, "q": q},
                           filtered=bool(start or end or source or q))


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = IncomeForm()
    if form.validate_on_submit():
        db.session.add(Income(user_id=current_user.id, amount=form.amount.data, source=form.source.data,
                              client=form.client.data or None, date=form.date.data,
                              description=form.description.data or None))
        db.session.commit()
        flash("Income added.", "success")
        return redirect(url_for("income.index"))
    return render_template("_form_page.html", form=form, title="Add income", icon="bi-cash-coin",
                           cancel_url=url_for("income.index"), submit_label="Save income")


@bp.route("/<int:income_id>/edit", methods=["GET", "POST"])
@login_required
def edit(income_id):
    record = owned_or_404(Income, income_id)
    form = IncomeForm(obj=record)
    if form.validate_on_submit():
        record.amount = form.amount.data
        record.source = form.source.data
        record.client = form.client.data or None
        record.date = form.date.data
        record.description = form.description.data or None
        record.is_demo = False  # once edited it is the user's own record
        db.session.commit()
        flash("Income updated.", "success")
        return redirect(url_for("income.index"))
    return render_template("_form_page.html", form=form, title="Edit income", icon="bi-cash-coin",
                           cancel_url=url_for("income.index"), submit_label="Update income")


@bp.route("/<int:income_id>/delete", methods=["POST"])
@login_required
def delete(income_id):
    record = owned_or_404(Income, income_id)
    db.session.delete(record)
    db.session.commit()
    flash("Income deleted.", "info")
    return redirect(url_for("income.index"))
