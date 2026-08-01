# -*- coding: utf-8 -*-

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import (
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash

from app.models.user import User

bp = Blueprint(
    "auth",
    __name__
)


@bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        login = request.form.get(
            "login"
        )

        password = request.form.get(
            "password"
        )


        user = User.query.filter_by(
            login=login
        ).first()

        if user:
            current_app.logger.debug("auth.login: user found for login=%s", login)
        else:
            current_app.logger.debug("auth.login: user not found for login=%s", login)


        if user and password and check_password_hash(
            user.password_hash,
            password
        ):

            current_app.logger.debug("auth.login: password valid for login=%s", login)

            login_user(user)

            current_app.logger.debug("auth.login: login_user executed for user_id=%s", user.id)

            response = redirect(
                url_for("dashboard.index")
            )

            current_app.logger.debug("auth.login: redirect executed to dashboard.index")

            return response

        if user:
            current_app.logger.debug("auth.login: invalid password for login=%s", login)
        else:
            current_app.logger.debug("auth.login: login failed due to missing user")


        flash(
            "Nieprawidłowy login lub hasło"
        )


    return render_template(
        "login.html"
    )


@bp.route("/logout")
def logout():

    logout_user()

    return redirect(
        url_for("auth.login")
    )
