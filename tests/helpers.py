"""Shared test helpers (pure Python - no Flask or database)."""
from decimal import Decimal as Dm

Z = Dm(0)


def make_snapshot(**overrides):
    """A student-like snapshot: income 8000, food 3000, entertainment 2000 (the spec's example)."""
    cats = {"food": Dm(3000), "entertainment": Dm(2000), "transport": Dm(800),
            "education": Dm(1000), "shopping": Dm(500), "other": Dm(300)}
    snap = dict(
        year=2026, month=10, label="October 2026", currency="₹", profile_type="student", is_current_month=True,
        income_total=Dm(8000), expense_total=Dm(7600), balance=Dm(400), savings_rate=5.0,
        category_totals=dict(cats), income_by_source={"allowance": Dm(8000)}, income_by_client={},
        budgets={}, total_budget=None,
        previous=dict(has_data=False, income=Z, expense=Z, balance=Z, categories={}),
        history=[], income_history=[Dm(8000)], avg_expense=Dm(7600), category_avg=dict(cats),
        income_variability=None, goals=[], total_saved=Z, emergency_saved=Z, contributions_month=Z, daily={},
    )
    snap.update(overrides)
    return snap
