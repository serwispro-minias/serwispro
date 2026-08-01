from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import Email, Length, Optional

from app.models.customer import CustomerTypeEnum


class CustomerForm(FlaskForm):
    customer_type = SelectField(
        "Typ klienta",
        choices=[
            ("", "Wybierz typ klienta"),
            (CustomerTypeEnum.PERSON.value, "Osoba"),
            (CustomerTypeEnum.COMPANY.value, "Firma"),
        ],
        validators=[Optional()],
        coerce=str,
    )
    full_name = StringField(
        "Nazwa klienta",
        validators=[Optional(), Length(max=255)],
        render_kw={"placeholder": "Pełna nazwa klienta"},
    )
    short_name = StringField(
        "Nazwa skrócona",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Skrócona nazwa, np. ABB"},
    )
    first_name = StringField(
        "Imię",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Imię klienta"},
    )
    last_name = StringField(
        "Nazwisko",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Nazwisko klienta"},
    )
    nip = StringField(
        "NIP",
        validators=[Optional(), Length(max=32)],
        render_kw={"placeholder": "NIP klienta"},
    )
    regon = StringField(
        "REGON",
        validators=[Optional(), Length(max=32)],
        render_kw={"placeholder": "REGON klienta"},
    )
    krs = StringField(
        "KRS",
        validators=[Optional(), Length(max=32)],
        render_kw={"placeholder": "KRS klienta"},
    )
    pesel = StringField(
        "PESEL",
        validators=[Optional(), Length(max=32)],
        render_kw={"placeholder": "PESEL klienta"},
    )
    email = StringField(
        "Email",
        validators=[Optional(), Email(), Length(max=120)],
        render_kw={"placeholder": "Email klienta"},
    )
    phone = StringField(
        "Telefon",
        validators=[Optional(), Length(max=50)],
        render_kw={"placeholder": "Numer telefonu"},
    )
    phone2 = StringField(
        "Telefon 2",
        validators=[Optional(), Length(max=50)],
        render_kw={"placeholder": "Drugi numer telefonu"},
    )
    website = StringField(
        "Strona internetowa",
        validators=[Optional(), Length(max=255)],
        render_kw={"placeholder": "Adres strony WWW"},
    )
    country = StringField(
        "Kraj",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Kraj"},
    )
    state = StringField(
        "Województwo",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Województwo"},
    )
    postal_code = StringField(
        "Kod pocztowy",
        validators=[Optional(), Length(max=20)],
        render_kw={"placeholder": "Kod pocztowy"},
    )
    city = StringField(
        "Miasto",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Miasto"},
    )
    street = StringField(
        "Ulica",
        validators=[Optional(), Length(max=200)],
        render_kw={"placeholder": "Ulica"},
    )
    building_no = StringField(
        "Nr budynku",
        validators=[Optional(), Length(max=20)],
        render_kw={"placeholder": "Numer budynku"},
    )
    apartment_no = StringField(
        "Nr lokalu",
        validators=[Optional(), Length(max=20)],
        render_kw={"placeholder": "Numer mieszkania"},
    )
    notes = TextAreaField(
        "Notatki",
        validators=[Optional(), Length(max=1000)],
        render_kw={"rows": 4, "placeholder": "Dodatkowe informacje o kliencie"},
    )
    submit = SubmitField("Zapisz")
