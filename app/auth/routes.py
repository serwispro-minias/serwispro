# -*- coding: utf-8 -*-

from flask import Blueprint, flash, redirect, render_template, request, url_for
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

        username = request.form.get(
            "username"
        )

        password = request.form.get(
            "password"
        )


        user = User.query.filter_by(
            username=username
        ).first()


        if user and password and check_password_hash(
            user.password_hash,
            password
        ):

            login_user(user)

            return redirect(
                url_for("dashboard")
            )


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
