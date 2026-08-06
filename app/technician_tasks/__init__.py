from flask import Blueprint

bp = Blueprint("technician_tasks", __name__, url_prefix="/tasks")

from . import routes  # noqa: F401

__all__ = ["bp"]
