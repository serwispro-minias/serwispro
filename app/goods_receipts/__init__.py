from flask import Blueprint

bp = Blueprint("goods_receipts", __name__, url_prefix="/goods-receipts")

from . import routes  # noqa: E402,F401

__all__ = ["bp"]