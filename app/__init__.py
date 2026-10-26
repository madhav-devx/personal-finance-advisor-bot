"""Personal Finance Advisor Bot - application factory."""
import os
import secrets
from datetime import date

from flask import Flask, render_template


def _ensure_secret_key(app):
    """Use SECRET_KEY from the environment, else create and reuse a private local key file."""
    if app.config.get("SECRET_KEY"):
        return
    key_file = os.path.join(app.instance_path, ".secret_key")
    try:
        with open(key_file, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
    except FileNotFoundError:
        key = ""
    if not key:
        key = secrets.token_hex(32)
        with open(key_file, "w", encoding="utf-8") as fh:
            fh.write(key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    app.config["SECRET_KEY"] = key


def create_app(config_object=None):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from app.extensions import csrf, db, login_manager

    if config_object is None:
        from config import Config as config_object

    app = Flask(__name__)
    app.config.from_object(config_object)
    os.makedirs(app.instance_path, exist_ok=True)
    _ensure_secret_key(app)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    @event.listens_for(Engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _record):
        # SQLite ignores foreign keys unless asked; this makes cascades and constraints real.
        if dbapi_connection.__class__.__module__.startswith("sqlite3"):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    from app.advisor.routes import bp as advisor_bp
    from app.auth.routes import bp as auth_bp
    from app.budgets.routes import bp as budgets_bp
    from app.dashboard.routes import bp as dashboard_bp
    from app.expenses.routes import bp as expenses_bp
    from app.income.routes import bp as income_bp
    from app.main import bp as main_bp
    from app.reports.routes import bp as reports_bp
    from app.savings.routes import bp as savings_bp

    for blueprint in (main_bp, auth_bp, dashboard_bp, income_bp, expenses_bp, budgets_bp,
                      savings_bp, advisor_bp, reports_bp):
        app.register_blueprint(blueprint)

    from app import utils

    app.add_template_filter(utils.money_filter, "money")
    app.add_template_filter(utils.percent_filter, "pct")
    app.add_template_filter(utils.category_label, "catlabel")
    app.add_template_filter(utils.source_label, "srclabel")
    app.add_template_filter(utils.payment_label, "paylabel")
    app.jinja_env.globals.update(month_choices=utils.MONTH_CHOICES, year_choices=utils.year_choices)

    @app.context_processor
    def inject_globals():
        from app.constants import APP_NAME, DISCLAIMER
        return {"APP_NAME": APP_NAME, "DISCLAIMER": DISCLAIMER, "today": date.today(),
                "ai_available": bool(app.config.get("AI_API_KEY"))}

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if "Cache-Control" not in response.headers and response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
        return response

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    register_cli(app)
    return app


def register_cli(app):
    import click

    from app.extensions import db

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (safe to run more than once)."""
        db.create_all()
        click.echo("Database initialised at: " + str(app.config["SQLALCHEMY_DATABASE_URI"]))

    @app.cli.command("create-demo-user")
    @click.option("--email", default="demo@example.com", show_default=True)
    @click.option("--password", default="DemoPass123", show_default=True)
    @click.option("--scenario", default="salaried", show_default=True,
                  type=click.Choice(["salaried", "student", "freelancer", "household"]))
    def create_demo_user(email, password, scenario):
        """Create a demo account pre-loaded with clearly-labelled demo data."""
        from app.demo import generate_demo_data
        from app.models import User

        db.create_all()
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            click.echo(f"A user with {email} already exists - nothing changed.")
            return
        user = User(name="Demo User", email=email, profile_type=scenario)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        generate_demo_data(user, scenario)
        click.echo(f"Created demo user {email} (password: {password}) with '{scenario}' demo data.")
