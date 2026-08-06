from flask import Blueprint

bp = Blueprint("order_photos", __name__, url_prefix="/order-photos")

from . import routes  # noqa: F401

__all__ = ["bp"]
