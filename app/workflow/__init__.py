from flask import Blueprint

bp = Blueprint("workflow", __name__, url_prefix="/workflow")

from . import routes  # noqa: F401

__all__ = ["bp"]
