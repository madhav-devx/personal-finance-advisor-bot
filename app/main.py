"""Landing page, profile/settings, demo data and account deletion."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required, logout_user

from app.demo import generate_demo_data, has_demo_data, remove_demo_data
from app.extensions import db
from app.forms import DeleteAccountForm, DemoForm, PasswordForm, ProfileForm
from app.models import User

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.profile_type = form.profile_type.data
        current_user.currency = form.currency.data
        current_user.ai_consent = bool(form.ai_consent.data)
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("main.profile"))
    return render_template("profile/index.html", form=form, password_form=PasswordForm(),
                           delete_form=DeleteAccountForm(), demo_form=DemoForm(),
                           has_demo=has_demo_data(current_user))


@bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    form = PasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash("Password changed.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
    return redirect(url_for("main.profile"))


@bp.route("/profile/demo", methods=["POST"])
@login_required
def load_demo():
    form = DemoForm()
    if form.validate_on_submit():
        if generate_demo_data(current_user, form.scenario.data):
            flash("Demo data added. It is labelled [Demo] and can be removed at any time.", "success")
        else:
            flash("Demo data already exists. Remove it first to load a different scenario.", "warning")
    return redirect(url_for("main.profile"))


@bp.route("/profile/demo/remove", methods=["POST"])
@login_required
def remove_demo():
    removed = remove_demo_data(current_user)
    flash(f"Removed {removed} demo records. Your own data was not touched.", "success")
    return redirect(url_for("main.profile"))


@bp.route("/profile/delete", methods=["POST"])
@login_required
def delete_account():
    form = DeleteAccountForm()
    if form.validate_on_submit() and current_user.check_password(form.password.data):
        user = db.session.get(User, current_user.id)
        logout_user()
        db.session.delete(user)  # cascades only to this user's own records
        db.session.commit()
        flash("Your account and all of its data were deleted.", "info")
        return redirect(url_for("main.index"))
    flash("Password incorrect - account was not deleted.", "danger")
    return redirect(url_for("main.profile"))
