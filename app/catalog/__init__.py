from flask import Blueprint

bp = Blueprint("catalog", __name__, url_prefix="/catalog")

from . import routes  # noqa: F401

__all__ = ["bp"]
