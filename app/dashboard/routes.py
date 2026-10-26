from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.advisor import engine
from app.models import Expense, Income
from app.services import (budget_chart, category_chart, daily_chart, get_snapshot, monthly_chart)
from app.utils import period_from_request

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    year, month = period_from_request()
    snap = get_snapshot(current_user, year, month)

    recent = []
    for r in Income.query.filter_by(user_id=current_user.id).order_by(Income.date.desc(), Income.id.desc()).limit(8):
        recent.append({"type": "income", "date": r.date, "label": r.source, "description": r.description,
                       "amount": r.amount, "demo": r.is_demo, "id": r.id})
    for r in Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc(), Expense.id.desc()).limit(8):
        recent.append({"type": "expense", "date": r.date, "label": r.category, "description": r.description,
                       "amount": r.amount, "demo": r.is_demo, "id": r.id})
    recent.sort(key=lambda x: (x["date"], x["id"]), reverse=True)

    chart_data = {"category": category_chart(snap), "monthly": monthly_chart(snap),
                  "daily": daily_chart(snap), "currency": current_user.currency}
    insights = engine.generate_insights(snap)
    has_data = bool(Income.query.filter_by(user_id=current_user.id).first()
                    or Expense.query.filter_by(user_id=current_user.id).first())
    return render_template(
        "dashboard/index.html", snap=snap, year=year, month=month, recent=recent[:8],
        chart_data=chart_data, insights=insights[:5], health=engine.health_score(snap),
        utilization=engine.budget_utilization(snap), alerts=engine.budget_alerts(snap),
        has_data=has_data)
