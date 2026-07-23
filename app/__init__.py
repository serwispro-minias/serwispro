from flask import Flask
from sqlalchemy import text

from app.config import Config

from app.extensions import (
    db,
    migrate,
    login_manager
)


def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)


    # Inicjalizacja rozszerzeń

    db.init_app(app)

    migrate.init_app(
        app,
        db
    )

    login_manager.init_app(app)


    # Strona główna

    @app.route("/")
    def index():

        return """
        <h1>SerwisPRO</h1>

        <p>System działa poprawnie.</p>

        <p>Wersja 0.1.1</p>

        """


    # Test połączenia z bazą danych

    @app.route("/test-db")
    def test_db():

        try:

            db.session.execute(
                text("SELECT 1")
            )

            return """
            <h2>Baza danych działa poprawnie</h2>
            <p>Połączenie Flask - MariaDB jest aktywne.</p>
            """

        except Exception as e:

            return f"""
            <h2>Błąd połączenia z bazą</h2>

            <pre>{e}</pre>
            """


    return app