import csv
from io import StringIO

from flask import Blueprint, Response, abort, render_template, request
from flask_login import current_user, login_required

from app.advisor import engine
from app.calculations import month_bounds
from app.models import Expense, Income
from app.reports.pdf import build_report_pdf
from app.services import budget_chart, category_chart, get_snapshot, monthly_chart
from app.utils import csv_safe, parse_date_arg, period_from_request

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@login_required
def index():
    year, month = period_from_request()
    snap = get_snapshot(current_user, year, month)
    extras = engine.report_extras(snap)
    chart_data = {"category": category_chart(snap), "monthly": monthly_chart(snap),
                  "budget": budget_chart(snap), "currency": current_user.currency}
    return render_template("reports/index.html", snap=snap, extras=extras, year=year, month=month,
                           chart_data=chart_data)


@bp.route("/export/transactions.csv")
@login_required
def export_csv():
    """Export only the logged-in user's transactions (optionally one month)."""
    incomes = Income.query.filter_by(user_id=current_user.id)
    expenses = Expense.query.filter_by(user_id=current_user.id)
    name = "transactions-all"
    if request.args.get("scope") == "month":
        year, month = period_from_request()
        start, end = month_bounds(year, month)
        incomes = incomes.filter(Income.date >= start, Income.date < end)
        expenses = expenses.filter(Expense.date >= start, Expense.date < end)
        name = f"transactions-{year}-{month:02d}"
    else:
        start, end = parse_date_arg(request.args.get("start")), parse_date_arg(request.args.get("end"))
        if start:
            incomes, expenses = incomes.filter(Income.date >= start), expenses.filter(Expense.date >= start)
        if end:
            incomes, expenses = incomes.filter(Income.date <= end), expenses.filter(Expense.date <= end)

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(["Type", "Date", "Category / Source", "Amount", "Payment method", "Client", "Description", "Demo data"])
    rows = [("Income", r.date, r.source, r.amount, "", r.client, r.description, r.is_demo) for r in incomes]
    rows += [("Expense", r.date, r.category, r.amount, r.payment_method, "", r.description, r.is_demo) for r in expenses]
    rows.sort(key=lambda r: r[1])
    for kind, day, cat, amount, pay, client, desc, demo in rows:
        writer.writerow([kind, day.isoformat(), csv_safe(cat), f"{amount:.2f}", pay, csv_safe(client),
                         csv_safe(desc), "yes" if demo else "no"])
    body = "\ufeff" + out.getvalue()  # BOM so Excel on Mac/Windows reads UTF-8 correctly
    return Response(body, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@bp.route("/export/report.pdf")
@login_required
def export_pdf():
    year, month = period_from_request()
    snap = get_snapshot(current_user, year, month)
    try:
        pdf = build_report_pdf(snap, engine.report_extras(snap), current_user.name)
    except Exception:  # pragma: no cover - reportlab problem should not expose a stack trace
        abort(500)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="report-{year}-{month:02d}.pdf"'})
