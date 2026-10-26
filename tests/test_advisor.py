"""Advisor engine tests (pure) plus chat-endpoint tests (use the app fixtures)."""
from decimal import Decimal as Dm

from app.advisor import engine
from helpers import Z, make_snapshot


def test_student_example_flags_food_and_entertainment():
    snap = make_snapshot()
    titles = " | ".join(i["title"] for i in engine.generate_insights(snap))
    assert "Food" in titles and "Entertainment" in titles
    flagged = {f["category"] for f in engine.flagged_categories(snap)}
    assert {"food", "entertainment"} <= flagged


def test_overspending_is_reported_as_danger():
    snap = make_snapshot(income_total=Dm(5000), balance=Dm(-2600), savings_rate=-52.0)
    first = engine.generate_insights(snap)[0]
    assert first["level"] == "danger" and "more than you earned" in first["title"]


def test_budget_levels_80_percent_and_over():
    snap = make_snapshot(budgets={"food": Dm(3500), "entertainment": Dm(1000), "transport": Dm(5000)})
    rows = {r["category"]: r for r in engine.budget_rows(snap)}
    assert rows["food"]["level"] == "warn"            # 3000/3500 = 85.7%
    assert rows["entertainment"]["level"] == "over"   # 200%
    assert rows["transport"]["level"] == "ok"
    keys = {a["key"] for a in engine.budget_alerts(snap)}
    assert {"warn_food", "over_entertainment"} <= keys


def test_budget_utilization_prefers_total_budget():
    snap = make_snapshot(total_budget=Dm(9000))           # 7600 / 9000 = 84% -> warning
    util = engine.budget_utilization(snap)
    assert util["limit"] == Dm(9000) and util["level"] == "warn" and util["remaining"] == Dm(1400)
    assert engine.budget_utilization(make_snapshot(total_budget=Dm(10000)))["level"] == "ok"   # 76%
    assert engine.budget_utilization(make_snapshot(total_budget=Dm(7000)))["level"] == "over"
    assert engine.budget_utilization(make_snapshot()) is None


def test_suggestions_never_negative_and_within_income():
    for profile in ("student", "salaried", "freelancer", "household"):
        for income in (Dm(8000), Dm(1000)):
            snap = make_snapshot(profile_type=profile, income_total=income, income_history=[income])
            s = engine.budget_suggestions(snap)
            assert s["possible"]
            assert all(v >= 0 for v in s["categories"].values())
            assert s["total"] <= income
            assert s["total"] <= s["spendable"]


def test_suggestions_without_income_or_history():
    none = engine.budget_suggestions(make_snapshot(income_total=Z, income_history=[]))
    assert none["possible"] is False and none["categories"] == {}
    fresh = make_snapshot(category_totals={}, category_avg={}, expense_total=Z, balance=Dm(8000))
    s = engine.budget_suggestions(fresh)
    assert s["possible"] and 0 < s["total"] <= Dm(8000)


def test_extreme_essentials_are_scaled_down():
    snap = make_snapshot(category_avg={"rent": Dm(9000), "food": Dm(3000)}, income_total=Dm(8000))
    s = engine.budget_suggestions(snap)
    assert s["total"] <= s["spendable"] and "scaled down" in " ".join(s["notes"])


def test_freelancer_uses_conservative_planning_income():
    snap = make_snapshot(profile_type="freelancer", income_history=[Dm(40000), Dm(80000), Dm(60000)],
                         income_variability=0.67)
    assert engine.base_income(snap) == Dm("51000.00")
    assert any(i["key"] == "variable_income" for i in engine.generate_insights(snap))


def test_emergency_fund_guidance():
    ef = engine.emergency_fund_guidance(make_snapshot(profile_type="freelancer", emergency_saved=Dm(10000)))
    assert ef["months_target"] == 6 and ef["gap"] > 0 and ef["current"] == Dm(10000)
    done = engine.emergency_fund_guidance(make_snapshot(emergency_saved=Dm(1000000)))
    assert done["gap"] == 0 and done["months_to_goal"] == 0
    assert engine.emergency_fund_guidance(make_snapshot(category_avg={}, avg_expense=Z)) is None


def test_health_score_range_and_empty_state():
    score = engine.health_score(make_snapshot())
    assert 0 <= score["score"] <= 100
    empty = engine.health_score(make_snapshot(income_total=Z, expense_total=Z, category_totals={}))
    assert empty["score"] is None


def test_empty_snapshot_gives_guidance_not_numbers():
    snap = make_snapshot(income_total=Z, expense_total=Z, balance=Z, savings_rate=None, category_totals={})
    insights = engine.generate_insights(snap)
    assert len(insights) == 1 and insights[0]["key"] == "no_data"


def test_chat_answers_are_grounded_and_refuse_investment_advice():
    snap = make_snapshot()
    assert "₹3,000" in engine.answer_question("where am I overspending?", snap)
    assert "emergency" in engine.answer_question("tell me about my emergency fund", snap).lower()
    reply = engine.answer_question("Which stocks will give guaranteed returns?", snap)
    assert "cannot recommend" in reply and "guaranteed" in reply


def test_month_over_month_increase_is_reported():
    prev = dict(has_data=True, income=Dm(8000), expense=Dm(5000), balance=Dm(3000), categories={"food": Dm(1500)})
    insights = engine.generate_insights(make_snapshot(previous=prev))
    assert any(i["key"] == "up_food" for i in insights)


def test_snapshot_to_plain_has_no_identity_and_is_json_safe():
    import json
    plain = engine.snapshot_to_plain(make_snapshot())
    json.dumps(plain)
    assert "email" not in plain and "name" not in plain


# ---------------------------------------------------------------- endpoint tests (need app fixtures)
def test_chat_endpoint_uses_builtin_without_key(app, make_client):
    client = make_client("chat@example.com")
    r = client.post("/advisor/chat", json={"question": "How can I save more?"})
    assert r.status_code == 200 and r.get_json()["source"] == "builtin"
    assert client.post("/advisor/chat", json={"question": ""}).status_code == 400
    assert client.post("/advisor/chat", json={"question": "x" * 600}).status_code == 400


def test_ai_not_called_without_user_consent(app, make_client, monkeypatch):
    import app.advisor.routes as routes
    app.config["AI_API_KEY"] = "sk-test"
    monkeypatch.setattr(routes, "generate_ai_reply", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    client = make_client("noconsent@example.com")
    assert client.post("/advisor/chat", json={"question": "hello"}).get_json()["source"] == "builtin"


def test_ai_failure_falls_back_to_builtin(app, make_client, monkeypatch):
    import app.advisor.routes as routes
    from app.advisor.ai_client import AIError
    from app.extensions import db
    from app.models import User
    app.config["AI_API_KEY"] = "sk-test"
    client = make_client("consent@example.com")
    User.query.filter_by(email="consent@example.com").one().ai_consent = True
    db.session.commit()

    def boom(*a, **k):
        raise AIError("down")
    monkeypatch.setattr(routes, "generate_ai_reply", boom)
    body = client.post("/advisor/chat", json={"question": "hello"}).get_json()
    assert body["source"] == "builtin" and "unavailable" in body["note"]
    monkeypatch.setattr(routes, "generate_ai_reply", lambda *a, **k: "AI says hi")
    assert client.post("/advisor/chat", json={"question": "hello"}).get_json() == {"reply": "AI says hi", "source": "ai"}


def test_advisor_page_renders_with_demo_data(app, make_client):
    from app.demo import generate_demo_data
    from app.models import User
    client = make_client("advpage@example.com")
    generate_demo_data(User.query.filter_by(email="advpage@example.com").one(), "student")
    r = client.get("/advisor/")
    assert r.status_code == 200 and b"Ask the advisor" in r.data
