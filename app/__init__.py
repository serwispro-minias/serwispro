from __future__ import annotations

from typing import cast

from flask import Flask
from flask_login import login_required
from sqlalchemy import text

from app.api import bp as api_bp
from app.auth import bp as auth_bp
from app.common import bp as common_bp
from app.customers import bp as customers_bp
from app.dashboard import bp as dashboard_bp
from app.devices import bp as devices_bp
from app.extensions import db, login_manager, migrate
from app.inventory import bp as inventory_bp
from app.models import Company, SystemLog, User
from app.orders import bp as orders_bp
from app.reports import bp as reports_bp
from app.services import bp as services_bp
from app.settings import bp as settings_bp
from app.utils import bp as utils_bp
from config import get_config


def create_app(environment: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config["JSON_AS_ASCII"] = False

    app.config.from_object(get_config(environment))
    app.config.from_pyfile('config.py', silent=True)

    register_extensions(app)
    register_blueprints(app)
    register_routes(app)

    return app


def register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        return User.query.get(int(user_id))


def register_blueprints(app: Flask) -> None:
    for blueprint in [
        auth_bp,
        dashboard_bp,
        customers_bp,
        devices_bp,
        orders_bp,
        inventory_bp,
        reports_bp,
        settings_bp,
        common_bp,
        services_bp,
        api_bp,
        utils_bp,
    ]:
        app.register_blueprint(blueprint)


def register_routes(app: Flask) -> None:
    @app.route('/')
    def index() -> str:
        return (
            '<h1>SerwisPRO</h1>'
            '<p>System działa poprawnie.</p>'
            '<p><a href="/login">Logowanie</a></p>'
        )

    @app.route('/test-db')
    def test_db() -> str:
        try:
            db.session.execute(text('SELECT 1'))
            return '<h2>Baza danych działa poprawnie</h2>'
        except Exception as exc:
            return str(exc)

    @app.route('/dashboard')
    @login_required
    def dashboard() -> str:
        return (
            '<h1>Panel SerwisPRO</h1>'
            '<p>Zalogowano poprawnie.</p>'
            '<a href="/logout">Wyloguj</a>'
        )
