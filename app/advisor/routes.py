"""Routes for the personal finance advisor."""
import json

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app.advisor import engine
from app.advisor.ai_client import AIError, generate_ai_reply
from app.constants import DISCLAIMER
from app.services import get_snapshot
from app.utils import period_from_request

bp = Blueprint("advisor", __name__, url_prefix="/advisor")


@bp.route("/")
@login_required
def index():
    year, month = period_from_request()
    snap = get_snapshot(current_user, year, month)

    return render_template(
        "advisor/index.html",
        year=year,
        month=month,
        snap=snap,
        ai_on=bool(
            current_app.config.get("AI_API_KEY")
            and current_user.ai_consent
        ),
        health=engine.health_score(snap),
        summary=engine.monthly_summary(snap),
        insights=engine.generate_insights(snap),
        saving_tips=engine.saving_suggestions(snap),
        strategies=engine.expense_reduction_strategies(snap),
        emergency=engine.emergency_fund_guidance(snap),
        plan=engine.budget_suggestions(snap),
    )


@bp.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question") or "").strip()

    if not question:
        return jsonify(error="Please enter a question."), 400

    if len(question) > 500:
        return jsonify(error="Please keep your question under 500 characters."), 400

    try:
        year = int(data.get("year"))
        month = int(data.get("month"))
        if not 1 <= month <= 12 or not 1900 <= year <= 2200:
            raise ValueError
    except (TypeError, ValueError):
        year, month = period_from_request()

    snap = get_snapshot(current_user, year, month)

    # Always have a built-in answer available.
    fallback = engine.answer_question(question, snap)

    # Only send aggregated financial figures to external AI when the user
    # has explicitly opted in and an API key is configured.
    if (
        current_user.ai_consent
        and current_app.config.get("AI_API_KEY")
    ):
        try:
            user_prompt = (
                "Answer the user's question using only this financial snapshot.\n"
                "Snapshot (JSON):\n"
                + json.dumps(engine.snapshot_to_plain(snap), ensure_ascii=False)
                + "\nUser question: "
                + question
            )
            reply = generate_ai_reply(
                current_app.config,
                engine.AI_SYSTEM_PROMPT,
                user_prompt,
            )
            return jsonify(reply=reply, source="ai")
        except (AIError, Exception):
            current_app.logger.warning(
                "External advisor request failed; using built-in advisor.",
                exc_info=True,
            )

    note = (
        "External AI is not enabled in Profile & settings; using the built-in advisor."
        if not current_user.ai_consent
        else "External AI is unavailable; using the built-in advisor."
    )
    return jsonify(reply=fallback, source="builtin", note=note)
