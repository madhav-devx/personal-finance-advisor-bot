"""Built-in, deterministic financial recommendation engine.

Pure Python: it receives a *snapshot* dict (built from the database by
``app.services.get_snapshot``) and returns insights. It never touches the database,
so it works without any API key and is easy to test.

Snapshot keys
-------------
year, month, label, currency, profile_type, is_current_month
income_total, expense_total, balance, savings_rate (float or None)
category_totals {category: Decimal}      income_by_source / income_by_client
budgets {category: Decimal}              total_budget (Decimal or None)
previous {has_data, income, expense, balance, categories}
history [{year, month, label, income, expense}]  (6 months, oldest first)
income_history [Decimal]  (non-zero months, up to 6)
avg_expense, category_avg {category: Decimal}, income_variability (float or None)
goals [{name, target, saved, remaining, percent, status, required_monthly, ...}]
total_saved, emergency_saved, contributions_month, daily {day: Decimal}
"""
import math
import re
from decimal import ROUND_DOWN, Decimal

from app.calculations import ZERO, D, format_money, pct, q2
from app.constants import (
    CATEGORY_GUIDE_PCT, CATEGORY_LABELS, CATEGORY_TIPS, DEFAULT_BUDGET_WEIGHTS,
    EMERGENCY_MONTHS, NEEDS, PROFILE_GUIDE_OVERRIDES, SAVINGS_TARGET_RATE, WANTS,
)

LEVEL_ORDER = {"danger": 0, "warning": 1, "info": 2, "success": 3}


def _m(snap, value, decimals=0):
    return format_money(value, snap.get("currency", "₹"), decimals)


def _label(cat):
    return CATEGORY_LABELS.get(cat, str(cat).title())


def _insight(level, key, title, message):
    return {"level": level, "key": key, "title": title, "message": message}


def guide_pct(profile, category):
    override = PROFILE_GUIDE_OVERRIDES.get(profile, {})
    return override.get(category, CATEGORY_GUIDE_PCT.get(category, 10))


def top_categories(snap, n=3):
    total = snap["expense_total"]
    ranked = sorted(snap["category_totals"].items(), key=lambda kv: kv[1], reverse=True)
    return [(c, v, pct(v, total) or 0.0) for c, v in ranked[:n] if v > 0]


# ------------------------------------------------------------------ budgets
def budget_rows(snap):
    """Budget-versus-actual rows for every category that has a budget or spending."""
    rows = []
    cats = set(snap["budgets"]) | set(snap["category_totals"])
    for cat in sorted(cats, key=lambda c: snap["category_totals"].get(c, ZERO), reverse=True):
        limit = snap["budgets"].get(cat)
        spent = snap["category_totals"].get(cat, ZERO)
        row = {"category": cat, "label": _label(cat), "limit": limit, "spent": spent,
               "remaining": None, "percent": None, "level": "none"}
        if limit is not None and limit > 0:
            percent = float(spent / limit * 100)
            row["remaining"] = limit - spent
            row["percent"] = round(percent, 1)
            row["level"] = "over" if spent > limit else ("warn" if percent >= 80 else "ok")
        rows.append(row)
    return rows


def budget_utilization(snap):
    """Overall budget usage: uses the total budget when set, else the sum of category limits."""
    total_budget = snap.get("total_budget")
    if total_budget and total_budget > 0:
        limit, spent = total_budget, snap["expense_total"]
    elif snap["budgets"]:
        limit = sum(snap["budgets"].values(), ZERO)
        spent = sum((snap["category_totals"].get(c, ZERO) for c in snap["budgets"]), ZERO)
    else:
        return None
    if limit <= 0:
        return None
    percent = float(spent / limit * 100)
    level = "over" if spent > limit else ("warn" if percent >= 80 else "ok")
    return {"limit": limit, "spent": spent, "remaining": limit - spent,
            "percent": round(percent, 1), "level": level}


def budget_alerts(snap):
    alerts = []
    util = None
    total_budget = snap.get("total_budget")
    if total_budget and total_budget > 0:
        util = budget_utilization(snap)
        if util["level"] == "over":
            alerts.append(_insight("danger", "total_over", "Monthly budget exceeded",
                f"You have spent {_m(snap, util['spent'])} against a total budget of "
                f"{_m(snap, util['limit'])} - {_m(snap, -util['remaining'])} over."))
        elif util["level"] == "warn":
            alerts.append(_insight("warning", "total_warn", "Close to your monthly budget",
                f"You have used {util['percent']:.0f}% of your total budget "
                f"({_m(snap, util['remaining'])} left)."))
    for row in budget_rows(snap):
        if row["level"] == "over":
            alerts.append(_insight("danger", "over_" + row["category"], f"{row['label']} is over budget",
                f"{row['label']} spending is {_m(snap, row['spent'])} against a limit of "
                f"{_m(snap, row['limit'])} ({_m(snap, row['spent'] - row['limit'])} over)."))
        elif row["level"] == "warn":
            alerts.append(_insight("warning", "warn_" + row["category"], f"{row['label']} is nearing its limit",
                f"{row['label']} has used {row['percent']:.0f}% of its budget "
                f"({_m(snap, row['remaining'])} remaining)."))
    return alerts


# ------------------------------------------------------------------ guidance
def base_income(snap):
    """Income figure used for planning. Freelancers get a conservative 85% of their average."""
    hist = snap["income_history"]
    if snap["profile_type"] == "freelancer":
        if hist:
            return q2(sum(hist, ZERO) / Decimal(len(hist)) * Decimal("0.85"))
        return ZERO
    if snap["income_total"] > 0:
        return snap["income_total"]
    if hist:
        return q2(sum(hist, ZERO) / Decimal(len(hist)))
    return ZERO


def flagged_categories(snap):
    """Categories whose spending is well above the rule-of-thumb share of income."""
    income = snap["income_total"]
    if income <= 0:
        return []
    flagged = []
    for cat, spent in snap["category_totals"].items():
        guide_amt = income * Decimal(guide_pct(snap["profile_type"], cat)) / Decimal(100)
        excess = spent - guide_amt
        if spent > guide_amt * Decimal("1.25") and excess >= income * Decimal("0.03"):
            flagged.append({"category": cat, "label": _label(cat), "spent": spent,
                            "guide_amount": guide_amt, "excess": excess,
                            "share": pct(spent, income),
                            "guide_share": guide_pct(snap["profile_type"], cat)})
    flagged.sort(key=lambda f: f["excess"], reverse=True)
    return flagged


def emergency_fund_guidance(snap):
    essential = sum((v for c, v in snap["category_avg"].items() if c in NEEDS), ZERO)
    if essential <= 0 and snap["avg_expense"] > 0:
        essential = snap["avg_expense"] * Decimal("0.7")
    if essential <= 0:
        return None
    months_target = EMERGENCY_MONTHS.get(snap["profile_type"], 3)
    target = q2(essential * months_target)
    current = snap["emergency_saved"]
    gap = max(ZERO, target - current)
    base = base_income(snap)
    capacity = max(ZERO, base - snap["avg_expense"]) if base > 0 else ZERO
    monthly = q2(capacity * Decimal("0.5"))
    if gap == 0:
        months_to_goal = 0
    elif monthly > 0:
        months_to_goal = math.ceil(gap / monthly)
    else:
        months_to_goal = None
    return {"monthly_essential": q2(essential), "months_target": months_target, "target": target,
            "current": current, "gap": gap, "months_covered": float(current / essential),
            "monthly_contribution": monthly, "months_to_goal": months_to_goal}


def budget_suggestions(snap):
    """Suggest next month's category budgets. Never negative, never above spendable income."""
    base = base_income(snap)
    if base <= 0:
        return {"possible": False, "base_income": ZERO, "savings_target": ZERO, "spendable": ZERO,
                "categories": {}, "total": ZERO,
                "notes": ["Add income records so a realistic budget can be suggested."]}
    notes = []
    rate = Decimal(str(SAVINGS_TARGET_RATE.get(snap["profile_type"], 0.15)))
    savings_target = q2(base * rate)
    spendable = base - savings_target
    avg = {c: v for c, v in snap["category_avg"].items() if v > 0}

    if snap["profile_type"] == "freelancer":
        notes.append("Because freelance income varies, planning uses 85% of your average monthly income.")

    if not avg:
        suggestions = {c: spendable * Decimal(w) / Decimal(100) for c, w in DEFAULT_BUDGET_WEIGHTS.items()}
        notes.append("No spending history yet, so these are starting points based on typical proportions. "
                     "Refine them as you record expenses.")
    else:
        needs = {c: v for c, v in avg.items() if c in NEEDS}
        wants = {c: v * Decimal("0.85") for c, v in avg.items() if c in WANTS}
        total_needs = sum(needs.values(), ZERO)
        total_wants = sum(wants.values(), ZERO)
        if total_needs + total_wants > spendable:
            room = spendable - total_needs
            if room <= 0:
                scale = spendable / total_needs
                needs = {c: v * scale for c, v in needs.items()}
                wants = {}
                notes.append("Your essential spending alone is above what remains after your savings target. "
                             "Budgets were scaled down proportionally - consider reducing fixed costs or raising income.")
            else:
                scale = room / total_wants
                floors = {c: avg[c] * Decimal("0.5") for c in wants}
                wants = {c: max(v * scale, floors[c]) for c, v in wants.items()}
                notes.append("Discretionary categories (entertainment, shopping, other) were trimmed so your "
                             "budget leaves room for your savings target.")
        else:
            notes.append("Essentials follow your recent average spending; discretionary categories are set "
                         "about 15% below it.")
        suggestions = dict(needs)
        suggestions.update(wants)
        buffer = spendable * Decimal("0.03")
        if "other" not in suggestions and sum(suggestions.values(), ZERO) + buffer <= spendable:
            suggestions["other"] = buffer

    total = sum(suggestions.values(), ZERO)
    if total > spendable:  # final safety net
        scale = spendable / total
        suggestions = {c: v * scale for c, v in suggestions.items()}
    categories = {}
    for cat, value in suggestions.items():
        whole = max(ZERO, value).to_integral_value(rounding=ROUND_DOWN)
        if whole >= 1:
            categories[cat] = whole
    total = sum(categories.values(), ZERO)
    notes.append(f"Savings target: {_m(snap, savings_target)} "
                 f"({int(rate * 100)}% of {_m(snap, base)} planning income).")
    return {"possible": True, "base_income": base, "savings_target": savings_target,
            "spendable": spendable, "categories": categories, "total": total, "notes": notes}


# ------------------------------------------------------------------ scoring
def health_score(snap):
    income, expense = snap["income_total"], snap["expense_total"]
    if income <= 0 and expense <= 0:
        return {"score": None, "label": "Not enough data", "components": []}
    rate = snap["savings_rate"]
    savings_pts = 0.0 if rate is None else max(0.0, min(40.0, rate / 20.0 * 40.0))

    rows = [r for r in budget_rows(snap) if r["level"] != "none"]
    if rows:
        good = sum(1 for r in rows if r["level"] == "ok") + 0.5 * sum(1 for r in rows if r["level"] == "warn")
        budget_pts = 30.0 * good / len(rows)
    else:
        budget_pts = 15.0

    if income > 0:
        needs_total = sum((v for c, v in snap["category_totals"].items() if c in NEEDS), ZERO)
        ratio = float(needs_total / income)
        needs_pts = 15.0 if ratio <= 0.5 else max(0.0, 15.0 * (0.8 - ratio) / 0.3)
    else:
        needs_pts = 0.0

    ef = emergency_fund_guidance(snap)
    ef_pts = 0.0 if not ef else min(15.0, 15.0 * float(ef["current"] / ef["target"])) if ef["target"] > 0 else 0.0

    components = [
        {"name": "Savings rate", "points": round(savings_pts), "max": 40},
        {"name": "Budget adherence", "points": round(budget_pts), "max": 30},
        {"name": "Essential spending ratio", "points": round(needs_pts), "max": 15},
        {"name": "Emergency fund", "points": round(ef_pts), "max": 15},
    ]
    score = sum(c["points"] for c in components)
    label = "Excellent" if score >= 80 else "Good" if score >= 60 else "Needs attention" if score >= 40 else "At risk"
    return {"score": score, "label": label, "components": components}


# ------------------------------------------------------------------ insights
def generate_insights(snap):
    out = []
    income, expense = snap["income_total"], snap["expense_total"]
    label = snap["label"]
    profile = snap["profile_type"]

    if income <= 0 and expense <= 0:
        return [_insight("info", "no_data", "Start by adding your data",
                         f"Add your income and expenses for {label} (or load demo data from your profile) "
                         "and the advisor will analyse them.")]
    if income <= 0:
        out.append(_insight("warning", "no_income", "No income recorded",
                            f"You spent {_m(snap, expense)} in {label} but no income is recorded, so the savings "
                            "rate and budget suggestions cannot be calculated accurately. Add your income to unlock them."))
    else:
        balance, rate = snap["balance"], snap["savings_rate"]
        if balance < 0:
            out.append(_insight("danger", "overspent", "You spent more than you earned",
                                f"Expenses exceeded income by {_m(snap, -balance)} in {label}. Focus on the "
                                "highest flexible categories below and avoid new borrowing."))
        elif rate >= 20:
            out.append(_insight("success", "rate_great", "Strong savings rate",
                                f"You kept {_m(snap, balance)} ({rate:.0f}% of income) in {label}. "
                                "Consider directing part of it to your goals or emergency fund."))
        elif rate >= 10:
            out.append(_insight("info", "rate_ok", "Healthy but improvable savings rate",
                                f"You kept {_m(snap, balance)} ({rate:.0f}% of income). Many people aim for around "
                                "20%; a small trim in one category could get you closer."))
        else:
            out.append(_insight("warning", "rate_low", "Thin savings margin",
                                f"Only {_m(snap, balance)} ({rate:.0f}% of income) was left in {label}. "
                                "Review your largest flexible categories."))

    out.extend(budget_alerts(snap))

    for f in flagged_categories(snap)[:3]:
        tip = CATEGORY_TIPS.get(f["category"], [""])[0]
        out.append(_insight("warning", "high_" + f["category"], f"High spending on {f['label']}",
                            f"{f['label']} is {_m(snap, f['spent'])} ({f['share']:.0f}% of income) versus a "
                            f"rule-of-thumb of about {f['guide_share']}% for your profile. Bringing it near "
                            f"{_m(snap, f['guide_amount'])} could free up around {_m(snap, f['excess'])} a month. {tip}".strip()))

    prev = snap["previous"]
    if prev["has_data"]:
        threshold = max(Decimal(500), income * Decimal("0.02")) if income > 0 else Decimal(500)
        count = 0
        for cat, spent in sorted(snap["category_totals"].items(), key=lambda kv: kv[1], reverse=True):
            before = prev["categories"].get(cat, ZERO)
            if before > 0 and spent > before * Decimal("1.3") and spent - before >= threshold and count < 2:
                count += 1
                out.append(_insight("info", "up_" + cat, f"{_label(cat)} spending rose",
                                    f"{_label(cat)} went from {_m(snap, before)} last month to {_m(snap, spent)} "
                                    f"(+{_m(snap, spent - before)})."))

    if income > 0:
        wants_total = sum((snap["category_totals"].get(c, ZERO) for c in ("entertainment", "shopping")), ZERO)
        flagged_keys = {f["category"] for f in flagged_categories(snap)}
        if wants_total / income * 100 > 20 and not ({"entertainment", "shopping"} & flagged_keys):
            out.append(_insight("warning", "wants_high", "Discretionary spending is high",
                                f"Entertainment and shopping together take {float(wants_total / income * 100):.0f}% of income. "
                                "Trimming them by a fifth would add to your savings."))

    var = snap.get("income_variability")
    if profile == "freelancer" and var is not None and var > 0.4:
        out.append(_insight("warning", "variable_income", "Your income varies a lot",
                            f"Monthly income swings by roughly {var * 100:.0f}% of its average. Budget from your "
                            f"lower months (planning income: {_m(snap, base_income(snap))}) and move surplus from "
                            "strong months into your emergency fund."))

    if profile == "household" and snap["category_totals"]:
        top = ", ".join(f"{_label(c)} {_m(snap, v)}" for c, v, _ in top_categories(snap, 3))
        out.append(_insight("info", "household_top", "Shared household spending",
                            f"Your largest consolidated categories this month: {top}."))

    ef = emergency_fund_guidance(snap)
    if ef and ef["gap"] > 0:
        level = "warning" if ef["months_covered"] < 1 else "info"
        out.append(_insight(level, "emergency", "Build your emergency fund",
                            f"Your essentials cost about {_m(snap, ef['monthly_essential'])} a month. A "
                            f"{ef['months_target']}-month cushion is {_m(snap, ef['target'])}; you have "
                            f"{_m(snap, ef['current'])} set aside ({ef['months_covered']:.1f} months)."))

    for g in snap["goals"]:
        if g["status"] in ("behind", "overdue"):
            out.append(_insight("warning", "goal_" + g["name"], f"Goal needs attention: {g['name']}",
                                f"To reach {_m(snap, g['target'])} on time you would need about "
                                f"{_m(snap, g['required_monthly'])} a month; you are currently {g['status'].replace('_', ' ')}."))

    under = [r for r in budget_rows(snap) if r["level"] == "ok"]
    if under and not any(r["level"] in ("over", "warn") for r in budget_rows(snap)):
        out.append(_insight("success", "budgets_ok", "Budgets on track",
                            f"All {len(under)} budgeted categories are within their limits."))

    out.sort(key=lambda i: LEVEL_ORDER.get(i["level"], 9))
    return out


def expense_reduction_strategies(snap):
    flagged = flagged_categories(snap)
    items = []
    if flagged:
        for f in flagged[:3]:
            items.append({"category": f["category"], "label": f["label"], "amount": f["spent"],
                          "potential": f["excess"], "tips": CATEGORY_TIPS.get(f["category"], [])})
    else:
        for cat, value, _ in top_categories(snap, 2):
            items.append({"category": cat, "label": _label(cat), "amount": value, "potential": None,
                          "tips": CATEGORY_TIPS.get(cat, [])})
    return items


def saving_suggestions(snap):
    tips = []
    base = base_income(snap)
    rate = Decimal(str(SAVINGS_TARGET_RATE.get(snap["profile_type"], 0.15)))
    if base > 0:
        tips.append(f"Pay yourself first: move about {_m(snap, base * rate)} to savings as soon as income arrives "
                    f"({int(rate * 100)}% of planning income).")
    flagged = flagged_categories(snap)
    if flagged:
        total_potential = sum((f["excess"] for f in flagged), ZERO)
        tips.append(f"Bringing {', '.join(f['label'] for f in flagged)} closer to typical levels could free up "
                    f"about {_m(snap, total_potential)} per month.")
    if snap["profile_type"] == "freelancer":
        tips.append("In high-income months, set aside a tax and slow-month reserve before spending the surplus.")
    if snap["profile_type"] == "student":
        tips.append("Use student discounts and set a weekly cash limit for fun spending.")
    if snap["profile_type"] == "household":
        tips.append("Review shared bills together each month and agree on limits for groceries and utilities.")
    if not tips:
        tips.append("Record a few weeks of income and expenses and the advisor will tailor suggestions to you.")
    return tips


def monthly_summary(snap):
    health = health_score(snap)
    if snap["income_total"] <= 0 and snap["expense_total"] <= 0:
        return {"score": None, "label": health["label"],
                "text": f"No transactions recorded for {snap['label']} yet."}
    parts = [f"In {snap['label']} you earned {_m(snap, snap['income_total'])} and spent "
             f"{_m(snap, snap['expense_total'])}"]
    if snap["income_total"] > 0:
        parts[0] += f", leaving {_m(snap, snap['balance'])} ({snap['savings_rate']:.0f}% savings rate)."
    else:
        parts[0] += "."
    top = top_categories(snap, 1)
    if top:
        parts.append(f"Your largest category was {_label(top[0][0])} at {_m(snap, top[0][1])} "
                     f"({top[0][2]:.0f}% of spending).")
    if health["score"] is not None:
        parts.append(f"Financial health score: {health['score']}/100 ({health['label']}).")
    return {"score": health["score"], "label": health["label"], "text": " ".join(parts)}


def report_extras(snap):
    """Everything the monthly report adds on top of the raw snapshot."""
    prev = snap["previous"]
    comparison = None
    if prev["has_data"]:
        comparison = {"income_change": snap["income_total"] - prev["income"],
                      "expense_change": snap["expense_total"] - prev["expense"],
                      "balance_change": snap["balance"] - prev["balance"],
                      "prev_income": prev["income"], "prev_expense": prev["expense"],
                      "prev_balance": prev["balance"]}
    return {"top_categories": top_categories(snap, 3), "budget_rows": budget_rows(snap),
            "utilization": budget_utilization(snap), "comparison": comparison,
            "observations": generate_insights(snap)[:6], "summary": monthly_summary(snap),
            "health": health_score(snap)}


# ------------------------------------------------------------------ chat
def _lines(*items):
    return "\n".join(i for i in items if i)


def answer_question(question, snap):
    """Rule-based answer to a free-text question, grounded in the snapshot."""
    q = (question or "").lower()
    m = lambda v: _m(snap, v)

    if snap["income_total"] <= 0 and snap["expense_total"] <= 0:
        return ("I do not see any transactions for " + snap["label"] + " yet. Add income and expenses "
                "(or load demo data from your profile) and ask me again.")

    if re.search(r"\b(invest|stock|mutual fund|crypto|returns?|sip|shares?|bitcoin)\b", q):
        ef = emergency_fund_guidance(snap)
        extra = ""
        if ef and ef["gap"] > 0:
            extra = (f"Based on your records, building your emergency fund (about {m(ef['gap'])} still to go) "
                     "is usually the first priority.")
        return _lines("I cannot recommend specific investments or predict returns - markets carry risk and "
                      "outcomes are never guaranteed. For investing decisions, consider a licensed financial adviser.",
                      extra)

    if "emergency" in q:
        ef = emergency_fund_guidance(snap)
        if not ef:
            return "I need some expense history to estimate an emergency fund target."
        when = ("You have reached it." if ef["gap"] == 0 else
                f"At about {m(ef['monthly_contribution'])} a month you could get there in "
                f"{ef['months_to_goal']} months." if ef["months_to_goal"] else
                "Your current surplus is too small to build it quickly - start by freeing up some budget.")
        return _lines(f"Your essential spending is about {m(ef['monthly_essential'])} a month.",
                      f"A {ef['months_target']}-month emergency fund is {m(ef['target'])}; you have set aside "
                      f"{m(ef['current'])} ({ef['months_covered']:.1f} months).", when)

    if re.search(r"next month|plan|budget", q):
        s = budget_suggestions(snap)
        if not s["possible"]:
            return s["notes"][0]
        rows = [f"- {_label(c)}: {m(v)}" for c, v in sorted(s["categories"].items(), key=lambda kv: -kv[1])]
        return _lines("Suggested budget for next month:", *rows,
                      f"Total planned spending {m(s['total'])}, leaving at least {m(s['savings_target'])} for savings.",
                      *s["notes"][:2])

    if re.search(r"overspen|too much|biggest|highest|top|where|which categor", q):
        top = top_categories(snap, 3)
        rows = [f"- {_label(c)}: {m(v)} ({p:.0f}% of spending)" for c, v, p in top]
        flagged = flagged_categories(snap)
        flag_line = ("Categories above typical levels: " + ", ".join(f["label"] for f in flagged) + "."
                     if flagged else "None of your categories is far above typical levels.")
        return _lines("Your highest-spending categories:", *rows, flag_line)

    if re.search(r"save|saving|reduce|cut|lower|spend less", q):
        strategies = expense_reduction_strategies(snap)
        rows = []
        for s in strategies:
            pot = f" (potential saving about {m(s['potential'])}/month)" if s["potential"] else ""
            rows.append(f"- {s['label']}{pot}: {s['tips'][0] if s['tips'] else ''}")
        return _lines("Practical ways to save more:", *saving_suggestions(snap)[:2], *rows)

    if "goal" in q:
        if not snap["goals"]:
            return "You have no savings goals yet. Create one on the Savings Goals page to track progress."
        rows = [f"- {g['name']}: {m(g['saved'])} of {m(g['target'])} ({g['percent']:.0f}%), "
                f"{g['status'].replace('_', ' ')}" for g in snap["goals"]]
        return _lines("Your savings goals:", *rows)

    summary = monthly_summary(snap)
    insights = [i for i in generate_insights(snap) if i["level"] in ("danger", "warning")][:2]
    return _lines(summary["text"], *[f"- {i['title']}: {i['message']}" for i in insights],
                  "You can also ask about saving, overspending, next month's budget, goals or your emergency fund.")


# ------------------------------------------------------------------ AI helpers
def snapshot_to_plain(snap):
    """Aggregated, JSON-serialisable figures for an optional external AI call (no identity data)."""
    def conv(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, dict):
            return {str(k): conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return v
    keep = ["label", "currency", "profile_type", "income_total", "expense_total", "balance", "savings_rate",
            "category_totals", "budgets", "total_budget", "previous", "history", "category_avg", "goals",
            "emergency_saved", "income_variability"]
    return conv({k: snap.get(k) for k in keep})


AI_SYSTEM_PROMPT = (
    "You are an educational personal-finance assistant inside a budgeting app. Use ONLY the figures provided "
    "in the JSON. Do not invent numbers. Do not recommend specific securities or promise investment returns. "
    "Be concise, practical and friendly, and end with a one-line reminder that this is educational, not "
    "financial advice."
)
