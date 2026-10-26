import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from config import TestingConfig  # noqa: E402

PASSWORD = "Password123"


@pytest.fixture()
def app(tmp_path):
    """A fresh app with its own temporary SQLite database for every test."""
    class Cfg(TestingConfig):
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + (tmp_path / "test.db").as_posix()

    application = create_app(Cfg)

    @application.teardown_request
    def _reset_login_cache(_exc):
        # The fixture below keeps ONE app context open for the whole test, and Flask reuses it for
        # every request. Flask-Login caches the current user on `g`, so without this reset a request
        # from user B could be served as user A (and the data-isolation tests would be meaningless).
        from flask import g
        g.pop("_login_user", None)

    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def make_client(app):
    """Factory: register + log in a brand-new user and return a dedicated test client."""
    def _make(email="user@example.com", name="Test User", profile="salaried"):
        c = app.test_client()
        r = c.post("/auth/register", data={"name": name, "email": email, "profile_type": profile,
                                           "password": PASSWORD, "confirm": PASSWORD}, follow_redirects=True)
        assert r.status_code == 200
        return c
    return _make


@pytest.fixture()
def user_a(make_client):
    return make_client("a@example.com", "Alice")


@pytest.fixture()
def user_b(make_client):
    return make_client("b@example.com", "Bob")
