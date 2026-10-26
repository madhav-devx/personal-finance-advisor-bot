from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Expense, Income, User
from app.services import get_snapshot

TODAY = date.today().isoformat()


def uid(email):
    return User.query.filter_by(email=email).one().id


def test_income_add_edit_delete(app, user_a):
    r = user_a.post("/income/new", data={"amount": "50000", "source": "salary", "date": TODAY, "description": "Pay"},
                    follow_redirects=True)
    assert b"Income added" in r.data
    rec = Income.query.filter_by(user_id=uid("a@example.com")).one()
    assert rec.amount == Decimal("50000.00") and rec.source == "salary"
    r = user_a.post(f"/income/{rec.id}/edit", data={"amount": "52000.50", "source": "freelance", "client": "Acme",
                                                    "date": TODAY, "description": "Updated"}, follow_redirects=True)
    assert b"Income updated" in r.data
    db.session.refresh(rec)
    assert rec.amount == Decimal("52000.50") and rec.client == "Acme"
    user_a.post(f"/income/{rec.id}/delete", follow_redirects=True)
    assert Income.query.count() == 0


def test_expense_add_edit_delete(app, user_a):
    r = user_a.post("/expenses/new", data={"amount": "1200.75", "category": "food", "date": TODAY,
                                           "payment_method": "upi", "description": "Lunch"}, follow_redirects=True)
    assert b"Expense added" in r.data
    rec = Expense.query.one()
    assert rec.amount == Decimal("1200.75")
    user_a.post(f"/expenses/{rec.id}/edit", data={"amount": "999", "category": "transport", "date": TODAY,
                                                  "payment_method": "cash", "description": "Cab"}, follow_redirects=True)
    db.session.refresh(rec)
    assert rec.category == "transport" and rec.amount == Decimal("999.00")
    user_a.post(f"/expenses/{rec.id}/delete", follow_redirects=True)
    assert Expense.query.count() == 0


def test_invalid_amounts_and_categories_rejected(app, user_a):
    for amount in ("0", "-50", "abc", ""):
        user_a.post("/expenses/new", data={"amount": amount, "category": "food", "date": TODAY, "payment_method": "upi"})
    user_a.post("/expenses/new", data={"amount": "10", "category": "not-a-category", "date": TODAY, "payment_method": "upi"})
    user_a.post("/income/new", data={"amount": "-5", "source": "salary", "date": TODAY})
    assert Expense.query.count() == 0 and Income.query.count() == 0


def test_totals_are_calculated_from_database(app, user_a):
    user_a.post("/income/new", data={"amount": "50000", "source": "salary", "date": TODAY})
    user_a.post("/income/new", data={"amount": "10000", "source": "freelance", "client": "Acme", "date": TODAY})
    user_a.post("/expenses/new", data={"amount": "20000", "category": "rent", "date": TODAY, "payment_method": "net_banking"})
    user_a.post("/expenses/new", data={"amount": "5000", "category": "food", "date": TODAY, "payment_method": "upi"})
    today = date.today()
    snap = get_snapshot(User.query.filter_by(email="a@example.com").one(), today.year, today.month)
    assert snap["income_total"] == Decimal("60000") and snap["expense_total"] == Decimal("25000")
    assert snap["balance"] == Decimal("35000") and round(snap["savings_rate"], 1) == 58.3
    assert snap["category_totals"]["rent"] == Decimal("20000")
    html = user_a.get("/dashboard").get_data(as_text=True)
    assert "60,000" in html and "25,000" in html and "35,000" in html


def test_expense_filters_and_search(app, user_a):
    for cat, desc in (("food", "Pizza night"), ("rent", "May rent"), ("food", "Groceries run")):
        user_a.post("/expenses/new", data={"amount": "100", "category": cat, "date": TODAY, "payment_method": "cash", "description": desc})
    html = user_a.get("/expenses/?category=rent").get_data(as_text=True)
    assert "May rent" in html and "Pizza night" not in html
    html = user_a.get("/expenses/?q=pizza").get_data(as_text=True)
    assert "Pizza night" in html and "May rent" not in html


def test_data_isolation_between_users(app, user_a, user_b):
    user_a.post("/expenses/new", data={"amount": "777", "category": "food", "date": TODAY, "payment_method": "upi", "description": "SECRET-A"})
    user_a.post("/income/new", data={"amount": "999", "source": "salary", "date": TODAY, "description": "INCOME-A"})
    exp, inc = Expense.query.one(), Income.query.one()
    assert user_b.get(f"/expenses/{exp.id}/edit").status_code == 404
    assert user_b.post(f"/expenses/{exp.id}/edit", data={"amount": "1", "category": "food", "date": TODAY, "payment_method": "upi"}).status_code == 404
    assert user_b.post(f"/expenses/{exp.id}/delete").status_code == 404
    assert user_b.post(f"/income/{inc.id}/delete").status_code == 404
    assert Expense.query.count() == 1 and Income.query.count() == 1
    assert "SECRET-A" not in user_b.get("/expenses/").get_data(as_text=True)
    csv_b = user_b.get("/reports/export/transactions.csv").get_data(as_text=True)
    assert "SECRET-A" not in csv_b and "INCOME-A" not in csv_b
    csv_a = user_a.get("/reports/export/transactions.csv").get_data(as_text=True)
    assert "SECRET-A" in csv_a and "INCOME-A" in csv_a


def test_deleting_account_only_removes_own_data(app, make_client):
    a, b = make_client("del-a@example.com"), make_client("del-b@example.com")
    for c in (a, b):
        c.post("/expenses/new", data={"amount": "10", "category": "food", "date": TODAY, "payment_method": "cash"})
    a.post("/profile/delete", data={"password": "Password123"}, follow_redirects=True)
    assert User.query.filter_by(email="del-a@example.com").first() is None
    assert Expense.query.count() == 1 and Expense.query.one().user_id == uid("del-b@example.com")


def test_csv_export_neutralises_formulas(app, user_a):
    user_a.post("/expenses/new", data={"amount": "5", "category": "other", "date": TODAY, "payment_method": "cash",
                                       "description": "=HYPERLINK(\"http://evil\")"})
    body = user_a.get("/reports/export/transactions.csv").get_data(as_text=True)
    assert "'=HYPERLINK" in body
