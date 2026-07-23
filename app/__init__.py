from flask import Flask

from app.config import Config

from app.extensions import (
    db,
    migrate,
    login_manager
)


def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)


    db.init_app(app)

    migrate.init_app(
        app,
        db
    )

    login_manager.init_app(app)


    @app.route("/")
    def index():

        return """
        <h1>SerwisPRO</h1>

        <p>System działa poprawnie.</p>

        <p>Wersja 0.1.1</p>
        """


    return app