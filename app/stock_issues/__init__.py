from flask import Blueprint

bp = Blueprint("stock_issues", __name__, url_prefix="/stock-issues")

from . import routes  # noqa: E402,F401

__all__ = ["bp"]