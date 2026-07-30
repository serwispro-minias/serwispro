"""
Customers blueprint package

TODO: This package exposes the `bp` Blueprint used to register
the customers module in the main application. Place module
initialization and imports here.
"""

from flask import Blueprint

bp = Blueprint('customers', __name__, url_prefix='/customers')

# Import routes to ensure they are registered with the blueprint.
from . import routes  # noqa: F401

from .exceptions import (
    CustomerError,
    CustomerNotFoundError,
    CustomerAlreadyExistsError,
    CustomerValidationError,
    CustomerInactiveError,
)
from .validators import CustomerValidator

__all__ = [
    'bp',
    'CustomerError',
    'CustomerNotFoundError',
    'CustomerAlreadyExistsError',
    'CustomerValidationError',
    'CustomerInactiveError',
    'CustomerValidator',
]
