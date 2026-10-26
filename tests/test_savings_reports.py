from datetime import date, timedelta
from decimal import Decimal

from app.demo import generate_demo_data, has_demo_data, remove_demo_data
from app.models import Expense, Income, SavingsContribution, SavingsGoal, User
from app.services import get_snapshot

TODAY = date.today()


def _user(email):
    return User.query.filter_by(email=email).one()


def _new_goal(client, name="Laptop", target="40000", emergency=False):
    data = {"name": name, "target_amount": target, "target_date": (TODAY + timedelta(days=180)).isoformat(), "description": "x"}
    if emergency:
        data["is_emergency"] = "y"
    return client.post("/savings/new", data=data, follow_redirects=True)


def test_goal_lifecycle_and_progress(app, user_a):
    assert b"Savings goal created" in _new_goal(user_a).data
    goal = SavingsGoal.query.one()
    user_a.post(f"/savings/{goal.id}", data={"amount": "10000", "date": TODAY.isoformat(), "note": "first"}, follow_redirects=True)
    user_a.post(f"/savings/{goal.id}", data={"amount": "5000", "date": TODAY.isoformat()}, follow_redirects=True)
    prog = goal.progress()
    assert prog["saved"] == Decimal("15000") and prog["remaining"] == Decimal("25000") and prog["percent"] == 37.5
    assert "37.5%" in user_a.get(f"/savings/{goal.id}").get_data(as_text=True)
    contribution = SavingsContribution.query.first()
    user_a.post(f"/savings/{goal.id}/contributions/{contribution.id}/delete")
    assert SavingsContribution.query.count() == 1
    user_a.post(f"/savings/{goal.id}/edit", data={"name": "Gaming laptop", "target_amount": "50000",
                                                  "target_date": (TODAY + timedelta(days=90)).isoformat()}, follow_redirects=True)
    assert SavingsGoal.query.one().name == "Gaming laptop"
    user_a.post(f"/savings/{goal.id}/delete", follow_redirects=True)
    assert SavingsGoal.query.count() == 0 and SavingsContribution.query.count() == 0   # cascade


def test_goals_are_private_and_validated(app, user_a, user_b):
    _new_goal(user_a)
    goal = SavingsGoal.query.one()
    assert user_b.get(f"/savings/{goal.id}").status_code == 404
    assert user_b.post(f"/savings/{goal.id}", data={"amount": "5", "date": TODAY.isoformat()}).status_code == 404
    assert user_b.post(f"/savings/{goal.id}/delete").status_code == 404
    user_a.post("/savings/new", data={"name": "Bad", "target_amount": "-1", "target_date": TODAY.isoformat()})
    assert SavingsGoal.query.count() == 1


def test_emergency_goal_feeds_snapshot(app, user_a):
    _new_goal(user_a, "Emergency fund", "90000", emergency=True)
    goal = SavingsGoal.query.one()
    user_a.post(f"/savings/{goal.id}", data={"amount": "12000", "date": TODAY.isoformat()})
    snap = get_snapshot(_user("a@example.com"), TODAY.year, TODAY.month)
    assert snap["emergency_saved"] == Decimal("12000") and snap["total_saved"] == Decimal("12000")


def test_monthly_report_calculations(app, user_a):
    user_a.post("/income/new", data={"amount": "40000", "source": "freelance", "client": "A", "date": TODAY.isoformat()})
    user_a.post("/income/new", data={"amount": "20000", "source": "freelance", "client": "B", "date": TODAY.isoformat()})
    user_a.post("/expenses/new", data={"amount": "30000", "category": "rent", "date": TODAY.isoformat(), "payment_method": "upi"})
    snap = get_snapshot(_user("a@example.com"), TODAY.year, TODAY.month)
    assert snap["income_by_client"] == {"A": Decimal("40000"), "B": Decimal("20000")}
    assert snap["balance"] == Decimal("30000") and snap["savings_rate"] == 50.0
    html = user_a.get(f"/reports/?year={TODAY.year}&month={TODAY.month}").get_data(as_text=True)
    assert "60,000" in html and "30,000" in html and "50.0%" in html


def test_report_month_comparison_and_invalid_period(app, user_a):
    prev = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=10)
    user_a.post("/expenses/new", data={"amount": "1000", "category": "food", "date": prev.isoformat(), "payment_method": "upi"})
    user_a.post("/expenses/new", data={"amount": "2500", "category": "food", "date": TODAY.isoformat(), "payment_method": "upi"})
    snap = get_snapshot(_user("a@example.com"), TODAY.year, TODAY.month)
    assert snap["previous"]["has_data"] and snap["previous"]["expense"] == Decimal("1000")
    assert user_a.get("/reports/?year=abc&month=99").status_code == 200      # bad input falls back safely


def test_pdf_and_csv_exports(app, user_a):
    user_a.post("/income/new", data={"amount": "1000", "source": "salary", "date": TODAY.isoformat()})
    pdf = user_a.get(f"/reports/export/report.pdf?year={TODAY.year}&month={TODAY.month}")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF") and pdf.mimetype == "application/pdf"
    csv_month = user_a.get(f"/reports/export/transactions.csv?scope=month&year={TODAY.year}&month={TODAY.month}")
    assert csv_month.status_code == 200 and "attachment" in csv_month.headers["Content-Disposition"]
    assert "Income" in csv_month.get_data(as_text=True)


def test_demo_data_is_labelled_additive_and_removable(app, user_a):
    user_a.post("/income/new", data={"amount": "123", "source": "gift", "date": TODAY.isoformat(), "description": "mine"})
    user = _user("a@example.com")
    assert generate_demo_data(user, "salaried") is True and has_demo_data(user)
    assert generate_demo_data(user, "student") is False             # never stacks or overwrites
    assert Income.query.filter_by(is_demo=False).count() == 1       # the user's own record is untouched
    assert all(r.description.startswith("[Demo]") for r in Expense.query.filter_by(is_demo=True))
    snap = get_snapshot(user, TODAY.year, TODAY.month)
    assert snap["income_total"] > 0 and snap["budgets"]
    removed = remove_demo_data(user)
    assert removed > 0 and not has_demo_data(user)
    assert Income.query.count() == 1 and Income.query.one().description == "mine"
    assert SavingsGoal.query.count() == 0 and SavingsContribution.query.count() == 0


def test_all_four_scenarios_generate_and_render(app, make_client):
    for i, scenario in enumerate(("salaried", "student", "freelancer", "household")):
        client = make_client(f"s{i}@example.com", profile=scenario)
        assert generate_demo_data(_user(f"s{i}@example.com"), scenario)
        for path in ("/dashboard", "/advisor/", "/reports/", "/budgets/", "/savings/", "/income/", "/expenses/"):
            assert client.get(path).status_code == 200, (scenario, path)


def test_profile_update_and_password_change(app, user_a):
    r = user_a.post("/profile", data={"name": "Alice B", "profile_type": "freelancer", "currency": "$"}, follow_redirects=True)
    assert b"Profile updated" in r.data
    user = _user("a@example.com")
    assert user.profile_type == "freelancer" and user.currency == "$" and user.ai_consent is False
    user_a.post("/profile/password", data={"current_password": "Password123", "new_password": "NewPass456", "confirm": "NewPass456"})
    assert _user("a@example.com").check_password("NewPass456")
