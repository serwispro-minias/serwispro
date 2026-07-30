"""
Routes for the customers module.

TODO: Add CRUD and view routes for customers here. For now this
module exposes a minimal index route placeholder. Do not implement
business logic in the routes; delegate to `services.py` and
`repository.py`.
"""

from . import bp


@bp.route('/')
def index():
    return (
        '<h1>Customers module</h1>'
        '<p>TODO: implement customers routes and views.</p>'
    )
