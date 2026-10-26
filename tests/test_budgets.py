from datetime import date
from decimal import Decimal

from app.advisor import engine
from app.models import Budget, User
from app.services import get_snapshot

TODAY = date.today()


def _post_period(extra):
    return {"year": TODAY.year, "month": TODAY.month, **extra}


def _user(email):
    return User.query.filter_by(email=email).one()


def test_set_and_clear_budgets(app, user_a):
    r = user_a.post("/budgets/save", data=_post_period({"total": "30000", "cat_food": "5000", "cat_rent": "15000"}), follow_redirects=True)
    assert b"Budgets saved" in r.data
    rows = {b.category: b.amount for b in Budget.query.all()}
    assert rows == {"total": Decimal("30000"), "food": Decimal("5000"), "rent": Decimal("15000")}
    user_a.post("/budgets/save", data=_post_period({"total": "30000", "cat_food": ""}), follow_redirects=True)
    assert {b.category for b in Budget.query.all()} == {"total"}   # blank fields remove limits


def test_invalid_budget_values_rejected(app, user_a):
    for bad in ("-5", "abc", "0"):
        r = user_a.post("/budgets/save", data=_post_period({"cat_food": bad}), follow_redirects=True)
        assert b"positive amount" in r.data
    assert Budget.query.count() == 0


def test_warning_at_80_percent_and_overspend_alert(app, user_a):
    user_a.post("/budgets/save", data=_post_period({"cat_food": "1000", "cat_rent": "1000"}))
    user_a.post("/expenses/new", data={"amount": "850", "category": "food", "date": TODAY.isoformat(), "payment_method": "upi"})
    user_a.post("/expenses/new", data={"amount": "1200", "category": "rent", "date": TODAY.isoformat(), "payment_method": "upi"})
    snap = get_snapshot(_user("a@example.com"), TODAY.year, TODAY.month)
    levels = {r["category"]: r["level"] for r in engine.budget_rows(snap)}
    assert levels == {"rent": "over", "food": "warn"}
    html = user_a.get("/budgets/").get_data(as_text=True)
    assert "nearing its limit" in html and "over budget" in html


def test_budget_suggestions_from_real_data_are_valid(app, user_a):
    user_a.post("/income/new", data={"amount": "8000", "source": "allowance", "date": TODAY.isoformat()})
    for cat, amt in (("food", 3000), ("entertainment", 2000), ("transport", 800)):
        user_a.post("/expenses/new", data={"amount": str(amt), "category": cat, "date": TODAY.isoformat(), "payment_method": "upi"})
    snap = get_snapshot(_user("a@example.com"), TODAY.year, TODAY.month)
    s = engine.budget_suggestions(snap)
    assert s["possible"] and s["total"] <= Decimal("8000") and all(v >= 0 for v in s["categories"].values())
    user_a.post("/budgets/apply-suggestions", data=_post_period({}), follow_redirects=True)
    saved = {b.category: b.amount for b in Budget.query.all() if b.category != "total"}
    assert saved and all(v > 0 for v in saved.values())


def test_budgets_are_private(app, user_a, user_b):
    user_a.post("/budgets/save", data=_post_period({"cat_food": "1234"}))
    assert "1,234" not in user_b.get("/budgets/").get_data(as_text=True)
