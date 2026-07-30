from flask import Blueprint

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

from . import routes  # noqa: F401

__all__ = ['bp']
