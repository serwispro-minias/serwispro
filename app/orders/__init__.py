from flask import Blueprint

bp = Blueprint('orders', __name__, url_prefix='/orders')

from . import routes  # noqa: F401

__all__ = ['bp']
