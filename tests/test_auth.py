import pytest

from app.models import User

PROTECTED = ["/dashboard", "/income/", "/income/new", "/expenses/", "/expenses/new", "/budgets/",
             "/savings/", "/savings/new", "/advisor/", "/reports/", "/reports/export/transactions.csv",
             "/reports/export/report.pdf", "/profile"]


def test_landing_and_auth_pages_render(client):
    for path in ("/", "/auth/login", "/auth/register"):
        assert client.get(path).status_code == 200


def test_register_login_logout(app, client):
    r = client.post("/auth/register", data={"name": "Alice", "email": "Alice@Example.com", "profile_type": "student",
                                            "password": "Password123", "confirm": "Password123"}, follow_redirects=True)
    assert r.status_code == 200 and b"Dashboard" in r.data or b"Hello, Alice" in r.data
    user = User.query.filter_by(email="alice@example.com").one()  # email normalised to lower case
    assert user.profile_type == "student"
    assert client.post("/auth/logout", follow_redirects=True).status_code == 200
    assert client.get("/dashboard").status_code == 302          # logged out again
    r = client.post("/auth/login", data={"email": "alice@example.com", "password": "Password123"}, follow_redirects=True)
    assert b"Hello, Alice" in r.data


def test_password_is_hashed(app, make_client):
    make_client("hash@example.com")
    user = User.query.filter_by(email="hash@example.com").one()
    assert user.password_hash != "Password123" and "Password123" not in user.password_hash
    assert user.check_password("Password123") and not user.check_password("wrong")


def test_duplicate_email_and_weak_password_rejected(app, client, make_client):
    make_client("dup@example.com")
    r = client.post("/auth/register", data={"name": "X", "email": "dup@example.com", "profile_type": "salaried",
                                            "password": "Password123", "confirm": "Password123"})
    assert b"already exists" in r.data
    r = client.post("/auth/register", data={"name": "Y", "email": "new@example.com", "profile_type": "salaried",
                                            "password": "onlyletters", "confirm": "onlyletters"})
    assert b"at least one letter and one number" in r.data
    assert User.query.filter_by(email="new@example.com").first() is None


def test_wrong_password_rejected(app, make_client, client):
    make_client("login@example.com")
    r = client.post("/auth/login", data={"email": "login@example.com", "password": "nope-nope1"})
    assert b"Invalid email or password" in r.data


@pytest.mark.parametrize("path", PROTECTED)
def test_private_routes_require_login(client, path):
    r = client.get(path)
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_login_does_not_redirect_to_other_sites(app, make_client, client):
    make_client("redir@example.com")
    r = client.post("/auth/login?next=//evil.example.com", data={"email": "redir@example.com", "password": "Password123"})
    assert r.status_code == 302 and "evil.example.com" not in r.headers["Location"]


def test_logout_requires_post(user_a):
    assert user_a.get("/auth/logout").status_code == 405


def test_404_page_is_friendly(client):
    r = client.get("/definitely-not-here")
    assert r.status_code == 404 and b"Page not found" in r.data
