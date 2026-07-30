from flask import Blueprint

bp = Blueprint('inventory', __name__, url_prefix='/inventory')

from . import routes  # noqa: F401

__all__ = ['bp']
