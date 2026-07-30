from flask import Blueprint

bp = Blueprint('services', __name__, url_prefix='/services')

from . import routes  # noqa: F401

__all__ = ['bp']
