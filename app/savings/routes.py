from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import ContributionForm, GoalForm
from app.models import SavingsContribution, SavingsGoal
from app.utils import owned_or_404

bp = Blueprint("savings", __name__, url_prefix="/savings")


@bp.route("/")
@login_required
def index():
    goals = SavingsGoal.query.filter_by(user_id=current_user.id).order_by(SavingsGoal.target_date).all()
    items = [{"goal": g, "progress": g.progress()} for g in goals]
    total_saved = sum((i["progress"]["saved"] for i in items), 0)
    total_target = sum((i["progress"]["target"] for i in items), 0)
    return render_template("savings/index.html", items=items, total_saved=total_saved, total_target=total_target)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = GoalForm()
    if form.validate_on_submit():
        goal = SavingsGoal(user_id=current_user.id, name=form.name.data, target_amount=form.target_amount.data,
                           target_date=form.target_date.data, description=form.description.data or None,
                           is_emergency=bool(form.is_emergency.data))
        db.session.add(goal)
        db.session.commit()
        flash("Savings goal created.", "success")
        return redirect(url_for("savings.detail", goal_id=goal.id))
    return render_template("_form_page.html", form=form, title="New savings goal", icon="bi-piggy-bank",
                           cancel_url=url_for("savings.index"), submit_label="Create goal")


@bp.route("/<int:goal_id>", methods=["GET", "POST"])
@login_required
def detail(goal_id):
    goal = owned_or_404(SavingsGoal, goal_id)
    form = ContributionForm()
    if form.validate_on_submit():
        db.session.add(SavingsContribution(goal_id=goal.id, user_id=current_user.id, amount=form.amount.data,
                                           date=form.date.data, note=form.note.data or None))
        db.session.commit()
        flash("Contribution recorded.", "success")
        return redirect(url_for("savings.detail", goal_id=goal.id))
    return render_template("savings/detail.html", goal=goal, progress=goal.progress(), form=form)


@bp.route("/<int:goal_id>/edit", methods=["GET", "POST"])
@login_required
def edit(goal_id):
    goal = owned_or_404(SavingsGoal, goal_id)
    form = GoalForm(obj=goal)
    if form.validate_on_submit():
        goal.name = form.name.data
        goal.target_amount = form.target_amount.data
        goal.target_date = form.target_date.data
        goal.description = form.description.data or None
        goal.is_emergency = bool(form.is_emergency.data)
        goal.is_demo = False
        db.session.commit()
        flash("Goal updated.", "success")
        return redirect(url_for("savings.detail", goal_id=goal.id))
    return render_template("_form_page.html", form=form, title="Edit savings goal", icon="bi-piggy-bank",
                           cancel_url=url_for("savings.detail", goal_id=goal.id), submit_label="Update goal")


@bp.route("/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete(goal_id):
    goal = owned_or_404(SavingsGoal, goal_id)
    db.session.delete(goal)
    db.session.commit()
    flash("Goal deleted.", "info")
    return redirect(url_for("savings.index"))


@bp.route("/<int:goal_id>/contributions/<int:contribution_id>/delete", methods=["POST"])
@login_required
def delete_contribution(goal_id, contribution_id):
    goal = owned_or_404(SavingsGoal, goal_id)
    contribution = SavingsContribution.query.filter_by(id=contribution_id, goal_id=goal.id,
                                                       user_id=current_user.id).first_or_404()
    db.session.delete(contribution)
    db.session.commit()
    flash("Contribution removed.", "info")
    return redirect(url_for("savings.detail", goal_id=goal.id))
