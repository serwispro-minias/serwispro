from flask import Blueprint

bp = Blueprint("opening_balances", __name__, url_prefix="/opening-balances")

from . import routes  # noqa: E402,F401

__all__ = ["bp"]
