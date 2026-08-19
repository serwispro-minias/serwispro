from flask import Blueprint

bp = Blueprint("purchase_orders", __name__, url_prefix="/purchase-orders")

from . import routes  # noqa: F401,E402

__all__ = ["bp"]