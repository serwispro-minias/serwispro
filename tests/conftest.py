from __future__ import annotations

from collections.abc import Generator

import pytest
from jinja2 import ChoiceLoader, DictLoader

from app import create_app
from app.extensions import db
from app.models.branch import Branch
from app.models.company import Company
from app.models.customer import Customer
from app.models.user import User


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch) -> Generator:
    app = create_app("testing")
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )
    app.jinja_env.globals["csrf_token"] = lambda: ""

    template_overrides = DictLoader(
        {
            "customers/index.html": (
                "{% for c in customers['items'] %}{{ c.id }}:{{ c.full_name }}\\n{% endfor %}"
                "TOTAL={{ customers['total'] }} PAGE={{ customers['page'] }} "
                "PAGES={{ customers['pages'] }} Q={{ q }}"
            ),
            "customers/form.html": (
                "{{ title }}"
                "<form method='post'>"
                "{{ form.customer_type() }}"
                "{{ form.full_name() }}"
                "{{ form.email() }}"
                "{{ form.phone() }}"
                "{{ form.submit() }}"
                "</form>"
            ),
            "customers/details.html": "ID={{ customer.id }} NAME={{ customer.full_name }} ACTIVE={{ customer.is_active }}",
        }
    )
    app.jinja_loader = ChoiceLoader([template_overrides, app.jinja_loader])

    from app.customers import routes as customer_routes

    monkeypatch.setattr(customer_routes.service.validator, "normalize", lambda data: data)
    monkeypatch.setattr(customer_routes.service.validator, "validate_create", lambda data: None)
    monkeypatch.setattr(
        customer_routes.service.validator,
        "validate_update",
        lambda customer_id, data: None,
    )

    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Company.__table__,
                Branch.__table__,
                User.__table__,
                Customer.__table__,
            ],
        )

        company = Company(name="Test Company", prefix="TST")
        db.session.add(company)
        db.session.flush()

        user = User(
            login="tester",
            password_hash="not-used-in-tests",
            company_id=company.id,
        )
        db.session.add(user)
        db.session.commit()

        app.config["TEST_COMPANY_ID"] = company.id
        app.config["TEST_USER_ID"] = user.id

    yield app

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                Customer.__table__,
                User.__table__,
                Branch.__table__,
                Company.__table__,
            ],
        )


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(client, app):
    with client.session_transaction() as session:
        session["_user_id"] = str(app.config["TEST_USER_ID"])
        session["_fresh"] = True
    return client


@pytest.fixture()
def company_id(app) -> int:
    return int(app.config["TEST_COMPANY_ID"])
