"""Database-backed calculations: builds the snapshot consumed by the advisor engine."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.advisor.engine import budget_rows  # noqa: F401  (re-exported for convenience)
from app.calculations import (ZERO, average, last_day_of_month, month_bounds, month_label, pct,
                              shift_month)
from app.constants import TOTAL_BUDGET_KEY
from app.models import Budget, Expense, Income, SavingsContribution, SavingsGoal


def get_snapshot(user, year, month, today=None):
    """Aggregate everything the advisor/dashboard/report needs for one user and month."""
    today = today or date.today()
    periods = [shift_month(year, month, d) for d in range(-5, 1)]
    window_start = date(periods[0][0], periods[0][1], 1)
    _, window_end = month_bounds(year, month)

    incomes = Income.query.filter(Income.user_id == user.id, Income.date >= window_start,
                                  Income.date < window_end).all()
    expenses = Expense.query.filter(Expense.user_id == user.id, Expense.date >= window_start,
                                    Expense.date < window_end).all()

    inc_by = defaultdict(Decimal)
    exp_by = defaultdict(Decimal)
    cat_by = defaultdict(lambda: defaultdict(Decimal))
    income_by_source, income_by_client = defaultdict(Decimal), defaultdict(Decimal)
    daily = defaultdict(Decimal)
    current = (year, month)

    for r in incomes:
        key = (r.date.year, r.date.month)
        inc_by[key] += r.amount
        if key == current:
            income_by_source[r.source] += r.amount
            income_by_client[r.client or "Unspecified"] += r.amount
    for r in expenses:
        key = (r.date.year, r.date.month)
        exp_by[key] += r.amount
        cat_by[key][r.category] += r.amount
        if key == current:
            daily[r.date.day] += r.amount

    income_total, expense_total = inc_by[current], exp_by[current]
    balance = income_total - expense_total
    prev_key = periods[-2]
    previous = {
        "has_data": inc_by[prev_key] > 0 or exp_by[prev_key] > 0,
        "income": inc_by[prev_key], "expense": exp_by[prev_key],
        "balance": inc_by[prev_key] - exp_by[prev_key], "categories": dict(cat_by[prev_key]),
    }
    history = [{"year": y, "month": m, "label": month_label(y, m)[:3] + " " + str(y)[2:],
                "income": inc_by[(y, m)], "expense": exp_by[(y, m)]} for y, m in periods]
    income_history = [inc_by[p] for p in periods if inc_by[p] > 0]

    # Averages: when the selected month is still in progress, prefer completed months.
    last3 = periods[-3:]
    in_progress = (today.year, today.month) == current and today.day < last_day_of_month(year, month)
    completed = [p for p in last3[:-1] if exp_by[p] > 0]
    avg_periods = completed if (in_progress and completed) else [p for p in last3 if exp_by[p] > 0]
    avg_expense = average(exp_by[p] for p in avg_periods)
    category_avg = {}
    if avg_periods:
        cats = {c for p in avg_periods for c in cat_by[p]}
        for c in cats:
            category_avg[c] = sum((cat_by[p].get(c, ZERO) for p in avg_periods), ZERO) / Decimal(len(avg_periods))

    variability = None
    if len(income_history) >= 2:
        mean = sum(income_history, ZERO) / Decimal(len(income_history))
        if mean > 0:
            variability = float((max(income_history) - min(income_history)) / mean)

    budgets, total_budget = {}, None
    for b in Budget.query.filter_by(user_id=user.id, year=year, month=month).all():
        if b.category == TOTAL_BUDGET_KEY:
            total_budget = b.amount
        else:
            budgets[b.category] = b.amount

    goals, total_saved, emergency_saved = [], ZERO, ZERO
    for g in SavingsGoal.query.filter_by(user_id=user.id).order_by(SavingsGoal.target_date).all():
        prog = g.progress(today)
        prog.update({"id": g.id, "name": g.name, "target_date": g.target_date, "is_emergency": g.is_emergency})
        goals.append(prog)
        total_saved += prog["saved"]
        if g.is_emergency:
            emergency_saved += prog["saved"]

    start, end = month_bounds(year, month)
    contributions_month = sum((c.amount for c in SavingsContribution.query.filter(
        SavingsContribution.user_id == user.id, SavingsContribution.date >= start,
        SavingsContribution.date < end).all()), ZERO)

    return {
        "year": year, "month": month, "label": month_label(year, month), "currency": user.currency,
        "profile_type": user.profile_type, "is_current_month": current == (today.year, today.month),
        "income_total": income_total, "expense_total": expense_total, "balance": balance,
        "savings_rate": pct(balance, income_total),
        "category_totals": dict(sorted(cat_by[current].items(), key=lambda kv: kv[1], reverse=True)),
        "income_by_source": dict(income_by_source), "income_by_client": dict(income_by_client),
        "budgets": budgets, "total_budget": total_budget, "previous": previous, "history": history,
        "income_history": income_history, "avg_expense": avg_expense, "category_avg": category_avg,
        "income_variability": variability, "goals": goals, "total_saved": total_saved,
        "emergency_saved": emergency_saved, "contributions_month": contributions_month,
        "daily": dict(daily),
    }


def category_chart(snap):
    from app.constants import CATEGORY_COLORS, CATEGORY_LABELS
    items = [(c, v) for c, v in snap["category_totals"].items() if v > 0]
    return {"labels": [CATEGORY_LABELS.get(c, c) for c, _ in items], "values": [float(v) for _, v in items],
            "colors": [CATEGORY_COLORS.get(c, "#94a3b8") for c, _ in items]}


def monthly_chart(snap):
    return {"labels": [h["label"] for h in snap["history"]],
            "income": [float(h["income"]) for h in snap["history"]],
            "expense": [float(h["expense"]) for h in snap["history"]]}


def daily_chart(snap):
    days = last_day_of_month(snap["year"], snap["month"])
    return {"labels": [str(d) for d in range(1, days + 1)],
            "values": [float(snap["daily"].get(d, 0)) for d in range(1, days + 1)]}


def budget_chart(snap):
    from app.constants import CATEGORY_LABELS
    rows = [r for r in budget_rows(snap) if r["limit"] is not None]
    return {"labels": [CATEGORY_LABELS.get(r["category"], r["category"]) for r in rows],
            "budget": [float(r["limit"]) for r in rows], "actual": [float(r["spent"]) for r in rows]}
