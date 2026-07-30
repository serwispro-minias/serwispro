from app import create_app


def test_create_app():
    app = create_app("testing")
    assert app is not None
    assert app.config["TESTING"] is True
