from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models.inventory_stock_operation import INVENTORY_OPERATION_TYPE_CHOICES


UNIT_CHOICES: list[tuple[str, str]] = [
    ("szt.", "szt."),
    ("komplet", "komplet"),
    ("metr", "metr"),
    ("ml", "ml"),
    ("l", "l"),
    ("kg", "kg"),
]

VAT_CHOICES: list[tuple[str, str]] = [
    ("0", "0%"),
    ("5", "5%"),
    ("8", "8%"),
    ("23", "23%"),
]


class InventoryPartForm(FlaskForm):
    part_code = StringField("Kod części", validators=[DataRequired(), Length(max=80)])
    name = StringField("Nazwa", validators=[DataRequired(), Length(max=255)])
    category = StringField("Kategoria", validators=[Optional(), Length(max=120)])
    manufacturer = StringField("Producent", validators=[Optional(), Length(max=120)])
    catalog_number = StringField("Numer katalogowy", validators=[Optional(), Length(max=120)])
    barcode = StringField("Kod kreskowy", validators=[Optional(), Length(max=120)])
    description = TextAreaField("Opis", validators=[Optional(), Length(max=10000)])
    unit = SelectField("Jednostka", validators=[DataRequired()], choices=UNIT_CHOICES)
    minimum_stock = DecimalField("Minimalny stan", validators=[DataRequired(), NumberRange(min=0)], places=3)
    current_stock = DecimalField("Aktualny stan", validators=[DataRequired(), NumberRange(min=0)], places=3)
    location = StringField("Lokalizacja magazynowa", validators=[Optional(), Length(max=120)])
    purchase_price_net = DecimalField("Cena zakupu netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    sale_price_net = DecimalField("Cena sprzedaży netto", validators=[DataRequired(), NumberRange(min=0)], places=2)
    vat_rate = SelectField("Stawka VAT", validators=[DataRequired()], choices=VAT_CHOICES)
    supplier = StringField("Dostawca", validators=[Optional(), Length(max=180)])
    image_path = StringField("Ścieżka zdjęcia", validators=[Optional(), Length(max=500)])
    is_record_active = SelectField("Aktywny", validators=[DataRequired()], choices=[("1", "Tak"), ("0", "Nie")])
    submit = SubmitField("Zapisz")


class InventoryOperationForm(FlaskForm):
    operation_type = SelectField("Typ operacji", validators=[DataRequired()], choices=INVENTORY_OPERATION_TYPE_CHOICES)
    quantity = DecimalField("Ilość", validators=[DataRequired()], places=3)
    document_number = StringField("Numer dokumentu", validators=[Optional(), Length(max=120)])
    comment = TextAreaField("Komentarz", validators=[Optional(), Length(max=3000)])
    submit = SubmitField("Zapisz operację")


class InventorySearchForm(FlaskForm):
    q = StringField("Szukaj", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Szukaj")
