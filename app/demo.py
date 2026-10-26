"""Optional demo-data generator. Everything it creates is flagged is_demo=True.

It only ever ADDS records (never edits or deletes the user's own data) and refuses to run
twice, so existing data can't be overwritten. ``remove_demo_data`` deletes only flagged rows.
"""
from datetime import date
from decimal import Decimal

from app.calculations import last_day_of_month, shift_month
from app.constants import TOTAL_BUDGET_KEY
from app.extensions import db
from app.models import Budget, Expense, Income, SavingsContribution, SavingsGoal

# (category, day, amount, payment, description) per month; amounts nudged slightly each month.
SCENARIOS = {
    "salaried": {
        "incomes": [("salary", None, 1, 85000, "Monthly salary")],
        "expenses": [
            ("rent", 1, 22000, "net_banking", "Apartment rent"),
            ("groceries", 6, 3200, "upi", "Weekly groceries"), ("groceries", 20, 2800, "upi", "Groceries"),
            ("food", 9, 3500, "credit_card", "Restaurants & delivery"), ("food", 23, 4200, "upi", "Dining out"),
            ("transport", 5, 2400, "upi", "Fuel"), ("transport", 18, 2100, "cash", "Cab rides"),
            ("utilities", 8, 3200, "net_banking", "Electricity, internet, phone"),
            ("entertainment", 12, 4500, "credit_card", "Concert & streaming"), ("entertainment", 25, 3000, "upi", "Weekend outing"),
            ("shopping", 15, 5500, "credit_card", "Clothes"), ("healthcare", 17, 1500, "upi", "Pharmacy"),
        ],
        "budgets": {"total": 70000, "rent": 22000, "food": 8000, "groceries": 6500, "transport": 5000,
                    "utilities": 3500, "entertainment": 5000, "shopping": 4000},
        "goals": [("Emergency fund", 255000, 8, True, 30000), ("Europe trip", 180000, 12, False, 15000)],
    },
    "student": {
        "incomes": [("allowance", None, 1, 8000, "Monthly allowance from parents")],
        "expenses": [
            ("food", 3, 1500, "upi", "Canteen & mess"), ("food", 17, 1500, "upi", "Food delivery"),
            ("entertainment", 10, 1200, "upi", "Movies & games"), ("entertainment", 22, 800, "upi", "Streaming & outings"),
            ("transport", 6, 800, "cash", "Bus pass & auto"), ("education", 9, 1000, "upi", "Books & printouts"),
            ("shopping", 20, 500, "upi", "Accessories"), ("other", 24, 300, "cash", "Miscellaneous"),
        ],
        "budgets": {"total": 7000, "food": 2500, "entertainment": 1000, "transport": 800, "education": 1000, "shopping": 400},
        "goals": [("Laptop", 45000, 10, False, 6000)],
    },
    "freelancer": {
        "incomes": [("freelance", "Acme Studio", 5, 38000, "Website project"),
                    ("freelance", "Bright Labs", 14, 22000, "App design retainer"),
                    ("freelance", "Nova Media", 24, 15000, "Video editing")],
        "expenses": [
            ("rent", 1, 15000, "net_banking", "Home office rent"), ("food", 8, 4500, "upi", "Food & coffee"),
            ("groceries", 10, 5000, "upi", "Groceries"), ("transport", 12, 2000, "upi", "Travel to clients"),
            ("utilities", 7, 2800, "net_banking", "Internet & phone"),
            ("business", 4, 3500, "credit_card", "Design software subscriptions"),
            ("business", 16, 4200, "credit_card", "Coworking space"), ("entertainment", 20, 2500, "upi", "Leisure"),
            ("healthcare", 18, 1200, "upi", "Health check"),
        ],
        "budgets": {"total": 50000, "rent": 15000, "food": 5000, "groceries": 5500, "business": 7000},
        "goals": [("Emergency fund", 180000, 10, True, 20000)],
    },
    "household": {
        "incomes": [("salary", None, 1, 110000, "Primary salary"), ("salary", None, 3, 45000, "Spouse salary")],
        "expenses": [
            ("rent", 1, 30000, "net_banking", "Home loan EMI / rent"),
            ("groceries", 4, 6500, "upi", "Groceries"), ("groceries", 12, 6000, "upi", "Groceries"),
            ("groceries", 20, 6500, "upi", "Groceries & household items"),
            ("utilities", 8, 8500, "net_banking", "Electricity, gas, water, internet"),
            ("education", 5, 14000, "net_banking", "School fees"), ("healthcare", 15, 6000, "upi", "Family medical"),
            ("transport", 9, 6500, "upi", "Fuel & maintenance"), ("food", 22, 5500, "credit_card", "Family dining"),
            ("entertainment", 26, 4000, "upi", "Family outing"), ("shopping", 18, 7000, "credit_card", "Household shopping"),
        ],
        "budgets": {"total": 110000, "groceries": 15000, "utilities": 8000, "education": 14000,
                    "healthcare": 5000, "entertainment": 3000},
        "goals": [("Emergency fund", 480000, 14, True, 40000), ("Child education fund", 300000, 24, False, 20000)],
    },
}


def has_demo_data(user):
    return any(model.query.filter_by(user_id=user.id, is_demo=True).first() is not None
               for model in (Income, Expense, Budget, SavingsGoal))


def _day(year, month, day, today):
    d = date(year, month, min(day, last_day_of_month(year, month)))
    return min(d, today)


def generate_demo_data(user, scenario, today=None):
    """Add three months of demo data. Returns False (and changes nothing) if demo data already exists."""
    if scenario not in SCENARIOS or has_demo_data(user):
        return False
    today = today or date.today()
    spec = SCENARIOS[scenario]
    for offset, factor in ((-2, Decimal("0.96")), (-1, Decimal("1.03")), (0, Decimal("1.00"))):
        y, m = shift_month(today.year, today.month, offset)
        for source, client, day, amount, desc in spec["incomes"]:
            adj = Decimal(amount) * (factor if scenario == "freelancer" else Decimal(1))
            db.session.add(Income(user_id=user.id, amount=adj.quantize(Decimal("1")), source=source,
                                  client=client, date=_day(y, m, day, today), description="[Demo] " + desc, is_demo=True))
        for category, day, amount, payment, desc in spec["expenses"]:
            adj = (Decimal(amount) * factor).quantize(Decimal("1"))
            db.session.add(Expense(user_id=user.id, amount=adj, category=category, date=_day(y, m, day, today),
                                   payment_method=payment, description="[Demo] " + desc, is_demo=True))
        for category, amount in spec["budgets"].items():
            exists = Budget.query.filter_by(user_id=user.id, year=y, month=m, category=category).first()
            if exists is None:  # never overwrite a budget the user already set
                db.session.add(Budget(user_id=user.id, year=y, month=m, category=category,
                                      amount=Decimal(amount), is_demo=True))
    for name, target, months, emergency, saved in spec["goals"]:
        ty, tm = shift_month(today.year, today.month, months)
        goal = SavingsGoal(user_id=user.id, name="[Demo] " + name, target_amount=Decimal(target),
                           target_date=date(ty, tm, min(today.day, last_day_of_month(ty, tm))),
                           description="Demo goal", is_emergency=emergency, is_demo=True)
        db.session.add(goal)
        db.session.flush()
        for i, offset in enumerate((-2, -1, 0)):
            y, m = shift_month(today.year, today.month, offset)
            db.session.add(SavingsContribution(goal_id=goal.id, user_id=user.id, amount=Decimal(saved) / 3,
                                               date=_day(y, m, 5 + i, today), note="Demo contribution", is_demo=True))
    db.session.commit()
    return True


def remove_demo_data(user):
    """Delete only rows flagged as demo data for this user."""
    removed = 0
    for model in (SavingsContribution, Income, Expense, Budget):
        removed += model.query.filter_by(user_id=user.id, is_demo=True).delete(synchronize_session=False)
    for goal in SavingsGoal.query.filter_by(user_id=user.id, is_demo=True).all():
        db.session.delete(goal)  # ORM cascade removes any remaining contributions
        removed += 1
    db.session.commit()
    return removed
