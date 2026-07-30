from flask import Blueprint

bp = Blueprint('settings', __name__, url_prefix='/settings')

from . import routes  # noqa: F401

__all__ = ['bp']
