from flask import Blueprint

bp = Blueprint('devices', __name__, url_prefix='/devices')

from . import routes  # noqa: F401

__all__ = ['bp']
