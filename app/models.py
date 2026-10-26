"""SQLAlchemy models. Every financial table carries a user_id for ownership."""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from flask_login import UserMixin
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from werkzeug.security import check_password_hash, generate_password_hash

from app.calculations import ZERO, goal_progress
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Money(TypeDecorator):
    """Exact money storage: Decimal in Python, integer minor units (x100) in the database."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(Decimal("0.01"))


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_type = db.Column(db.String(20), nullable=False, default="salaried")
    currency = db.Column(db.String(3), nullable=False, default="₹")
    ai_consent = db.Column(db.Boolean, nullable=False, default=False)

    incomes = db.relationship("Income", backref="user", cascade="all, delete-orphan")
    expenses = db.relationship("Expense", backref="user", cascade="all, delete-orphan")
    budgets = db.relationship("Budget", backref="user", cascade="all, delete-orphan")
    goals = db.relationship("SavingsGoal", backref="user", cascade="all, delete-orphan")

    def set_password(self, password):
        # PBKDF2 is used explicitly: scrypt is unavailable in some macOS system Python builds.
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.id}>"


class Income(TimestampMixin, db.Model):
    __tablename__ = "incomes"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_income_amount_positive"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = db.Column(Money, nullable=False)
    source = db.Column(db.String(30), nullable=False, default="salary")
    client = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.String(255))
    is_demo = db.Column(db.Boolean, nullable=False, default=False)


class Expense(TimestampMixin, db.Model):
    __tablename__ = "expenses"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_expense_amount_positive"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = db.Column(Money, nullable=False)
    category = db.Column(db.String(30), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    payment_method = db.Column(db.String(30), nullable=False, default="upi")
    description = db.Column(db.String(255))
    is_demo = db.Column(db.Boolean, nullable=False, default=False)


class Budget(TimestampMixin, db.Model):
    """One row per user/month/category. category == 'total' stores the overall monthly budget."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", "category", name="uq_budget_period_category"),
        CheckConstraint("amount > 0", name="ck_budget_amount_positive"),
        CheckConstraint("month >= 1 AND month <= 12", name="ck_budget_month"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(30), nullable=False)
    amount = db.Column(Money, nullable=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)


class SavingsGoal(TimestampMixin, db.Model):
    __tablename__ = "savings_goals"
    __table_args__ = (CheckConstraint("target_amount > 0", name="ck_goal_target_positive"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(Money, nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255))
    is_emergency = db.Column(db.Boolean, nullable=False, default=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)

    contributions = db.relationship(
        "SavingsContribution", backref="goal", cascade="all, delete-orphan",
        order_by="SavingsContribution.date.desc()",
    )

    @property
    def saved(self):
        return sum((c.amount for c in self.contributions), ZERO)

    def progress(self, today=None):
        dates = [c.date for c in self.contributions]
        return goal_progress(
            self.target_amount, self.saved, self.created_at.date() if self.created_at else None,
            self.target_date, today=today, first_contribution=min(dates) if dates else None,
        )


class SavingsContribution(TimestampMixin, db.Model):
    __tablename__ = "savings_contributions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_contribution_positive"),)

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, ForeignKey("savings_goals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = db.Column(Money, nullable=False)
    date = db.Column(db.Date, nullable=False)
    note = db.Column(db.String(255))
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
