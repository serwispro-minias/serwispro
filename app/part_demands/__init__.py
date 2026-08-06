from flask import Blueprint

bp = Blueprint("part_demands", __name__, url_prefix="/part-demands")

from . import routes  # noqa: F401

__all__ = ["bp"]
