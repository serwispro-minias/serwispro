from flask import Blueprint

bp = Blueprint('common', __name__, url_prefix='/common')

from . import routes  # noqa: F401

__all__ = ['bp']
