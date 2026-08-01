from __future__ import annotations

from app.extensions import db
from app.models.customer import Customer, CustomerTypeEnum


def _create_customer(*, company_id: int, full_name: str, email: str, phone: str, is_active: bool = True) -> Customer:
    customer = Customer(
        company_id=company_id,
        customer_type=CustomerTypeEnum.PERSON,
        full_name=full_name,
        email=email,
        phone=phone,
        is_active=is_active,
    )
    db.session.add(customer)
    db.session.commit()
    return customer


def _customer_form_payload(**overrides):
    payload = {
        "customer_type": CustomerTypeEnum.PERSON.value,
        "full_name": "Jan Kowalski",
        "short_name": "Jan-Kow",
        "first_name": "Jan",
        "last_name": "Kowalski",
        "nip": "1234567890",
        "regon": "123456789",
        "krs": "0000123456",
        "pesel": "90010112345",
        "email": "jan@example.com",
        "phone": "+48123456789",
        "phone2": "",
        "website": "",
        "country": "PL",
        "state": "Mazowieckie",
        "postal_code": "00-001",
        "city": "Warszawa",
        "street": "Testowa",
        "building_no": "1",
        "apartment_no": "2",
        "notes": "test",
        "submit": "Zapisz",
    }
    payload.update(overrides)
    return payload


def test_customer_list_page(auth_client, app, company_id):
    with app.app_context():
        _create_customer(
            company_id=company_id,
            full_name="Lista Klient",
            email="lista@example.com",
            phone="111111111",
        )

    response = auth_client.get("/customers/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Lista Klient" in body
    assert "TOTAL=1" in body


def test_create_customer(auth_client, app):
    response = auth_client.post(
        "/customers/create",
        data=_customer_form_payload(
            full_name="Nowy Klient",
            email="nowy@example.com",
            phone="222222222",
            nip="2222222222",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "NAME=Nowy Klient" in body

    with app.app_context():
        created = Customer.query.filter_by(email="nowy@example.com").one()
        assert created.full_name == "Nowy Klient"
        assert created.is_active is True


def test_edit_customer(auth_client, app, company_id):
    with app.app_context():
        customer = _create_customer(
            company_id=company_id,
            full_name="Przed Edycja",
            email="przed@example.com",
            phone="333333333",
        )
        customer_id = customer.id

    response = auth_client.post(
        f"/customers/{customer_id}/edit",
        data=_customer_form_payload(
            full_name="Po Edycji",
            email="po@example.com",
            phone="444444444",
            nip="3333333333",
        ),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "NAME=Po Edycji" in response.get_data(as_text=True)

    with app.app_context():
        updated = db.session.get(Customer, customer_id)
        assert updated is not None
        assert updated.full_name == "Po Edycji"
        assert updated.email == "po@example.com"


def test_soft_delete_customer(auth_client, app, company_id):
    with app.app_context():
        customer = _create_customer(
            company_id=company_id,
            full_name="Do Usuniecia",
            email="usun@example.com",
            phone="555555555",
        )
        customer_id = customer.id

    response = auth_client.post(f"/customers/{customer_id}/delete", follow_redirects=True)

    assert response.status_code == 200

    with app.app_context():
        deleted = db.session.get(Customer, customer_id)
        assert deleted is not None
        assert deleted.is_active is False

    list_response = auth_client.get("/customers/")
    assert "Do Usuniecia" not in list_response.get_data(as_text=True)


def test_search_customers(auth_client, app, company_id):
    with app.app_context():
        _create_customer(
            company_id=company_id,
            full_name="Alpha Serwis",
            email="alpha@example.com",
            phone="666666666",
        )
        _create_customer(
            company_id=company_id,
            full_name="Beta Serwis",
            email="beta@example.com",
            phone="777777777",
        )

    response = auth_client.get("/customers/?q=Alpha")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Alpha Serwis" in body
    assert "Beta Serwis" not in body
    assert "Q=Alpha" in body


def test_customers_pagination(auth_client, app, company_id):
    with app.app_context():
        for idx in range(1, 22):
            _create_customer(
                company_id=company_id,
                full_name=f"Customer {idx:02d}",
                email=f"customer{idx:02d}@example.com",
                phone=f"48{idx:09d}",
            )

    page_1 = auth_client.get("/customers/?page=1")
    page_2 = auth_client.get("/customers/?page=2")

    assert page_1.status_code == 200
    assert page_2.status_code == 200

    page_1_body = page_1.get_data(as_text=True)
    page_2_body = page_2.get_data(as_text=True)

    assert "PAGES=2" in page_1_body
    assert "PAGE=1" in page_1_body
    assert "PAGE=2" in page_2_body

    assert "Customer 01" in page_1_body
    assert "Customer 21" not in page_1_body
    assert "Customer 21" in page_2_body
