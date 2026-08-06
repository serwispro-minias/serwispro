from flask import Blueprint

bp = Blueprint("estimate_approval", __name__, url_prefix="/estimate")

from . import routes  # noqa: F401

__all__ = ["bp"]
